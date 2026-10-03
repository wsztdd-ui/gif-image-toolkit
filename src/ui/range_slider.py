"""双滑块区间滑杆：一条滑轨，左滑块=起点，右滑块=结束，可整体拖动。"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

MARGIN = 12
HANDLE_R = 7
GAP = 1  # 两滑块最小间隔（单位=0.1s）


class RangeSlider(QWidget):
    selectionChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min, self._max = 0, 100
        self._lo, self._hi = 0, 100
        self._drag = None       # 'lo' / 'hi' / 'span'
        self._span_delta = 0
        self.setFixedHeight(36)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # ---------- 公开接口 ----------
    def set_range(self, lo, hi):
        self._min, self._max = int(lo), int(hi)
        self._lo = max(self._min, min(self._lo, self._max))
        self._hi = max(self._min, min(self._hi, self._max))
        self.update()

    def set_selection(self, lo, hi):
        lo = max(self._min, min(int(lo), self._max))
        hi = max(self._min, min(int(hi), self._max))
        if hi < lo:
            lo, hi = hi, lo
        if (lo, hi) != (self._lo, self._hi):
            self._lo, self._hi = lo, hi
            self.update()
            self.selectionChanged.emit(self._lo, self._hi)

    def selection(self):
        return self._lo, self._hi

    # ---------- 坐标换算 ----------
    def _val_to_x(self, v):
        w = self.width() - MARGIN * 2
        if self._max <= self._min:
            return MARGIN
        return MARGIN + w * (v - self._min) / max(1, self._max - self._min)

    def _x_to_val(self, x):
        w = self.width() - MARGIN * 2
        if w <= 0 or self._max <= self._min:
            return self._min
        v = self._min + (x - MARGIN) * (self._max - self._min) / w
        return int(round(max(self._min, min(self._max, v))))

    # ---------- 绘制 ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        x_lo, x_hi = self._val_to_x(self._lo), self._val_to_x(self._hi)
        enabled = self.isEnabled()
        groove = QColor("#d1d1d1") if enabled else QColor("#e0e0e0")
        accent = QColor("#0f6cbd") if enabled else QColor("#c7c7c7")
        handle_fill = QColor("#ffffff") if enabled else QColor("#f5f5f5")
        # 滑轨
        p.setPen(Qt.NoPen)
        p.setBrush(groove)
        p.drawRoundedRect(QRectF(MARGIN, cy - 2, self.width() - MARGIN * 2, 4), 2, 2)
        # 选中区间
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(x_lo, cy - 2, max(4, x_hi - x_lo), 4), 2, 2)
        # 两个滑块：白底 + 品牌蓝描边 + 蓝色圆心（Fluent 滑块样式）
        pen = p.pen()
        pen.setColor(accent)
        pen.setWidth(2)
        for x in (x_lo, x_hi):
            p.setPen(pen)
            p.setBrush(handle_fill)
            p.drawEllipse(QRectF(x - HANDLE_R, cy - HANDLE_R, HANDLE_R * 2, HANDLE_R * 2))
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(QRectF(x - 3, cy - 3, 6, 6))
        p.end()

    # ---------- 鼠标 ----------
    def _near(self, x1, x2):
        return abs(x1 - x2) <= HANDLE_R + 3

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        x = e.position().x()
        x_lo, x_hi = self._val_to_x(self._lo), self._val_to_x(self._hi)
        if self._near(x, x_lo) and (not self._near(x, x_hi) or x <= x_hi):
            self._drag = "lo"
        elif self._near(x, x_hi):
            self._drag = "hi"
        elif x_lo < x < x_hi:
            self._drag = "span"
            self._span_delta = self._x_to_val(x) - self._lo
        else:
            # 点在轨道外：最近滑块跳过来并进入拖动
            v = self._x_to_val(x)
            if abs(v - self._lo) <= abs(v - self._hi):
                self._drag = "lo"
                self.set_selection(v, self._hi)
            else:
                self._drag = "hi"
                self.set_selection(self._lo, v)
        e.accept()

    def mouseMoveEvent(self, e):
        if not self.isEnabled():
            return
        if not self._drag:
            return
        v = self._x_to_val(e.position().x())
        if self._drag == "lo":
            self.set_selection(min(v, self._hi - GAP), self._hi)
        elif self._drag == "hi":
            self.set_selection(self._lo, max(v, self._lo + GAP))
        else:
            length = self._hi - self._lo
            lo = min(max(v - self._span_delta, self._min), self._max - length)
            self.set_selection(lo, lo + length)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        e.accept()
