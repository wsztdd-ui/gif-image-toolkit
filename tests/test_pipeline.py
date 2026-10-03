"""无界面冒烟测试：生成测试视频 → 完整 GIF 两遍管线 → 动图再压缩 → 图片压缩。

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
          f"{info['fps']:.1f}fps {info['codec']}")

    # 2) 视频截取 GIF（默认参数：720 宽，16:9 → 720x405，裁剪全画面）
    out1 = os.path.join(tmp, "out_720.gif")
    ff.make_gif(src, out1, start=0.5, duration=2.0, crop=None, width=720,
                fps=12, colors=128, dither="bayer",
                progress=lambda p: print(f"\r  生成中 {int(p*100)}%", end=""))
    print(f"\nGIF(视频截取): {os.path.getsize(out1)} bytes")

    # 3) 带裁剪
    out2 = os.path.join(tmp, "out_crop.gif")
    ff.make_gif(src, out2, start=0.0, duration=1.0,
                crop=(160, 90, 960, 540), width=480, fps=10, colors=64, dither="floyd",
                progress=lambda p: None)
    print(f"GIF(带裁剪): {os.path.getsize(out2)} bytes")

    # 4) 动图 GIF 再压缩：先把 out1 当输入再压一遍
    out3 = os.path.join(tmp, "out_re.gif")
    ff.make_gif(out1, out3, start=0.0, duration=None, crop=None, width=480,
                fps=8, colors=64, dither="none", progress=lambda p: None)
    print(f"GIF(再压缩 {os.path.getsize(out1)} -> {os.path.getsize(out3)} bytes)")

    # 5) 图片压缩
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
