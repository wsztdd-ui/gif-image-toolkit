# -*- mode: python ; coding: utf-8 -*-
r"""GifKit 文件夹绿色版打包配置（启动更快）。用法: pyinstaller build\gifkit_onedir.spec"""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

datas = []
for name in ("ffmpeg.exe", "ffprobe.exe"):
    p = os.path.join(ROOT, "bin", name)
    if os.path.isfile(p):
        datas.append((p, "bin"))
fonts_dir = os.path.join(ROOT, "fonts")
if os.path.isdir(fonts_dir):
    for f in os.listdir(fonts_dir):
        if f.lower().endswith((".otf", ".ttf")):
            datas.append((os.path.join(fonts_dir, f), "fonts"))

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=[],
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
