"""视频帧预览 + 裁剪框选控件。

裁剪框以源视频像素坐标存储，换帧、换分辨率不失效。
交互：空白处拖出新框 / 框内拖动 / 四角手柄缩放；比例锁定时按比例拟合。
"""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRegion
from PySide6.QtWidgets import QLabel

HANDLE = 10          # 手柄命中半径（控件像素）
MIN_CROP = 8         # 最小裁剪尺寸（视频像素）


class CropPreview(QLabel):
    cropChanged = Signal(object)   # QRect(视频像素坐标) 或 None（表示全画面）
    fileDropped = Signal(str)
    editRequested = Signal()       # 播放预览时点击画面 → 请求回到编辑模式

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 240)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "CropPreview{background:#17191d;border:1px solid #d1d3d9;border-radius:8px;}")
        self._orig = None       # 当前帧 QPixmap（原始尺寸）
        self._scaled = None     # 等比缩放后的显示图
        self._vw = 0
        self._vh = 0
        self._crop = None       # QRect 视频像素坐标
        self._ratio = None      # float 宽/高，None=自由
        self._live = False      # True=选段预览播放中（隐藏裁剪框、点击返回编辑）
        self._mode = None       # None/'draw'/'move'/'nw'/'ne'/'sw'/'se'
        self._anchor = QPoint()
        self._move_off = QPoint()
        self._crop_before = None

    # ---------- 图像与坐标 ----------
    def set_image(self, pixmap, video_w, video_h):
        self._orig = pixmap
        self._vw, self._vh = int(video_w), int(video_h)
        self._rescale()
        if self._crop is not None:
            self._clamp_crop()
        self.update()

    def clear_image(self):
        self._orig = self._scaled = None
        self._vw = self._vh = 0
        self._crop = None
        self.update()

    def has_image(self):
        return self._scaled is not None

    def get_crop(self):
        return self._crop

    def set_crop(self, rect):
        self._crop = QRect(rect) if rect is not None else None
        if self._crop is not None:
            self._clamp_crop()
        self.update()
        self.cropChanged.emit(self._crop)

    def clear_crop(self):
        self.set_crop(None)

    def set_ratio(self, ratio):
        self._ratio = ratio
        if self._crop is not None and ratio:
            self._apply_ratio_centered()

    def set_live(self, pixmap):
        """选段预览播放中的一帧：铺满显示、不画裁剪框。"""
        self._live = True
        self._orig = pixmap
        self._vw, self._vh = pixmap.width(), pixmap.height()
        self._rescale()
        self.update()

    def end_live(self):
        self._live = False

    def is_live(self):
        return self._live

    def _disp_rect(self):
        if not self._scaled:
            return QRect()
        return QRect((self.width() - self._scaled.width()) // 2,
                     (self.height() - self._scaled.height()) // 2,
                     self._scaled.width(), self._scaled.height())

    def _scale(self):
        r = self._disp_rect()
        if not r.width() or not self._vw:
            return 1.0
        return self._vw / r.width()

    def _to_video(self, pos):
        r = self._disp_rect()
        s = self._scale()
        return QPoint(int(round((pos.x() - r.x()) / s)),
                      int(round((pos.y() - r.y()) / s)))

    def _to_widget(self, pt):
        r = self._disp_rect()
        s = self._scale()
        return QPoint(r.x() + int(round(pt.x() * s)),
                      r.y() + int(round(pt.y() * s)))

    def _video_rect(self):
        return QRect(0, 0, max(1, self._vw), max(1, self._vh))

    def _rescale(self):
        if not self._orig:
            self._scaled = None
            return
        avail = QSize(max(40, self.width() - 32), max(40, self.height() - 32))
        self._scaled = self._orig.scaled(avail, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)

    def resizeEvent(self, e):
        self._rescale()
        self.update()
        super().resizeEvent(e)

    # ---------- 裁剪逻辑 ----------
    def _clamp_crop(self):
        if self._crop is None:
            return
        self._crop = self._crop.intersected(self._video_rect())
        if self._crop.width() < 2 or self._crop.height() < 2:
            self._crop = None

    def _apply_ratio_centered(self):
        c, r, vr = self._crop, self._ratio, self._video_rect()
        w = c.width()
        h = int(round(w / r))
        if h > vr.height():
            h = vr.height()
            w = max(2, int(round(h * r)))
        cx, cy = c.center().x(), c.center().y()
        x = min(max(cx - w // 2, 0), vr.width() - w)
        y = min(max(cy - h // 2, 0), vr.height() - h)
        self._crop = QRect(x, y, w, h)
        self._clamp_crop()
        self.update()
        self.cropChanged.emit(self._crop)

    def _ratio_fit(self, anchor, free):
        """anchor 为固定角、free 为活动角，按比例拟合矩形并限制在画面内。"""
        vr = self._video_rect()
        dx = free.x() - anchor.x()
        w = max(abs(dx), 2)
        if self._ratio:
            h = int(round(w / self._ratio))
            avail_w = (vr.width() - anchor.x()) if dx >= 0 else anchor.x()
            below = free.y() >= anchor.y()
            avail_h = (vr.height() - anchor.y()) if below else anchor.y()
            if h > avail_h and avail_h >= 2:
                h = avail_h
                w = max(2, int(round(h * self._ratio)))
            if w > avail_w and avail_w >= 2:
                w = avail_w
                h = max(2, int(round(w / self._ratio)))
        else:
            h = max(abs(free.y() - anchor.y()), 2)
        x = anchor.x() if dx >= 0 else anchor.x() - w
        y = anchor.y() if free.y() >= anchor.y() else anchor.y() - h
        return QRect(x, y, w, h)

    # ---------- 绘制 ----------
    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        if not self._scaled:
            p.setPen(QColor(147, 160, 180))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "将视频或动图 GIF 拖到此处\n（也可点下方“选择视频”按钮）")
            p.end()
            return
        r = self._disp_rect()
        p.drawPixmap(r.topLeft(), self._scaled)
        if self._crop is not None and not self._live:
            wr = QRect(self._to_widget(self._crop.topLeft()),
                       self._to_widget(self._crop.bottomRight())).normalized()
            p.setClipRegion(QRegion(r) - QRegion(wr))
            p.fillRect(r, QColor(0, 0, 0, 130))
            p.setClipping(False)
            accent = QColor(76, 194, 255)          # Fluent 亮蓝，在深色视频帧上清晰
            pen = QPen(accent)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(wr)
            p.setBrush(accent)
            p.setPen(Qt.NoPen)
            for pt in (wr.topLeft(), wr.topRight(), wr.bottomLeft(), wr.bottomRight()):
                p.drawRect(pt.x() - HANDLE // 2, pt.y() - HANDLE // 2, HANDLE, HANDLE)
            p.setPen(accent)
            p.drawText(wr.x(), max(14, wr.y() - 6),
                       f"{self._crop.width()} × {self._crop.height()} px")
        p.end()

    # ---------- 鼠标 ----------
    def _widget_crop_rect(self):
        if self._crop is None:
            return None
        return QRect(self._to_widget(self._crop.topLeft()),
                     self._to_widget(self._crop.bottomRight())).normalized()

    def _hit_handle(self, pos, wr):
        for name, pt in (("nw", wr.topLeft()), ("ne", wr.topRight()),
                         ("sw", wr.bottomLeft()), ("se", wr.bottomRight())):
            if (pos - pt).manhattanLength() <= HANDLE:
                return name
        return None

    def mousePressEvent(self, e):
        if self._live:
            if e.button() == Qt.LeftButton:
                self.editRequested.emit()
            e.accept()
            return
        if e.button() != Qt.LeftButton or not self._scaled:
            return
        pos = e.position().toPoint()
        v = self._to_video(pos)
        wr = self._widget_crop_rect()
        h = self._hit_handle(pos, wr) if wr else None
        self._crop_before = self._crop
        if h:
            self._mode = h
            self._anchor = {"nw": self._crop.bottomRight(),
                            "ne": self._crop.bottomLeft(),
                            "sw": self._crop.topRight(),
                            "se": self._crop.topLeft()}[h]
        elif wr and wr.contains(pos):
            self._mode = "move"
            self._move_off = v - self._crop.topLeft()
        elif self._disp_rect().contains(pos):
            self._mode = "draw"
            self._anchor = v
            self._crop = QRect(v, v)
            self.update()
        e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if not self._mode:
            self._update_cursor(pos)
            return
        v = self._to_video(pos)
        if self._mode == "move":
            nx = min(max(v.x() - self._move_off.x(), 0),
                     max(0, self._vw - self._crop.width()))
            ny = min(max(v.y() - self._move_off.y(), 0),
                     max(0, self._vh - self._crop.height()))
            self._crop.moveTo(nx, ny)
        elif self._mode == "draw":
            self._crop = self._ratio_fit(self._anchor, v)
        else:
            self._crop = self._ratio_fit(self._anchor, v)
        self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        if not self._mode:
            return
        m = self._mode
        self._mode = None
        if self._crop is not None and (self._crop.width() < MIN_CROP
                                       or self._crop.height() < MIN_CROP):
            self._crop = self._crop_before
        elif self._crop is not None and m == "draw" and \
                self._crop.width() >= self._vw - 2 and self._crop.height() >= self._vh - 2:
            self._crop = None        # 拉满全画面 = 不裁剪
        if self._crop is not None:
            self._clamp_crop()
        self.update()
        self.cropChanged.emit(self._crop)
        e.accept()

    def _update_cursor(self, pos):
        if self._live:
            self.setCursor(Qt.PointingHandCursor)
            return
        wr = self._widget_crop_rect()
        h = self._hit_handle(pos, wr) if wr else None
        if h in ("nw", "se"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif h in ("ne", "sw"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif wr and wr.contains(pos):
            self.setCursor(Qt.SizeAllCursor)
        elif self._disp_rect().contains(pos):
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # ---------- 拖放 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if u.isLocalFile():
                    e.acceptProposedAction()
                    return

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.fileDropped.emit(u.toLocalFile())
                e.acceptProposedAction()
                return
