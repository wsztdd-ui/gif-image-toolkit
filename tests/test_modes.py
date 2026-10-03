"""imglib 特殊像素模式单测：I;16 / F / CMYK / PA → JPEG / WebP / PNG 不崩溃。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PIL import Image                     # noqa: E402
from core import imglib                   # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="gifkit_modes_")
    sources = {}
    Image.new("I;16", (64, 48)).save(p16 := os.path.join(tmp, "p16.png"))
    sources["I;16"] = p16
    Image.new("F", (64, 48)).save(pf := os.path.join(tmp, "pf.tif"))
    sources["F"] = pf
    Image.new("CMYK", (64, 48)).save(pc := os.path.join(tmp, "pc.tif"))
    sources["CMYK"] = pc
    Image.new("LA", (64, 48)).save(pla := os.path.join(tmp, "pla.png"))
    sources["LA"] = pla
    ext = {"jpeg": ".jpg", "webp": ".webp", "png": ".png"}
    for mode, src in sources.items():
        for fmt in ("jpeg", "webp", "png"):
            dst = os.path.join(tmp, f"out_{mode}_{fmt}{ext[fmt]}")
            o, n, k = imglib.compress_one(src, dst, fmt=fmt, quality=80)
            print(f"{mode:5s} -> {fmt:4s} ({k}) OK, {n} bytes")
    # PA/RGBa 无法存成常规文件，直接在内存里测 _save_webp 的转换分支
    for mode in ("PA", "RGBa", "La"):
        im = Image.new("RGBA", (64, 48)).convert(mode)
        dst = os.path.join(tmp, f"mem_{mode}.webp")
        imglib._save_webp(im, dst, 80)
        print(f"{mode:5s} -> webp OK, {os.path.getsize(dst)} bytes")
    print("ALL MODES OK")


if __name__ == "__main__":
    main()
