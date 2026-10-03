"""文件路径辅助。"""
import os
import subprocess
import sys


def unique_path(dst: str) -> str:
    """目标路径已存在时追加 " (2)"、" (3)" … 防覆盖。"""
    if not os.path.exists(dst):
        return dst
    base, ext = os.path.splitext(dst)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def open_in_explorer(path: str):
    """在系统文件管理器中打开目录（或选中文件）。Windows 为主，
    macOS/Linux 源码运行时回退到 Finder / 文件管理器。"""
    if not path:
        return
    path = os.path.normpath(path)
    if sys.platform == "win32":
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        if os.path.isfile(path):
            subprocess.Popen(["open", "-R", path])      # Finder 中显示该文件
        else:
            subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)
                          if os.path.isfile(path) else path])  # noqa: S606
