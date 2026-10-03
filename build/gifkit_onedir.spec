# -*- mode: python ; coding: utf-8 -*-
r"""GifKit 文件夹绿色版打包配置（Windows / Linux）。用法: pyinstaller build/gifkit_onedir.spec"""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")


def ff_binaries():
    """ffmpeg 放 binaries 而非 datas：打包后保留可执行位（跨平台通用）。"""
    out = []
    names = ("ffmpeg.exe", "ffprobe.exe") if os.name == "nt" else ("ffmpeg", "ffprobe")
    for name in names:
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

icon = os.path.join(ROOT, "build", "icon.ico")
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
    icon=icon if os.name == "nt" and os.path.isfile(icon) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="GifKit",
)
