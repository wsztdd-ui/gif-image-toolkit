"""保存链路回归测试：预览动画占用文件时点“保存”，必须先释放句柄再移动（WinError 32）。

背景：QMovie.stop()/setMovie(None) 都不会关闭内部 QFile（Qt 6.11 实测），
必须显式 movie.device().close()，否则 Windows 下 move 预览文件必报 WinError 32。

场景 A（修复路径）：jumpToFrame(0) 强制 QMovie 打开文件并确认占用 → 保存必须成功。
场景 B（阴性对照）：屏蔽释放逻辑 → 保存必须复现“保存失败”。
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QMovie            # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import ffmpeg as ff               # noqa: E402
from ui.gif_tab import GifTab               # noqa: E402


def make_gif(path):
    subprocess.run(
        [ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
         "-i", "testsrc2=size=480x270:rate=15:duration=5", "-loop", "0", path],
        check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)


def is_locked(path):
    try:
        os.rename(path, path + ".t")
        os.rename(path + ".t", path)
        return False
    except OSError:
        return True


def setup_scene(app, scene_dir, disable_release=False):
    """搭好“生成完成、动画已打开文件”的状态，返回 (tab, preview_file)。"""
    os.makedirs(scene_dir, exist_ok=True)
    gif = os.path.join(scene_dir, "a.gif")
    make_gif(gif)
    preview_dir = os.path.join(scene_dir, "GifKit_preview")
    os.makedirs(preview_dir, exist_ok=True)
    preview_file = os.path.join(preview_dir, "a_gif.gif")
    shutil.copy(gif, preview_file)

    tab = GifTab({})
    tab.video = gif
    tab.radio_src.setChecked(True)
    movie = QMovie(preview_file)
    tab.preview_label.setMovie(movie)
    tab._movie = movie
    tab.preview_stack.setCurrentIndex(1)
    tab.btn_save.setVisible(True)
    tab._preview_file = preview_file
    assert movie.jumpToFrame(0), "QMovie 未能打开测试 GIF"
    assert is_locked(preview_file), "QMovie 未持有文件句柄，测试前提不成立"
    if disable_release:
        tab._release_movie = lambda: None      # 阴性对照：屏蔽修复
    return tab, preview_file


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="gifkit_save_")

    # 场景 B（阴性对照）：不释放句柄直接保存 → 预期复现“保存失败”
    tab_b, _ = setup_scene(app, os.path.join(tmp, "b"), disable_release=True)
    tab_b._save_preview()
    control_reproduced = tab_b.status.text().startswith("保存失败")
    print("  对照组:", tab_b.status.text())

    # 场景 A（修复路径）：必须保存成功
    tab_a, pf_a = setup_scene(app, os.path.join(tmp, "a"))
    tab_a._save_preview()
    for _ in range(5):
        app.processEvents()
    print("  正常组:", tab_a.status.text())
    dst_a = os.path.join(tmp, "a", "a_gif.gif")
    saved = os.path.isfile(dst_a) and os.path.getsize(dst_a) > 0
    gone = not os.path.exists(pf_a)
    released = tab_a._movie is None and tab_a.preview_label.movie() is None
    print("  保存成功:", saved, "| 临时产物已移走:", gone, "| 动画已释放:", released)

    ok = saved and gone and released and control_reproduced
    print("MOVIE RELEASE TEST",
          "PASS" if ok else "FAIL",
          f"(对照组复现原始bug: {control_reproduced})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
