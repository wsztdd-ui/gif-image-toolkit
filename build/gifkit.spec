# -*- mode: python ; coding: utf-8 -*-
r"""GifKit 单文件绿色版打包配置。用法: pyinstaller build\gifkit.spec"""
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
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GifKit",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)
