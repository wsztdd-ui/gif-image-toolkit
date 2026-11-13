"""整窗冒烟：MainWindow 完整构建（主题/字体/两页签/配置加载）→ shutdown → 关闭。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from main import apply_theme                # noqa: E402
from ui.main_window import MainWindow       # noqa: E402
from utils.config import Config             # noqa: E402

app = QApplication([])
apply_theme(app)
win = MainWindow(Config())
win.resize(1120, 740)
app.processEvents()
ok = (win.tabs.count() == 2
      and win.gif_tab is not None and win.img_tab is not None
      and "GifKit" in win.windowTitle())
print("窗口标题:", win.windowTitle())
print("页签:", [win.tabs.tabText(i) for i in range(win.tabs.count())])
win.gif_tab.shutdown()
win.img_tab.shutdown()
win.close()
print("MAINWINDOW SMOKE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
