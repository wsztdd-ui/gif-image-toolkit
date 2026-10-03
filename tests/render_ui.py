"""离屏渲染主窗口并截图，用于验证 UI 主题与布局（不弹窗口）。"""
import os
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
out2 = os.path.join(ROOT, "build", "ui_preview_play.png")
win.grab().save(out2)
print("playing     : live =", win.gif_tab.preview.is_live(),
      "| btn =", win.gif_tab.btn_play.text(), "->", out2)

# 3) 点击画面 → 回编辑模式，设裁剪框
win.gif_tab._stop_playback()
settle(app, 2500)
win.gif_tab.preview.set_crop(QRect(160, 90, 960, 540))
settle(app, 1500)
out = os.path.join(ROOT, "build", "ui_preview_gif.png")
win.grab().save(out)
print("edit mode   : live =", win.gif_tab.preview.is_live(),
      "| btn =", win.gif_tab.btn_play.text(), "->", out)

# 4) 图片页
win.tabs.setCurrentIndex(1)
settle(app, 300)
win.grab().save(os.path.join(ROOT, "build", "ui_preview_img.png"))
print("img page saved")
