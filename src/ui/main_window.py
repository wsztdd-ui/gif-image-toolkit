"""主窗口：两个页签 + 状态栏 + 设置持久化。"""
import base64

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

from core import ffmpeg as ff
from ui.gif_tab import GifTab
from ui.image_tab import ImageTab
from utils.config import APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(f"GifKit — GIF截取 & 图片压缩  v{APP_VERSION}")

        self.tabs = QTabWidget()
        self.gif_tab = GifTab(cfg.data["gif"])
        self.img_tab = ImageTab(cfg.data["img"])
        self.gif_tab.imageDropped.connect(self._on_image_dropped)
        self.tabs.addTab(self.gif_tab, "视频转 GIF")
        self.tabs.addTab(self.img_tab, "图片压缩")
        self.setCentralWidget(self.tabs)

        ok, msg = ff.available()
        tip = "已检测到 ffmpeg" if ok else msg
        status = QLabel(tip)
        status.setStyleSheet("color:#0e700e;" if ok else "color:#c50f1f; padding:0 8px;")
        self.statusBar().addWidget(status)
        ver = QLabel(f"v{APP_VERSION} 绿色便携版 · 设置保存在程序目录")
        self.statusBar().addPermanentWidget(ver)

        geom = cfg.data.get("win", {}).get("geom")
        if geom:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geom.encode()))
            except Exception:  # noqa: BLE001
                pass

    def _on_image_dropped(self, path):
        self.tabs.setCurrentIndex(1)
        self.img_tab.add_files([path])

    def closeEvent(self, e):
        # 两页是子页签，各自的 closeEvent 不会触发，必须在这里显式收尾
        self.gif_tab.shutdown()
        self.img_tab.shutdown()
        self.gif_tab.save_settings()
        self.img_tab.save_settings()
        self.cfg.data.setdefault("win", {})["geom"] = \
            base64.b64encode(bytes(self.saveGeometry())).decode()
        self.cfg.save()
        super().closeEvent(e)
