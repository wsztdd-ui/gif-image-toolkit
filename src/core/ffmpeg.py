"""ffmpeg / ffprobe 封装与 GIF 两遍调色板生成。纯逻辑层，不依赖 Qt，可独立测试。"""
import glob
import json
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
        exe_dir = os.path.dirname(sys.executable)
        dirs.append(exe_dir)
        dirs.append(os.path.join(exe_dir, "_internal"))   # PyInstaller 6 onedir 数据目录
        dirs.append(os.path.join(exe_dir, "..", "Frameworks"))  # macOS .app 结构
        dirs.append(os.path.join(exe_dir, "..", "Frameworks", "_internal"))
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
        "frames": int(vs["nb_frames"]) if str(vs.get("nb_frames", "")).isdigit() else 0,
        "size": size,
    }


_TIME_RE = re.compile(r"^out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def run_with_progress(args, duration, progress=None, cancel_check=None):
    """执行 ffmpeg 并从 -progress pipe:1 解析 out_time= 汇报 0~1 进度。

    进度行由独立线程读取（ffmpeg 卡住不输出时主流程不被读阻塞）；
    主流程每 0.2s 轮询一次 cancel_check，取消立即杀死子进程并抛 FfmpegCancelled；
    任何异常退出路径都会杀掉残留的 ffmpeg 进程，避免孤儿进程。
    """
    import threading

    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error",
           "-progress", "pipe:1", *args]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=CREATE_NO_WINDOW)
        pump_err = []

        def _pump():
            last = 0.0
            try:
                for line in proc.stdout:
                    m = _TIME_RE.match(line.strip())
                    if m and duration > 0 and progress:
                        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                        last = max(last, t / duration)
                        progress(min(0.999, last))
            except BaseException as e:  # progress 回调抛出的取消等异常，主流程统一处理
                pump_err.append(e)

        reader = threading.Thread(target=_pump, daemon=True)
        reader.start()
        try:
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_check is not None and cancel_check():
                        raise FfmpegCancelled("已取消")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            reader.join(timeout=1)
        errf.seek(0)
        stderr = errf.read() or ""
    if pump_err:
        raise pump_err[0]
    if proc.returncode != 0:
        raise FfmpegError("ffmpeg 执行失败: " + stderr.strip()[-800:])


def build_chain(crop, width, fps):
    """滤镜链：crop(可选) → scale(可选，高度自适应保留奇数) → fps。"""
    parts = []
    if crop:
        x, y, w, h = crop
        parts.append(f"crop={w}:{h}:{x}:{y}")
    if width:
        parts.append(f"scale={width}:-1:flags=lanczos")
    parts.append(f"fps={fps}")
    return ",".join(parts)


def make_gif(video, out_path, start=0.0, duration=None, crop=None, width=720,
             fps=12, colors=128, dither="bayer", progress=None, cancel_check=None):
    """两遍调色板法生成 GIF。video 也可以是 .gif（动图再压缩）。"""
    info = probe(video)
    total = info["duration"] or 0
    if duration is None:
        duration = max(0.0, total - start) if total else None
    seg = duration or (max(0.0, total - start) if total else 0)
    chain = build_chain(crop, width, fps)
    if progress:
        progress(0.0)

    tmp_pal = os.path.join(tempfile.gettempdir(),
                           f"gifkit_{os.getpid()}_palette.png")
    try:
        seg_args = ["-ss", f"{max(0.0, start):.3f}"]
        if duration:
            seg_args += ["-t", f"{duration:.3f}"]
        seg_args += ["-i", video]

        pass1 = [*seg_args, "-vf", f"{chain},palettegen=max_colors={colors}:stats_mode=diff",
                 "-update", "1", "-y", tmp_pal]
        run_with_progress(pass1, seg, (lambda p: progress(p * 0.45)) if progress else None,
                          cancel_check)

        d = DITHER_MAP.get(dither, dither)
        fc = f"[0:v]{chain}[v];[v][1:v]paletteuse=dither={d}[out]"
        pass2 = [*seg_args, "-i", tmp_pal, "-filter_complex", fc,
                 "-map", "[out]", "-loop", "0", "-y", out_path]
        run_with_progress(pass2, seg, (lambda p: progress(0.45 + p * 0.55)) if progress else None,
                          cancel_check)
    finally:
        try:
            os.remove(tmp_pal)
        except OSError:
            pass
    return out_path


def extract_frame(video, t, out_png, width=None):
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    args = ["-y", "-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1"]
    if width:
        args += ["-vf", f"scale={width}:-1:flags=lanczos"]
    args.append(out_png)
    p = _run([ffmpeg, "-hide_banner", "-loglevel", "error", *args], timeout=120)
    if p.returncode != 0 or not os.path.isfile(out_png):
        raise FfmpegError("取帧失败: " + (p.stderr or "").strip()[-400:])
    return out_png


def extract_frames(video, out_dir, start=0.0, duration=None, crop=None,
                   width=480, fps=12, quality="3"):
    """按当前裁剪/宽度/fps 抽取选段帧到 out_dir/00001.jpg…，返回帧路径列表。"""
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        raise FfmpegError("未找到 ffmpeg")
    os.makedirs(out_dir, exist_ok=True)
    args = ["-y", "-ss", f"{max(0.0, start):.3f}"]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-i", video, "-vf", build_chain(crop, width, fps),
             "-q:v", quality, os.path.join(out_dir, "%05d.jpg")]
    p = _run([ffmpeg, "-hide_banner", "-loglevel", "error", *args], timeout=180)
    if p.returncode != 0:
        raise FfmpegError("抽取预览帧失败: " + (p.stderr or "").strip()[-400:])
    return sorted(glob.glob(os.path.join(out_dir, "*.jpg")))


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
    w0 = max(1, int(w0 or 1))       # 损坏文件探不到宽高时避免除零
    h0 = max(1, int(h0 or 1))
    w = width or w0
    h = max(1, round(h0 * w / w0))
    return int(w), int(h)


def estimate_gif_size(w, h, fps, dur, colors=128, dither="bayer"):
    """粗略体积估算（±40% 量级），仅用于选参数参考。"""
    base = {"bayer": 0.10, "floyd": 0.13, "none": 0.08}.get(dither, 0.10)
    cf = 0.65 + 0.35 * (min(colors, 256) / 256.0)
    return int(w * h * fps * max(0.0, dur) * base * cf)
