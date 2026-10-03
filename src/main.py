"""GifKit 入口。主题：Microsoft Fluent 2 浅色（品牌蓝 #0F6CBD），思源黑体 Medium。"""
import os
import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.config import Config, APP_VERSION

# Fluent 2 tokens（https://fluent2.microsoft.design）
ACCENT = "#0f6cbd"          # brandMain
ACCENT_HOVER = "#115ea3"
ACCENT_PRESSED = "#0c3b5e"
ACCENT_TINT = "#eff6fc"     # 选中底
TEXT1 = "#242424"
TEXT2 = "#616161"
STROKE = "#d1d1d1"
DIVIDER = "#e0e0e0"
CARD = "#ffffff"
BG = "#f9f9f9"
SUCCESS = "#0e700e"
ERROR = "#c50f1f"

FONT_FILES = ("SourceHanSansCN-Medium.otf",)
FONT_FALLBACKS = ("思源黑体 CN", "思源黑体", "Noto Sans CJK SC", "Microsoft YaHei UI")

STYLE = f"""
QWidget{{background:{BG};color:{TEXT1};font-size:10pt;}}
QLabel{{background:transparent;color:{TEXT1};}}
QGroupBox{{background:{CARD};border:1px solid {DIVIDER};border-radius:8px;
  margin-top:14px;padding-top:6px;font-weight:600;}}
QGroupBox::title{{subcontrol-origin:margin;left:12px;padding:0 6px;color:{TEXT2};}}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{{background:{CARD};color:{TEXT1};
  border:1px solid {STROKE};border-radius:4px;padding:4px 10px;
  selection-background-color:{ACCENT};selection-color:#fff;}}
QLineEdit:hover,QSpinBox:hover,QDoubleSpinBox:hover,QComboBox:hover{{border-color:#b8b8b8;}}
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus{{border:1px solid {ACCENT};}}
QLineEdit:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled,QComboBox:disabled{{color:#bdbdbd;background:#f5f5f5;}}
QSpinBox::up-button,QDoubleSpinBox::up-button,QSpinBox::down-button,
QDoubleSpinBox::down-button{{background:transparent;border:none;width:16px;}}
QSpinBox::up-button:hover,QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover,QDoubleSpinBox::down-button:hover{{border-radius:2px;background:#f0f0f0;}}
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow{{image:none;width:0;height:0;
  border-left:4px solid transparent;border-right:4px solid transparent;
  border-bottom:5px solid {TEXT2};}}
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{{image:none;width:0;height:0;
  border-left:4px solid transparent;border-right:4px solid transparent;
  border-top:5px solid {TEXT2};}}
QComboBox::drop-down{{border:none;width:22px;background:transparent;}}
QComboBox::down-arrow{{image:none;width:0;height:0;border-left:4px solid transparent;
  border-right:4px solid transparent;border-top:5px solid {TEXT2};}}
QComboBox QAbstractItemView{{background:{CARD};border:1px solid {STROKE};
  selection-background-color:{ACCENT_TINT};selection-color:{TEXT1};outline:none;}}
QPushButton{{background:{CARD};color:{TEXT1};border:1px solid {STROKE};
  border-radius:4px;padding:5px 14px;font-weight:600;}}
QPushButton:hover{{background:#f5f5f5;border-color:#c7c7c7;}}
QPushButton:pressed{{background:#ededed;}}
QPushButton:disabled{{color:#bdbdbd;background:#f5f5f5;border-color:{DIVIDER};}}
QPushButton#genBtn{{background:{ACCENT};color:#fff;border:1px solid {ACCENT};}}
QPushButton#genBtn:hover{{background:{ACCENT_HOVER};}}
QPushButton#genBtn:pressed{{background:{ACCENT_PRESSED};}}
QPushButton#genBtn:disabled{{background:#a9c6e4;color:#f0f6fc;border:1px solid #a9c6e4;}}
QProgressBar{{background:#e0e0e0;border:none;border-radius:3px;max-height:6px;}}
QProgressBar::chunk{{background:{ACCENT};border-radius:3px;}}
QSlider{{background:transparent;}}
QSlider::groove:horizontal{{height:4px;background:{STROKE};border-radius:2px;}}
QSlider::sub-page:horizontal{{background:{ACCENT};border-radius:2px;}}
QSlider::handle:horizontal{{width:14px;height:14px;margin:-5px 0;border-radius:7px;
  background:#fff;border:2px solid {ACCENT};}}
QSlider::handle:horizontal:hover{{border-color:{ACCENT_HOVER};}}
QListWidget{{background:{CARD};border:1px solid {DIVIDER};border-radius:8px;}}
QListWidget::item{{color:#424242;border-radius:4px;margin:2px;}}
QListWidget::item:hover{{background:#f5f5f5;}}
QListWidget::item:selected{{background:{ACCENT_TINT};color:{ACCENT};}}
QTableWidget{{background:{CARD};border:1px solid {DIVIDER};border-radius:8px;
  gridline-color:#f0f0f0;selection-background-color:{ACCENT_TINT};
  selection-color:{TEXT1};}}
QHeaderView::section{{background:#f5f5f5;border:none;border-bottom:1px solid {DIVIDER};
  padding:6px;color:{TEXT2};font-weight:600;}}
QTableCornerButton::section{{background:#f5f5f5;border:none;}}
QTabWidget::pane{{border:none;}}
QTabBar{{background:transparent;}}
QTabBar::tab{{background:transparent;color:#424242;padding:8px 16px;
  border-bottom:2px solid transparent;margin-right:4px;}}
QTabBar::tab:selected{{color:{ACCENT};border-bottom:2px solid {ACCENT};font-weight:600;}}
QTabBar::tab:hover{{color:{ACCENT_HOVER};}}
QStatusBar{{background:{CARD};color:{TEXT2};border-top:1px solid {DIVIDER};}}
QStatusBar::item{{border:none;}}
QToolTip{{background:{CARD};color:{TEXT1};border:1px solid {STROKE};padding:4px;}}
QScrollBar:vertical{{background:transparent;width:10px;margin:2px;}}
QScrollBar::handle:vertical{{background:#c7c7c7;border-radius:4px;min-height:30px;}}
QScrollBar::handle:vertical:hover{{background:#b0b0b0;}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
QScrollBar:horizontal{{background:transparent;height:10px;margin:2px;}}
QScrollBar::handle:horizontal{{background:#c7c7c7;border-radius:4px;min-width:30px;}}
QScrollBar::handle:horizontal:hover{{background:#b0b0b0;}}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;}}
QRadioButton{{background:transparent;}}
QRadioButton::indicator{{width:16px;height:16px;border-radius:9px;
  border:2px solid #666666;background:#fff;}}
QRadioButton::indicator:hover{{border-color:{ACCENT};}}
QRadioButton::indicator:checked{{border:5px solid {ACCENT};background:#fff;}}
QRadioButton:disabled{{color:#bdbdbd;}}
QCheckBox{{background:transparent;}}
QCheckBox::indicator{{width:16px;height:16px;border-radius:4px;
  border:1px solid #666666;background:#fff;}}
QCheckBox::indicator:hover{{border-color:{ACCENT};}}
QCheckBox::indicator:checked{{border:1px solid {ACCENT};background:{ACCENT};}}
QCheckBox:disabled{{color:#bdbdbd;}}
"""


def _load_bundled_font():
    """优先加载随包内置的思源黑体；无则回退系统已装的思源/雅黑。"""
    bases = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        bases.append(base)
        bases.append(os.path.dirname(sys.executable))
    bases.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for base in bases:
        for name in FONT_FILES:
            p = os.path.join(base, "fonts", name)
            if os.path.isfile(p):
                fid = QFontDatabase.addApplicationFont(p)
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
    installed = set(QFontDatabase.families())
    for fam in FONT_FALLBACKS:
        if fam in installed:
            return fam
    return None


def apply_theme(app):
    app.setStyle("Fusion")
    fam = _load_bundled_font() or "Microsoft YaHei UI"
    font = QFont(fam, 10)
    font.setWeight(QFont.Medium)          # 中等偏粗一点点
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)
    app.setStyleSheet(STYLE)


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    win = MainWindow(Config())
    win.setWindowTitle(f"GifKit — GIF截取 & 图片压缩  v{APP_VERSION}")
    win.resize(1120, 740)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
