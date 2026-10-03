"""生成 GifKit 应用图标：build/icon.png（512）与 build/icon.ico。

仅在构建机上需要运行（build.sh / CI 会自动调用）；icns 由 macOS 的
sips + iconutil 从 icon.png 现场生成，不随仓库存二进制。
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
os.makedirs(BUILD, exist_ok=True)

SIZE = 512


def rounded_gradient(size, radius, top, bottom):
    """圆角矩形 + 垂直渐变（用 1px 行模拟线性渐变再蒙圆角）。"""
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    img = grad.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    img = rounded_gradient(SIZE, 112, (30, 132, 216), (12, 59, 94))  # Fluent 蓝

    d = ImageDraw.Draw(img)
    # 胶片齿孔：上下两条半透明白条
    for y0, h in ((36, 34), (SIZE - 70, 34)):
        d.rounded_rectangle([64, y0, SIZE - 64, y0 + h], radius=10, fill=(255, 255, 255, 56))
        for i in range(6):
            x = 96 + i * ((SIZE - 192 - 44) // 5)
            d.rounded_rectangle([x, y0 + 9, x + 44, y0 + h - 9], radius=7,
                                fill=(255, 255, 255, 120))

    # 主体文字 GIF
    font = None
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.isfile(p):
            try:
                font = ImageFont.truetype(p, 200)
                break
            except OSError:
                continue
    if font is None:                       # 兜底：默认位图字体放大
        font = ImageFont.load_default()
    text = "GIF"
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((SIZE - w) / 2 - bbox[0], (SIZE - h) / 2 - bbox[1] - 6), text,
           font=font, fill=(255, 255, 255, 255))

    png = os.path.join(BUILD, "icon.png")
    img.save(png)
    img.save(os.path.join(BUILD, "icon.ico"),
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("已生成", png)


if __name__ == "__main__":
    main()
