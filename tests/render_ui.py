"""离屏渲染主窗口并截图，用于验证 UI 主题与布局（不弹窗口）。"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from core import ffmpeg as ff
from main import apply_theme
from ui.main_window import MainWindow
from utils.config import Config


def settle(app, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.03)


app = QApplication([])
apply_theme(app)
win = MainWindow(Config())
win.resize(1120, 760)
win.show()

BUILD_DIR = os.path.join(ROOT, "build")
os.makedirs(BUILD_DIR, exist_ok=True)   # .gitignore 只忽略内容，目录本身可能不存在


def shot(app, path):
    """截图并检查返回值（win.grab().save() 失败不抛异常，静默返回 False）。"""
    ok = win.grab().save(path)
    print("  screenshot:", os.path.basename(path), "ok" if ok else "FAILED")
    return ok

tmp = tempfile.mkdtemp(prefix="gifkit_ui_")
ts = os.path.join(tmp, "demo.ts")
subprocess.run([ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
                "-i", "testsrc2=size=1280x720:rate=30:duration=6",
                "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts", ts],
               check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)

# 1) 载入 → 静态帧（不自动播放）
win.gif_tab.load_path(ts)
settle(app, 5000)
print("after load  : live =", win.gif_tab.preview.is_live(),
      "| btn =", win.gif_tab.btn_play.text())

# 2) 点“▶ 播放选段” → 播放
win.gif_tab.btn_play.click()
settle(app, 6000)
out2 = os.path.join(BUILD_DIR, "ui_preview_play.png")
shot(app, out2)
print("playing     : live =", win.gif_tab.preview.is_live(),
      "| btn =", win.gif_tab.btn_play.text(), "->", out2)

# 3) 点击画面 → 回编辑模式，设裁剪框
win.gif_tab._stop_playback()
settle(app, 2500)
win.gif_tab.preview.set_crop(QRect(160, 90, 960, 540))
settle(app, 1500)
out = os.path.join(BUILD_DIR, "ui_preview_gif.png")
shot(app, out)
print("edit mode   : live =", win.gif_tab.preview.is_live(),
      "| btn =", win.gif_tab.btn_play.text(), "->", out)

# 4) 图片页
win.tabs.setCurrentIndex(1)
settle(app, 300)
shot(app, os.path.join(BUILD_DIR, "ui_preview_img.png"))
print("img page saved")

# 收尾：等后台线程跑完再退出，否则 QThread 带线程销毁会 0xC0000409
win.gif_tab.shutdown()
win.img_tab.shutdown()
# QApplication 存活期间销毁残留顶层控件，防解释器退出阶段段错误（CI 实测）
for w in list(QApplication.topLevelWidgets()):
    w.deleteLater()
for _ in range(2):
    app.processEvents()
    time.sleep(0.03)
shutil.rmtree(tmp, ignore_errors=True)
