"""文件路径辅助。"""
import os
import subprocess


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
    """在资源管理器中打开目录（或选中文件）。"""
    if not path:
        return
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        os.startfile(os.path.normpath(path))  # noqa: S606
