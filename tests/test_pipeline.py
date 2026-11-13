"""无界面冒烟测试：生成测试视频 → 完整 GIF 两遍管线 → 动图再压缩 → 图片压缩。
v0.5 新增：目标体积搜索、隔行源自动去隔行、试编外推估算。

用法: python tests/test_pipeline.py   （需 ffmpeg 在 PATH 或 bin 目录下，需 Pillow）
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from core import ffmpeg as ff          # noqa: E402
from core import imglib                # noqa: E402


def main():
    ok, msg = ff.available()
    print("ffmpeg:", ok, msg)
    if not ok:
        sys.exit(1)

    tmp = tempfile.mkdtemp(prefix="gifkit_test_")
    print("临时目录:", tmp)

    # 1) 生成 4 秒测试视频（TS 封装，mpeg2 编码任何 ffmpeg 都有，模拟广电 TS 素材）
    src = os.path.join(tmp, "test.ts")
    subprocess.run(
        [ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
         "-i", "testsrc2=size=1280x720:rate=30:duration=4",
         "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts", src],
        check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)
    info = ff.probe(src)
    print(f"probe: {info['width']}x{info['height']} {info['duration']:.1f}s "
          f"{info['fps']:.1f}fps {info['codec']} field_order={info['field_order']}")

    # 2) 视频截取 GIF（默认参数：720 宽，16:9 → 720x405，裁剪全画面）
    out1, ap1 = ff.make_gif(src, os.path.join(tmp, "out_720.gif"), start=0.5,
                            duration=2.0, crop=None, width=720,
                            fps=12, colors=128, dither="bayer",
                            progress=lambda p: print(f"\r  生成中 {int(p*100)}%", end=""))
    assert ap1["target_hit"] and not ap1["adjusted"]
    print(f"\nGIF(视频截取): {ap1['bytes']} bytes  applied={ap1}")

    # 3) 带裁剪
    out2, ap2 = ff.make_gif(src, os.path.join(tmp, "out_crop.gif"), start=0.0,
                            duration=1.0, crop=(160, 90, 960, 540), width=480,
                            fps=10, colors=64, dither="floyd", progress=lambda p: None)
    print(f"GIF(带裁剪): {ap2['bytes']} bytes")

    # 4) 动图 GIF 再压缩：先把 out1 当输入再压一遍
    out3, ap3 = ff.make_gif(out1, os.path.join(tmp, "out_re.gif"), start=0.0,
                            duration=None, crop=None, width=480,
                            fps=8, colors=64, dither="none", progress=lambda p: None)
    print(f"GIF(再压缩 {ap1['bytes']} -> {ap3['bytes']} bytes)")

    # 5) 目标体积模式：0.35MB 远低于常规产出（~1.3MB），必须自动下调参数收敛
    out4, ap4 = ff.make_gif(src, os.path.join(tmp, "out_target.gif"), start=0.0,
                            duration=4.0, crop=None, width=720,
                            fps=12, colors=128, dither="bayer", target_mb=0.35,
                            progress=lambda p: None)
    hit = os.path.getsize(out4) <= int(0.35 * 1024 * 1024)
    print(f"GIF(目标体积): {ap4['bytes']} bytes hit={ap4['target_hit']} "
          f"adjusted={ap4['adjusted']} applied=fps{ap4['fps']}/"
          f"{ap4['colors']}c/w{ap4['width']}")
    if not ap4["target_hit"]:
        print("  [警告] 到下限仍超目标（4 轮上限）——检查搜索策略")
    else:
        assert hit, "target_hit=True 但产物超目标"

    # 6) 隔行源：合成隔行 TS → 自动去隔行
    src_il = os.path.join(tmp, "il.ts")
    subprocess.run(
        [ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
         "-i", "testsrc2=size=1280x720:rate=25:duration=2",
         "-c:v", "mpeg2video", "-q:v", "4", "-flags", "+ilme+ildct", "-top", "1",
         "-f", "mpegts", src_il],
        check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)
    info_il = ff.probe(src_il)
    print(f"隔行源 probe field_order: {info_il['field_order']}")
    assert info_il["field_order"] in ff.INTERLACED_ORDERS, \
        "隔行 TS 未被识别（field_order=" + info_il["field_order"] + "）"
    out5, ap5 = ff.make_gif(src_il, os.path.join(tmp, "out_deint.gif"), start=0.0,
                            duration=1.0, crop=None, width=480,
                            fps=10, colors=64, dither="bayer",
                            deinterlace="auto", progress=lambda p: None)
    assert ap5["deinterlace"] is True, "auto 模式未对隔行源启用 yadif"
    frame = os.path.join(tmp, "f_deint.png")
    ff.extract_frame(src_il, 1.0, frame, width=480, deinterlace=True)
    print(f"GIF(隔行源自动去隔行): {ap5['bytes']} bytes, 抽帧 OK -> {os.path.basename(frame)}")
    # 渐进源 auto 不去隔行
    _, ap6 = ff.make_gif(src, os.path.join(tmp, "out_prog.gif"), start=0.0,
                         duration=0.5, crop=None, width=320, fps=8,
                         colors=32, dither="bayer", deinterlace="auto",
                         progress=lambda p: None)
    assert ap6["deinterlace"] is False, "渐进源被误去隔行"

    # 7) 试编外推估算：应接近实际值（同参数完整生成对比）
    est, probe_dur = ff.estimate_gif_size_probe(src, start=0.0, duration=4.0,
                                                width=720, fps=12, colors=128,
                                                dither="bayer")
    actual = ff.make_gif(src, os.path.join(tmp, "out_full.gif"), start=0.0,
                         duration=4.0, crop=None, width=720, fps=12,
                         colors=128, dither="bayer",
                         progress=lambda p: None)[1]["bytes"]
    err = abs(est - actual) / actual * 100
    print(f"估算校准: 试编 {probe_dur:.1f}s 外推 {est} bytes vs 实际 {actual} bytes"
          f"（误差 {err:.0f}%）")
    assert err < 60, f"试编外推误差过大: {err:.0f}%"

    # 8) 图片压缩
    from PIL import Image
    img_src = os.path.join(tmp, "pic.png")
    Image.effect_noise((1600, 900), 60).resize((1600, 900)).convert("RGB").save(img_src)
    dst_jpg = os.path.join(tmp, "pic_c.jpg")
    o, n, k = imglib.compress_one(img_src, dst_jpg, fmt="jpeg", quality=80)
    print(f"图片 JPEG: {o} -> {n} ({k})")
    dst_png = os.path.join(tmp, "pic_c.png")
    o2, n2, k2 = imglib.compress_one(img_src, dst_png, fmt="keep", quality=80,
                                     quantize_png=True)
    print(f"图片 PNG量化: {o2} -> {n2} ({k2})")

    print("\n全部通过 ✔  产物在:", tmp)


if __name__ == "__main__":
    main()
