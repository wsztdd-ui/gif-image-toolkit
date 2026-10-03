# -*- mode: python ; coding: utf-8 -*-
r"""GifKit macOS .app 打包配置。用法: pyinstaller build/gifkit_mac.spec（需先有 build/icon.icns）"""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")


def ff_binaries():
    """ffmpeg 放 binaries 而非 datas：打包后保留可执行位。"""
    out = []
    for name in ("ffmpeg", "ffprobe"):
        p = os.path.join(ROOT, "bin", name)
        if os.path.isfile(p):
            out.append((p, "bin"))
    return out


datas = []
fonts_dir = os.path.join(ROOT, "fonts")
if os.path.isdir(fonts_dir):
    for f in os.listdir(fonts_dir):
        if f.lower().endswith((".otf", ".ttf")):
            datas.append((os.path.join(fonts_dir, f), "fonts"))

icns = os.path.join(ROOT, "build", "icon.icns")
a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=ff_binaries(),
    datas=datas,
    hiddenimports=[],
    excludes=["tkinter", "matplotlib", "numpy"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GifKit",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="GifKit",
)

app = BUNDLE(
    coll,
    name="GifKit.app",
    icon=icns if os.path.isfile(icns) else None,
    bundle_identifier="io.github.wsztdd-ui.gifkit",
)
