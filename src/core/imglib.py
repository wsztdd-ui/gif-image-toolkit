"""图片压缩与格式转换。纯逻辑层，仅依赖 Pillow。"""
import os

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 200_000_000


def target_kind(src: str, fmt: str) -> str:
    """fmt ∈ {keep,jpeg,webp,png} → 实际输出格式。BMP/TIFF/GIF(静) 在 keep 下转 PNG。"""
    if fmt != "keep":
        return fmt
    ext = os.path.splitext(src)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "jpeg"
    if ext == ".webp":
        return "webp"
    return "png"


EXT_BY_KIND = {"jpeg": ".jpg", "webp": ".webp", "png": ".png"}


def _shrink(img, max_edge):
    if max_edge and max_edge > 0:
        w, h = img.size
        longest = max(w, h)
        if longest > max_edge:
            scale = max_edge / longest
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                             Image.LANCZOS)
    return img


def _save_jpeg(img, dst, quality):
    if img.mode not in ("RGB", "L", "CMYK", "1"):
        img = img.convert("RGB")    # I;16/F/PA 等模式 JPEG 写不了，统一转 RGB
    img.save(dst, "JPEG", quality=int(quality), optimize=True, progressive=True)


def _save_webp(img, dst, quality):
    if img.mode in ("CMYK", "I", "I;16", "F", "1"):
        img = img.convert("RGB")
    elif img.mode in ("RGBa", "PA"):
        img = img.convert("RGBA")
    elif img.mode == "La":          # Pillow 预乘模式，只能转回 LA
        img = img.convert("LA")
    img.save(dst, "WEBP", quality=int(quality), method=6)


def _save_png(img, dst, quantize):
    if img.mode in ("CMYK", "F"):   # Pillow 写不了 CMYK/F 的 PNG，先转 RGB
        img = img.convert("RGB")
    if img.mode == "P":
        img.save(dst, "PNG", optimize=True)
    elif quantize and img.mode in ("RGB", "L"):
        img.quantize(colors=256).save(dst, "PNG", optimize=True)
    elif quantize and img.mode in ("RGBA", "LA"):
        img.convert("RGBA").quantize(colors=256, method=Image.FASTOCTREE)\
            .save(dst, "PNG", optimize=True)
    else:
        img.save(dst, "PNG", optimize=True)


def compress_one(src, dst, fmt="keep", quality=80, max_edge=0, quantize_png=True):
    """压缩/转换单张图片，返回 (原大小, 新大小, 实际格式)。"""
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    img = _shrink(img, max_edge)
    kind = target_kind(src, fmt)
    if kind == "jpeg":
        _save_jpeg(img, dst, quality)
    elif kind == "webp":
        _save_webp(img, dst, quality)
    else:
        _save_png(img, dst, quantize_png)
    return os.path.getsize(src), os.path.getsize(dst), kind
