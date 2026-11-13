"""ffmpeg / ffprobe 封装与 GIF 两遍调色板生成。纯逻辑层，不依赖 Qt，可独立测试。"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

VIDEO_EXTS = {".ts", ".m2ts", ".mts", ".mp4", ".m4v", ".mkv", ".avi", ".mov",
              ".flv", ".webm", ".wmv", ".mpg", ".mpeg", ".3gp", ".ogv", ".vob"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DITHER_MAP = {
    "bayer": "bayer:bayer_scale=3",
    "floyd": "floyd_steinberg",
    "none": "none",
}


class FfmpegError(RuntimeError):
    pass


class FfmpegCancelled(FfmpegError):
    pass


def _base_dirs():
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
    dirs.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return dirs


def tool_path(name: str):
    """查找顺序：程序目录 bin 目录 → PyInstaller 解包目录 bin → PATH。"""
    exe_names = (name + ".exe", name) if os.name == "nt" else (name,)
    for base in _base_dirs():
        for n in exe_names:
            p = os.path.join(base, "bin", n)
            if os.path.isfile(p):
                return p
    return shutil.which(name)


def available():
    missing = [n for n in ("ffmpeg", "ffprobe") if not tool_path(n)]
    if missing:
        return False, "未找到 " + "、".join(missing) + "：请放入程序目录的 bin\\ 文件夹，或加入 PATH"
    return True, "OK"


def _run(args, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=CREATE_NO_WINDOW, timeout=timeout)


def probe(path: str) -> dict:
    ffprobe = tool_path("ffprobe")
    if not ffprobe:
        raise FfmpegError("未找到 ffprobe")
    p = _run([ffprobe, "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", path])
    if p.returncode != 0:
        raise FfmpegError("读取媒体信息失败: " + (p.stderr or "").strip()[-500:])
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise FfmpegError(f"无法解析媒体信息: {e}")
    vs = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not vs:
        raise FfmpegError("文件中没有可用的视频流")

    def fps_of(v):
        try:
            num, den = v.split("/")
            den = float(den)
            return float(num) / den if den else 0.0
        except (ValueError, AttributeError, ZeroDivisionError):
            return 0.0

    duration = 0.0
    for src in (data.get("format", {}).get("duration"), vs.get("duration")):
        try:
            duration = max(duration, float(src))
        except (TypeError, ValueError):
            pass
    size = 0
    try:
        size = int(float(data.get("format", {}).get("size") or 0))
    except (TypeError, ValueError):
        pass
    return {
        "path": path,
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "duration": duration,
        "fps": fps_of(vs.get("avg_frame_rate", "")) or fps_of(vs.get("r_frame_rate", "")),
        "codec": vs.get("codec_name", "?"),
        "field_order": vs.get("field_order") or "unknown",
        "frames": int(vs["nb_frames"]) if str(vs.get("nb_frames", "")).isdigit() else 0,
        "size": size,
    }


_TIME_RE = re.compile(r"^out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def run_with_progress(args, duration, progress=None, cancel_check=None):
    """执行 ffmpeg 并从 -progress pipe:1 解析 out_time= 汇报 0~1 进度。

    cancel_check 每读一行进度调用一次，返回 True 时杀死子进程并抛 FfmpegCancelled；
    任何异常退出路径都会杀掉残留的 ffmpeg 进程，避免孤儿进程。
    """
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error",
           "-progress", "pipe:1", *args]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=CREATE_NO_WINDOW)
        try:
            last = 0.0
            for line in proc.stdout:
                if cancel_check is not None and cancel_check():
                    raise FfmpegCancelled("已取消")
                m = _TIME_RE.match(line.strip())
                if m and duration > 0 and progress:
                    t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                    last = max(last, t / duration)
                    progress(min(0.999, last))
            proc.wait()
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        errf.seek(0)
        stderr = errf.read() or ""
    if proc.returncode != 0:
        raise FfmpegError("ffmpeg 执行失败: " + stderr.strip()[-800:])


INTERLACED_ORDERS = {"tt", "bb", "tb", "bt"}

# 目标体积模式的可调档位（从用户参数向下搜索，只降不升）
FPS_LADDER = (30, 24, 20, 15, 12, 10, 8, 6)
COLORS_LADDER = (256, 192, 128, 96, 64, 48, 32)
WIDTH_LADDER = (1920, 1600, 1280, 960, 720, 600, 480, 360, 240)


def _need_deinterlace(mode, field_order):
    """mode ∈ {auto,on,off}：auto 按探测到的 field_order 判定。"""
    if mode == "on":
        return True
    if mode == "off":
        return False
    return (field_order or "unknown") in INTERLACED_ORDERS


def _down_ladder(start, ladder, floor):
    """从 start 向下的档位表（含 start，降序；不低于 floor，除非 start 本身更低）。"""
    vals = sorted({int(start), *(v for v in ladder if v <= start)}, reverse=True)
    if start >= floor:
        vals = [v for v in vals if v >= floor]
    return vals


def _pick_ladder(ladder, cur, bound):
    """ladder 降序，cur 为当前值：返回 ≤ min(bound,cur) 的最大档（往更小的一端找）；
    至少降一档。"""
    i = ladder.index(cur)
    for j in range(i, len(ladder)):
        if ladder[j] <= bound:
            if j == i:                # bound 没压出降幅时也至少降一档
                return ladder[i + 1] if i + 1 < len(ladder) else ladder[i]
            return ladder[j]
    return ladder[-1]


def build_chain(crop, width, fps, deinterlace=False):
    """滤镜链：yadif(可选，隔行源) → crop(可选) → scale(可选，高度自适应) → fps。"""
    parts = []
    if deinterlace:
        parts.append("yadif=0:-1:0")
    if crop:
        x, y, w, h = crop
        parts.append(f"crop={w}:{h}:{x}:{y}")
    if width:
        parts.append(f"scale={width}:-1:flags=lanczos")
    parts.append(f"fps={fps}")
    return ",".join(parts)


def make_gif(video, out_path, start=0.0, duration=None, crop=None, width=720,
             fps=12, colors=128, dither="bayer", deinterlace="off",
             target_mb=None, progress=None, cancel_check=None):
    """两遍调色板法生成 GIF。video 也可以是 .gif（动图再压缩）。

    target_mb 给定时进入目标体积模式：以传入参数为质量上限只降不升
    （帧率→颜色数→宽度），最多 4 轮，返回体积 ≤ 目标的最优轮；
    到下限仍超则返回最小一轮，由 applied["target_hit"]=False 提示调用方。

    返回 (产物路径, applied 参数 dict)：fps/colors/width/dither/deinterlace/
    bytes/target_hit/adjusted。width=0（原始宽度）未调整时保持 0。
    """
    info = probe(video)
    total = info["duration"] or 0
    if duration is None:
        duration = max(0.0, total - start) if total else None
    seg = duration or (max(0.0, total - start) if total else 0)
    need_deint = _need_deinterlace(deinterlace, info.get("field_order"))
    if progress:
        progress(0.0)

    start_w = width or (crop[2] if crop else info["width"] or 720)
    fps_l = _down_ladder(fps, FPS_LADDER, 6)
    colors_l = _down_ladder(colors, COLORS_LADDER, 32)
    width_l = _down_ladder(start_w, WIDTH_LADDER, 240)
    target = float(target_mb) * 1024 * 1024 if target_mb else None

    tmp_pal = os.path.join(tempfile.gettempdir(),
                           f"gifkit_{os.getpid()}_palette.png")
    rounds = []                       # (size, path, fps, colors, width)

    def report(p, base, span):
        if progress:
            progress(min(0.999, base + p * span))

    try:
        seg_args = ["-ss", f"{max(0.0, start):.3f}"]
        if duration:
            seg_args += ["-t", f"{duration:.3f}"]
        seg_args += ["-i", video]

        cur = (fps_l[0], colors_l[0], width_l[0])
        while True:
            i = len(rounds)
            if cancel_check is not None and cancel_check():
                raise FfmpegCancelled("已取消")
            f, c, w = cur
            rpath = out_path if target is None else f"{out_path}.r{i}.gif"
            chain = build_chain(crop, w, f, deinterlace=need_deint)
            est_rounds = 4 if target is None or not rounds else \
                max(2, min(4, int(math.log2(max(1.05, rounds[0][0] / target))) + 2))
            base, span = (0.0, 1.0) if target is None else (i / est_rounds, 1 / est_rounds)

            pass1 = [*seg_args, "-vf",
                     f"{chain},palettegen=max_colors={c}:stats_mode=diff",
                     "-update", "1", "-y", tmp_pal]
            run_with_progress(pass1, seg, (lambda p: report(p * 0.45, base, span)),
                              cancel_check)

            d = DITHER_MAP.get(dither, dither)
            fc = f"[0:v]{chain}[v];[v][1:v]paletteuse=dither={d}[out]"
            pass2 = [*seg_args, "-i", tmp_pal, "-filter_complex", fc,
                     "-map", "[out]", "-loop", "0", "-y", rpath]
            run_with_progress(pass2, seg, (lambda p: report(0.45 + p * 0.55, base, span)),
                              cancel_check)

            size = os.path.getsize(rpath)
            rounds.append((size, rpath, f, c, w))
            if target is None or size <= target or len(rounds) >= 4:
                break

            # 按比例跳档：GIF 体积 ≈ ∝ 帧率 ∝ 像素量，各分担 √r；颜色影响弱，更激进
            ratio = size / target
            nf = _pick_ladder(fps_l, f, f / math.sqrt(ratio))
            nc = _pick_ladder(colors_l, c, c / max(1.0, ratio))
            nw = _pick_ladder(width_l, w, w / math.sqrt(ratio))
            if (nf, nc, nw) == (f, c, w):      # 三项都已到下限
                break
            cur = (nf, nc, nw)

        if target is not None and all(r[0] > target for r in rounds):
            best = min(rounds, key=lambda r: r[0])     # 到下限仍超：取最小一轮
        else:
            best = rounds[-1]
        bsize, bpath, bf, bc, bw = best
        if bpath != out_path:
            os.replace(bpath, out_path)
        applied = {"fps": bf, "colors": bc, "width": bw, "dither": dither,
                   "deinterlace": need_deint, "bytes": bsize,
                   "target_hit": target is None or bsize <= target,
                   "adjusted": target is not None and (bf, bc, bw) != (fps_l[0], colors_l[0], width_l[0])}
        if progress:
            progress(1.0)
        return out_path, applied
    finally:
        try:
            os.remove(tmp_pal)
        except OSError:
            pass
        for r in rounds:
            if r[1] != out_path and os.path.isfile(r[1]):
                try:
                    os.remove(r[1])
                except OSError:
                    pass


def extract_frame(video, t, out_png, width=None, deinterlace=False):
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    args = ["-y", "-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1"]
    chain = ",".join(filter(None, ("yadif=0:-1:0" if deinterlace else "",
                                   f"scale={width}:-1:flags=lanczos" if width else "")))
    if chain:
        args += ["-vf", chain]
    args.append(out_png)
    p = _run([ffmpeg, "-hide_banner", "-loglevel", "error", *args], timeout=120)
    if p.returncode != 0 or not os.path.isfile(out_png):
        raise FfmpegError("取帧失败: " + (p.stderr or "").strip()[-400:])
    return out_png


def extract_frames(video, out_dir, start=0.0, duration=None, crop=None,
                   width=480, fps=12, quality="3", deinterlace=False):
    """按当前裁剪/宽度/fps 抽取选段帧到 out_dir/00001.jpg…，返回帧路径列表。"""
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    os.makedirs(out_dir, exist_ok=True)
    args = ["-y", "-ss", f"{max(0.0, start):.3f}"]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-i", video,
             "-vf", build_chain(crop, width, fps, deinterlace=deinterlace),
             "-q:v", quality, os.path.join(out_dir, "%05d.jpg")]
    p = _run([ffmpeg, "-hide_banner", "-loglevel", "error", *args], timeout=180)
    if p.returncode != 0:
        raise FfmpegError("抽取预览帧失败: " + (p.stderr or "").strip()[-400:])
    return sorted(glob.glob(os.path.join(out_dir, "*.jpg")))


def estimate_gif_size_probe(video, start=0.0, duration=None, crop=None,
                            width=720, fps=12, colors=128, dither="bayer",
                            deinterlace="auto", probe_seconds=1.0,
                            cancel_check=None):
    """试编外推估算：按完整参数实际编码选段开头 probe_seconds 秒，线性外推全段体积。

    选段本身 ≤ probe_seconds 时直接编全段（结果近似精确值）。
    返回 (外推字节数, 实际试编时长)。
    """
    info = probe(video)
    total = info["duration"] or 0
    if duration is None:
        duration = max(0.0, total - start) if total else None
    if not duration:
        duration = probe_seconds
    probe_dur = min(duration, probe_seconds)
    fd, tmp = tempfile.mkstemp(prefix="gifkit_est_", suffix=".gif")
    os.close(fd)
    try:
        _, applied = make_gif(video, tmp, start=start, duration=probe_dur,
                              crop=crop, width=width, fps=fps, colors=colors,
                              dither=dither, deinterlace=deinterlace,
                              cancel_check=cancel_check)
        est = applied["bytes"] / probe_dur * duration
        return int(est), probe_dur
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def extract_thumbs(video, count=8, out_dir=None, width=192):
    """均匀抽 count 张缩略图，返回 [(时间, 路径), ...]。"""
    total = probe(video)["duration"]
    if total <= 0:
        return []
    out_dir = out_dir or tempfile.mkdtemp(prefix="gifkit_thumbs_")
    os.makedirs(out_dir, exist_ok=True)
    thumbs = []
    for i in range(count):
        t = total * (i + 0.5) / count
        p = os.path.join(out_dir, f"thumb_{i:02d}.jpg")
        try:
            extract_frame(video, t, p, width=width)
        except FfmpegError:
            continue
        thumbs.append((t, p))
    return thumbs


def output_dims(src_w, src_h, crop, width):
    """计算输出分辨率：width=0 表示保持原始宽度；高度自适应保留奇数。"""
    w0 = crop[2] if crop else src_w
    h0 = crop[3] if crop else src_h
    w = width or w0
    h = max(1, round(h0 * w / w0))
    return int(w), int(h)


def estimate_gif_size(w, h, fps, dur, colors=128, dither="bayer"):
    """粗略体积估算（±40% 量级），仅用于选参数参考。"""
    base = {"bayer": 0.10, "floyd": 0.13, "none": 0.08}.get(dither, 0.10)
    cf = 0.65 + 0.35 * (min(colors, 256) / 256.0)
    return int(w * h * fps * max(0.0, dur) * base * cf)
