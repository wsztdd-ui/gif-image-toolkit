"""「视频转 GIF」页：拖入视频/动图 → 时间选取 → 框选裁剪 → 参数 → 预览 → 保存。"""
import os
import shutil
import tempfile

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QMovie, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFrame, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QListView, QProgressBar, QPushButton, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from core import ffmpeg as ff
from core.workers import FnWorker, GifWorker, install_preview, shutdown_worker
from ui.crop_preview import CropPreview
from ui.range_slider import RangeSlider
from ui.widgets import Collapsible, OutputLocation
from utils import fsutil
from utils.timefmt import fmt_seconds, human_size

PRESETS = {"均衡（默认）": (12, 128, "bayer"),
           "高质量": (15, 256, "floyd"),
           "高压缩": (8, 64, "none")}
WIDTHS = [("720", "720（默认 · 16:9 源即 720×405）"), ("0", "原始宽度"),
          ("640", "640"), ("480", "480"), ("360", "360"), ("240", "240"),
          ("c", "自定义…")]
COLORS = ["256", "128", "64", "32"]
DITHERS = [("bayer", "Bayer"), ("floyd", "Floyd"), ("none", "无抖动")]
PREVIEW_W, PREVIEW_H = 640, 400


class GifTab(QWidget):
    imageDropped = Signal(str)     # 图片被拖到本页 → 主窗口切到图片页

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.video = None
        self.info = None
        self.gif_mode = False
        self._busy = False
        self._gen = None
        self._tmp_workers = []
        self._thumb_dir = None
        self._preview_file = None
        self._last_dst = None
        self._movie = None                  # QMovie 强引用，防 GC 中断动画
        self._frame_gen = 0                 # 取帧代数：丢弃旧视频的迟到结果
        self._thumb_gen = 0
        self._est_gen = 0                   # 估算校准代数：丢弃旧参数的迟到结果
        self._sel_timer = QTimer(self)      # 选段变化 → 防抖刷新静态预览帧
        self._sel_timer.setSingleShot(True)
        self._sel_timer.timeout.connect(self._refresh_frame)
        self._est_timer = QTimer(self)      # 参数变化 → 防抖后台试编校准估算
        self._est_timer.setSingleShot(True)
        self._est_timer.timeout.connect(self._start_est_probe)
        self._replay_timer = QTimer(self)   # 播放中改参数 → 防抖后按新参数重播
        self._replay_timer.setSingleShot(True)
        self._replay_timer.timeout.connect(self._on_replay_timeout)
        self._play_timer = None             # 预览翻帧定时器
        self._play_frames = []
        self._play_idx = 0
        self._play_gen = 0
        self._sel_dir = None
        self._build_ui()
        self.apply_settings()

    # ================= UI 构建 =================
    def _build_ui(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 1)
        root.addLayout(right, 0)

        # -- 左列 --
        self.warn_label = QLabel("")
        self.warn_label.setStyleSheet("color:#bc4b09;")
        self.warn_label.setWordWrap(True)
        self.warn_label.setVisible(False)
        left.addWidget(self.warn_label)

        self.preview_stack = QStackedWidget()
        self.preview = CropPreview()
        self.preview.cropChanged.connect(self._on_crop_changed)
        self.preview.fileDropped.connect(self._route_drop)
        self.preview.editRequested.connect(self._stop_playback)
        self.preview.openRequested.connect(self._pick_video)
        self.preview.setMinimumHeight(300)
        self.preview_label = QLabel("预览生成中…")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            "background:#17191d;border:1px solid #d1d3d9;border-radius:8px;color:#9a9da5;")
        self.preview_stack.addWidget(self.preview)          # 0 裁剪
        self.preview_stack.addWidget(self.preview_label)    # 1 成品预览
        left.addWidget(self.preview_stack, 1)

        self.file_line = QLabel("")
        self.file_line.setWordWrap(True)
        self.file_line.setStyleSheet(
            "background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;"
            "padding:6px 12px;color:#616161;font-size:12px;")
        self.file_line.setVisible(False)
        left.addWidget(self.file_line)

        tbox = QGroupBox("截取时间")
        tform = QVBoxLayout(tbox)
        prow = QHBoxLayout()
        self.btn_play = QPushButton("▶ 播放选段")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_play)
        prow.addWidget(self.btn_play)
        prow.addStretch(1)
        tform.addLayout(prow)
        self.range_slider = RangeSlider()
        self.range_slider.selectionChanged.connect(self._on_range)
        tform.addWidget(self.range_slider)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("起点"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(2)
        self.start_spin.setSingleStep(0.1)
        self.start_spin.setSuffix(" s")
        self.start_spin.setValue(0.0)
        self.start_spin.valueChanged.connect(self._on_start_spin)
        row2.addWidget(self.start_spin)
        row2.addSpacing(14)
        row2.addWidget(QLabel("时长"))
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setDecimals(2)
        self.dur_spin.setSingleStep(0.1)
        self.dur_spin.setSuffix(" s")
        self.dur_spin.setValue(5.0)
        self.dur_spin.valueChanged.connect(self._on_dur_spin)
        row2.addWidget(self.dur_spin)
        row2.addStretch(1)
        self.btn_full = QPushButton("选整段")
        self.btn_full.clicked.connect(self._select_full)
        row2.addWidget(self.btn_full)
        tform.addLayout(row2)
        self.time_note = QLabel("")
        self.time_note.setStyleSheet("color:#616161;font-size:12px;")
        tform.addWidget(self.time_note)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setFlow(QListView.LeftToRight)     # 单行横向，左右滚动
        self.thumbs.setWrapping(False)
        self.thumbs.setFixedHeight(118)
        self.thumbs.setIconSize(QSize(128, 72))
        self.thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumbs.itemClicked.connect(self._on_thumb_click)
        tform.addWidget(self.thumbs)
        left.addWidget(tbox)

        # -- 右列 --
        right_box = QWidget()
        right_box.setFixedWidth(366)
        right.addWidget(right_box, 1)
        rc = QVBoxLayout(right_box)
        rc.setContentsMargins(0, 0, 0, 0)

        cbox = QGroupBox("裁剪")
        cv = QVBoxLayout(cbox)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("比例"))
        self.ratio_combo = QComboBox()
        for k, v in (("自由", None), ("16:9", 16 / 9), ("1:1", 1.0),
                     ("9:16", 9 / 16), ("4:3", 4 / 3), ("16:10", 1.6)):
            self.ratio_combo.addItem(k, v)
        self.ratio_combo.currentIndexChanged.connect(self._on_ratio)
        crow.addWidget(self.ratio_combo, 1)
        self.btn_crop_reset = QPushButton("重置")
        self.btn_crop_reset.clicked.connect(self.preview.clear_crop)
        crow.addWidget(self.btn_crop_reset)
        cv.addLayout(crow)
        self.crop_label = QLabel("全画面 · 在预览图上拖拽框选可只截局部")
        self.crop_label.setStyleSheet("color:#616161;font-size:12px;")
        self.crop_label.setWordWrap(True)
        cv.addWidget(self.crop_label)
        rc.addWidget(cbox)

        obox = QGroupBox("输出")
        ov = QVBoxLayout(obox)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("质量预设"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["自定义", *PRESETS.keys()])
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        prow.addWidget(self.preset_combo, 1)
        ov.addLayout(prow)
        wrow = QHBoxLayout()
        wrow.addWidget(QLabel("宽度"))
        self.width_combo = QComboBox()
        for val, name in WIDTHS:
            self.width_combo.addItem(name, val)
        self.width_combo.currentIndexChanged.connect(self._on_width_mode)
        wrow.addWidget(self.width_combo, 1)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(64, 1920)
        self.width_spin.setValue(720)
        self.width_spin.valueChanged.connect(self._on_output_changed)
        self.width_spin.setVisible(False)
        wrow.addWidget(self.width_spin)
        ov.addLayout(wrow)
        trow = QHBoxLayout()
        self.target_chk = QCheckBox("压到指定体积")
        self.target_chk.setToolTip("以当前参数为质量上限自动下调（帧率→颜色数→宽度），"
                                   "生成不超过目标体积的 GIF；耗时可能成倍增加")
        self.target_chk.toggled.connect(self._on_target_mode)
        trow.addWidget(self.target_chk)
        self.target_spin = QDoubleSpinBox()
        self.target_spin.setDecimals(1)
        self.target_spin.setSingleStep(0.1)
        self.target_spin.setRange(0.1, 500.0)
        self.target_spin.setSuffix(" MB")
        self.target_spin.setValue(2.0)
        self.target_spin.setEnabled(False)
        self.target_spin.valueChanged.connect(self._on_output_changed)
        trow.addWidget(self.target_spin)
        trow.addStretch(1)
        ov.addLayout(trow)
        self.estimate = QLabel("—")
        self.estimate.setStyleSheet("color:#0e700e;")
        self.estimate.setToolTip("“粗估”为公式快算；“实测”按当前参数试编码 1 秒外推，更准")
        ov.addWidget(self.estimate)

        adv = Collapsible("高级参数")
        arow1 = QHBoxLayout()
        arow1.addWidget(QLabel("帧率"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(3, 30)
        self.fps_spin.setValue(12)
        self.fps_spin.valueChanged.connect(self._on_detail_change)
        arow1.addWidget(self.fps_spin)
        arow1.addSpacing(8)
        arow1.addWidget(QLabel("颜色数"))
        self.colors_combo = QComboBox()
        self.colors_combo.addItems(COLORS)
        self.colors_combo.currentIndexChanged.connect(self._on_detail_change)
        arow1.addWidget(self.colors_combo)
        arow1.addSpacing(8)
        arow1.addWidget(QLabel("抖动"))
        self.dither_combo = QComboBox()
        for val, name in DITHERS:
            self.dither_combo.addItem(name, val)
        self.dither_combo.setItemData(0, "Bayer 抖动：体积小，适合截图类", Qt.ToolTipRole)
        self.dither_combo.setItemData(1, "Floyd 抖动：过渡更平滑，体积略大", Qt.ToolTipRole)
        self.dither_combo.currentIndexChanged.connect(self._on_detail_change)
        arow1.addWidget(self.dither_combo, 1)
        adv.add_layout(arow1)
        arow1b = QHBoxLayout()
        arow1b.addWidget(QLabel("隔行源"))
        self.deint_combo = QComboBox()
        for val, name in (("auto", "自动去隔行"), ("on", "强制开启"), ("off", "关闭")):
            self.deint_combo.addItem(name, val)
        self.deint_combo.setItemData(
            0, "检测到隔行扫描素材（如广电 1080i TS）时自动套 yadif 去隔行，"
               "避免画面梳齿", Qt.ToolTipRole)
        self.deint_combo.currentIndexChanged.connect(self._on_detail_change)
        arow1b.addWidget(self.deint_combo)
        arow1b.addStretch(1)
        adv.add_layout(arow1b)
        arow2 = QHBoxLayout()
        arow2.addWidget(QLabel("文件后缀"))
        self.suffix_edit = QLineEdit("_gif")
        self.suffix_edit.setFixedWidth(80)
        arow2.addWidget(self.suffix_edit)
        arow2.addWidget(QLabel("文件名 = 源文件名 + 后缀 + .gif"))
        arow2.addStretch(1)
        adv.add_layout(arow2)
        ov.addWidget(adv)

        self.outloc = OutputLocation("和视频相同的位置")
        self.radio_src = self.outloc.radio_src
        self.radio_custom = self.outloc.radio_custom
        self.out_edit = self.outloc.out_edit
        ov.addWidget(self.outloc)
        rc.addWidget(obox)

        gen_card = QFrame()
        gen_card.setObjectName("card")
        gv = QVBoxLayout(gen_card)
        gv.setContentsMargins(10, 10, 10, 10)
        gv.setSpacing(6)
        self.btn_gen = QPushButton("生成 GIF")
        self.btn_gen.setObjectName("genBtn")
        self.btn_gen.setMinimumHeight(40)
        self.btn_gen.clicked.connect(self._do_preview)
        gv.addWidget(self.btn_gen)
        self.progress = _ProgressBar()
        self.progress.setVisible(False)
        gv.addWidget(self.progress)
        gstat = QHBoxLayout()
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#616161;")
        self.status.setWordWrap(True)
        gstat.addWidget(self.status, 1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_gen)
        gstat.addWidget(self.btn_cancel)
        gv.addLayout(gstat)
        self.cmp_label = QLabel("")
        self.cmp_label.setStyleSheet("color:#0e700e;font-size:14pt;font-weight:600;")
        self.cmp_label.setToolTip("预览产物与保存的文件完全一致")
        self.cmp_label.setVisible(False)
        gv.addWidget(self.cmp_label)
        self.pv_meta = QLabel("")
        self.pv_meta.setWordWrap(True)
        self.pv_meta.setStyleSheet("color:#616161;font-size:12px;")
        self.pv_meta.setVisible(False)
        gv.addWidget(self.pv_meta)
        brow = QHBoxLayout()
        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("genBtn")
        self.btn_save.setMinimumHeight(34)
        self.btn_save.setVisible(False)
        self.btn_save.clicked.connect(self._save_preview)
        brow.addWidget(self.btn_save, 1)
        self.btn_discard = QPushButton("重新调整")
        self.btn_discard.setVisible(False)
        self.btn_discard.clicked.connect(self._back_to_edit)
        brow.addWidget(self.btn_discard)
        gv.addLayout(brow)
        srow = QHBoxLayout()
        self.btn_open = QPushButton("打开目录")
        self.btn_open.setObjectName("linkBtn")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setVisible(False)
        self.btn_open.clicked.connect(lambda: fsutil.open_in_explorer(self._last_dst))
        srow.addWidget(self.btn_open)
        srow.addStretch(1)
        gv.addLayout(srow)
        rc.addWidget(gen_card)
        rc.addStretch(1)

        ok, msg = ff.available()
        if not ok:
            self.warn_label.setText(msg)
            self.warn_label.setVisible(True)
            self.preview.set_hint("把视频拖到这里，或点击选择", msg)
            self.btn_gen.setEnabled(False)

    # ================= 载入 =================
    def _pick_video(self):
        exts = " ".join("*" + e for e in sorted(ff.VIDEO_EXTS | {".gif"}))
        path, _ = QFileDialog.getOpenFileName(self, "选择视频或动图 GIF", "",
                                              f"视频/动图 ({exts});;所有文件 (*)")
        if path:
            self.load_path(path)

    def _route_drop(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".gif" or ext in ff.VIDEO_EXTS:
            self.load_path(path)
        elif ext in ff.IMAGE_EXTS:
            self.imageDropped.emit(path)
        else:
            self._status("不支持的文件类型: " + ext, warn=True)

    def load_path(self, path):
        if self._busy:
            self._status("正在生成中，请先取消或等待完成", warn=True)
            return
        ok, msg = ff.available()
        if not ok:
            self._status(msg, warn=True)
            return
        try:
            info = ff.probe(path)
        except ff.FfmpegError as e:
            self._status(str(e), warn=True)
            return
        self._stop_playback()
        self._sel_timer.stop()
        self._est_timer.stop()
        self._est_gen += 1          # 作废旧视频的迟到估算校准
        self._back_to_edit()        # 先释放预览动画的文件句柄，临时产物才删得掉
        self._cleanup_temp()
        self.video = path
        self.info = info
        self.gif_mode = path.lower().endswith(".gif")
        self.preview.clear_crop()
        dur = info["duration"]
        known = dur > 0
        self.range_slider.blockSignals(True)
        if known:
            self.range_slider.setEnabled(True)
            self.range_slider.set_range(0, max(1, round(dur * 10)))
            self.range_slider.set_selection(0, round(min(10.0, dur) * 10))
            self.start_spin.setRange(0.0, max(0.0, round(dur * 100) / 100))
            self.dur_spin.setRange(0.1, round(dur * 100) / 100)
            self.start_spin.setValue(0.0)
            self.dur_spin.setValue(min(10.0, dur))
        else:
            self.range_slider.setEnabled(False)
            self.range_slider.set_range(0, 1)
            self.range_slider.set_selection(0, 1)
            self.start_spin.setRange(0.0, 7200.0)
            self.dur_spin.setRange(0.1, 120.0)
            self.start_spin.setValue(0.0)
            self.dur_spin.setValue(10.0)
        self.range_slider.blockSignals(False)
        if self.gif_mode:
            self.time_note.setText("点“▶ 播放选段”预览效果；点击画面返回编辑。")
        else:
            self.time_note.setText("拖两端选范围，按住中间整体平移；点缩略图设为起点，"
                                   "“▶ 播放选段”可预览效果。")
        size_txt = human_size(info["size"]) if info["size"] else "未知"
        dur_txt = fmt_seconds(info["duration"]) if known else "时长未知"
        self.file_line.setText(
            f"<b>{os.path.basename(path)}</b>　{size_txt} · "
            f"{info['width']}×{info['height']} · {dur_txt}"
            + ("　· 动图" if self.gif_mode else ""))
        self.file_line.setVisible(True)
        self._stop_playback()
        self._load_thumbs()
        self._update_estimate()
        self._refresh_frame()
        self.btn_play.setEnabled(True)
        self._status("已载入 " + os.path.basename(path))

    # ================= 时间与帧 =================
    def _start_sec(self):
        return float(self.start_spin.value())

    def _dur_sec(self):
        return float(self.dur_spin.value())

    def _deint_mode(self):
        return self.deint_combo.currentData()

    def _on_target_mode(self, checked):
        self.target_spin.setEnabled(checked)
        self._on_output_changed()

    def _on_preview_param_changed(self):
        """参数变化：刷新估算；播放中则去抖后按新参数重播，避免拖动期间反复抽帧。"""
        self._update_estimate()
        if self._is_playing():
            self._replay_timer.start(400)
        else:
            self._sel_timer.start(600)

    def _on_replay_timeout(self):
        if self._is_playing():
            self._play_selection()

    def _on_range(self, lo, hi):
        self.start_spin.blockSignals(True)
        self.dur_spin.blockSignals(True)
        self.start_spin.setValue(lo / 10.0)
        self.dur_spin.setValue((hi - lo) / 10.0)
        self.start_spin.blockSignals(False)
        self.dur_spin.blockSignals(False)
        self._on_preview_param_changed()

    def _on_start_spin(self, val):
        total = self.info["duration"] if self.info else 0
        if total > 0:
            if val > total - 0.1:
                val = max(0.0, total - 0.1)
                self.start_spin.blockSignals(True)
                self.start_spin.setValue(val)
                self.start_spin.blockSignals(False)
            max_dur = max(0.1, total - self._start_sec())
            if self.dur_spin.value() > max_dur:
                self.dur_spin.blockSignals(True)
                self.dur_spin.setValue(max_dur)
                self.dur_spin.blockSignals(False)
        self._sync_slider()
        self._on_preview_param_changed()

    def _on_dur_spin(self, val):
        total = self.info["duration"] if self.info else 0
        if total > 0:
            max_dur = max(0.1, total - self._start_sec())
            if val > max_dur:
                val = max_dur
                self.dur_spin.blockSignals(True)
                self.dur_spin.setValue(val)
                self.dur_spin.blockSignals(False)
        self._sync_slider()
        self._on_preview_param_changed()

    def _sync_slider(self):
        s = self.range_slider
        if not s.isEnabled():
            return
        s.blockSignals(True)
        s.set_selection(round(self._start_sec() * 10),
                        round((self._start_sec() + self._dur_sec()) * 10))
        s.blockSignals(False)

    def _select_full(self):
        total = self.info["duration"] if self.info else 0
        if total <= 0:
            self._status("该文件时长未知，请手动输入时长", warn=True)
            return
        self.start_spin.setValue(0.0)
        self.dur_spin.setValue(total)

    def _on_thumb_click(self, item):
        t = item.data(Qt.UserRole)
        if t is not None:
            self.start_spin.setValue(round(float(t) * 100) / 100)

    def _refresh_frame(self):
        if not self.video or self._busy:
            return
        w = self.info["width"] or 1280
        self._frame_gen += 1
        gen = self._frame_gen

        def job():
            # 文件名带上代数：快速调参时新旧两帧可能并发抽帧，避免写同一个文件
            out = os.path.join(tempfile.gettempdir(),
                               f"gifkit_{os.getpid()}_frame_{gen}.png")
            ff.extract_frame(self.video, self._start_sec(), out,
                             width=min(960, max(320, w)),
                             deinterlace=ff._need_deinterlace(
                                 self._deint_mode(), self.info.get("field_order")))
            return out

        wk = FnWorker(job)
        self._track(wk)
        wk.gen = gen
        wk.done.connect(self._on_frame)
        wk.failed.connect(self._on_frame_failed)
        wk.start()

    def _on_frame_failed(self, msg):
        wk = self.sender()
        if getattr(wk, "gen", 0) != self._frame_gen:
            return
        self._status("取帧失败：" + msg, warn=True)

    def _on_frame(self, path):
        wk = self.sender()
        stale = getattr(wk, "gen", 0) != self._frame_gen
        if stale or not self.video:
            try:
                os.remove(path)
            except OSError:
                pass
            return
        if self.preview.is_live():
            # 选段播放/冻结期间迟到的静态帧会顶掉播放画面，丢弃
            try:
                os.remove(path)
            except OSError:
                pass
            return
        pm = QPixmap(path)
        if not pm.isNull():
            self.preview.set_image(pm, self.info["width"], self.info["height"])
        try:
            os.remove(path)
        except OSError:
            pass

    def _load_thumbs(self):
        self.thumbs.clear()
        if self._thumb_dir:
            shutil.rmtree(self._thumb_dir, ignore_errors=True)
        self._thumb_dir = tempfile.mkdtemp(prefix="gifkit_thumbs_")
        self._thumb_gen += 1
        gen = self._thumb_gen

        def job():
            return ff.extract_thumbs(self.video, count=8, out_dir=self._thumb_dir)

        wk = FnWorker(job)
        self._track(wk)
        wk.gen = gen
        wk.done.connect(self._on_thumbs)
        wk.failed.connect(self._on_thumbs_failed)
        wk.start()

    def _on_thumbs_failed(self, msg):
        wk = self.sender()
        if getattr(wk, "gen", 0) != self._thumb_gen:
            return
        self.time_note.setText("缩略图生成失败：" + msg)

    def _on_thumbs(self, thumbs):
        wk = self.sender()
        if getattr(wk, "gen", 0) != self._thumb_gen:
            return
        self.thumbs.clear()
        for t, p in thumbs:
            icon = _scaled_icon(p, 128, 72)
            it = QListWidgetItem(icon, fmt_seconds(t))
            it.setData(Qt.UserRole, t)
            it.setSizeHint(QSize(132, 88))
            self.thumbs.addItem(it)
        if not thumbs:
            self.time_note.setText("未能生成缩略图（时长未知或文件异常），请手动输入时间。")

    # ================= 选段预览（手动播放） =================
    def _is_playing(self):
        return self._play_timer is not None and self._play_timer.isActive()

    def _toggle_play(self):
        if self._is_playing():
            self._stop_playback()
        else:
            self._play_selection()

    def _pause_playback(self):
        """停掉翻帧定时器但保留最后一帧画面（冻结）。

        帧目录马上要清掉重建，旧帧路径即将失效：若不停定时器，它会继续
        翻已删除的帧，QPixmap 变空后预览会闪成空状态提示。
        """
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
        self._sel_timer.stop()
        self._play_frames = []
        self._play_idx = 0

    def _play_selection(self):
        """按当前 范围+裁剪+宽度+帧率 抽帧并循环播放（点击画面返回编辑）。"""
        if not self.video or self._busy:
            return
        start = self._start_sec()
        dur = self._dur_sec()
        if dur <= 0:
            return
        pfs = min(max(3, self.fps_spin.value()), 15)      # 预览帧率封顶 15，够流畅
        if dur * pfs > 240:                               # 帧数上限保护
            pfs = max(3, int(240 / dur))
        self._pause_playback()    # 旧一轮先冻结在最后一帧，帧目录才能安全重建
        if self._sel_dir:
            shutil.rmtree(self._sel_dir, ignore_errors=True)
        self._sel_dir = tempfile.mkdtemp(prefix="gifkit_sel_")
        self._play_gen += 1
        gen = self._play_gen

        def job():
            return ff.extract_frames(self.video, self._sel_dir, start=start,
                                     duration=dur, crop=self._crop_tuple(),
                                     width=480, fps=pfs,
                                     deinterlace=ff._need_deinterlace(
                                         self._deint_mode(),
                                         self.info.get("field_order")))

        wk = FnWorker(job)
        self._track(wk)
        wk.gen = gen
        wk.fps = pfs
        wk.done.connect(self._on_play_done)
        wk.failed.connect(self._on_play_failed)
        wk.start()

    def _on_play_done(self, paths):
        wk = self.sender()
        self._on_play_frames(paths, getattr(wk, "gen", 0), getattr(wk, "fps", 12))

    def _on_play_failed(self, msg):
        wk = self.sender()
        if getattr(wk, "gen", 0) != self._play_gen:
            return              # 旧一代抽帧失败（目录已被新一轮清掉），忽略
        self._stop_playback()   # 本轮失败：回到编辑模式，别停在冻结画面上
        self._status("选段预览失败：" + msg, warn=True)

    def _on_play_frames(self, paths, gen, fps):
        if gen != self._play_gen or not paths or not self.video:
            return
        self._stop_playback(quiet=True)
        self._play_frames = paths
        self._play_idx = 0
        self.preview.set_live(QPixmap(paths[0]))
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(max(33, round(1000 / fps)))
        self._play_timer.timeout.connect(self._advance_playback)
        self._play_timer.start()
        self.btn_play.setText("⏹ 停止预览")
        self._status("选段预览中 · 点击画面返回编辑")

    def _advance_playback(self):
        if not self._play_frames:
            return
        self._play_idx = (self._play_idx + 1) % len(self._play_frames)
        pm = QPixmap(self._play_frames[self._play_idx])
        if not pm.isNull():     # 帧文件被外部清掉等异常下别把空图贴上去
            self.preview.set_live(pm)

    def _stop_playback(self, quiet=False):
        self._replay_timer.stop()
        self._play_gen += 1     # 作废在途抽帧：停止后结果返回不得把播放拉起来
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
        was_live = self.preview.is_live()
        self.preview.end_live()
        if hasattr(self, "btn_play"):
            self.btn_play.setText("▶ 播放选段")
        if was_live and not quiet and self.video and not self._busy:
            self._refresh_frame()
            self._status("已返回编辑模式")
        if not quiet:
            self._play_frames = []
            self._play_idx = 0

    # ================= 裁剪 / 参数 =================
    def _on_crop_changed(self, crop):
        if crop is None:
            self.crop_label.setText("全画面 · 在预览图上拖拽框选可只截局部")
        else:
            self.crop_label.setText(f"裁剪 {crop.width()} × {crop.height()} px")
        self._update_estimate()

    def _on_ratio(self):
        self.preview.set_ratio(self.ratio_combo.currentData())

    def _on_width_mode(self):
        custom = self.width_combo.currentData() == "c"
        self.width_spin.setVisible(custom)
        self._on_output_changed()

    def _on_preset(self):
        idx = self.preset_combo.currentIndex()
        if idx <= 0:
            return
        fps, colors, dither = list(PRESETS.values())[idx - 1]
        self.fps_spin.blockSignals(True)
        self.colors_combo.blockSignals(True)
        self.dither_combo.blockSignals(True)
        self.fps_spin.setValue(fps)
        self.colors_combo.setCurrentIndex(COLORS.index(str(colors)))
        self.dither_combo.setCurrentIndex([v for v, _ in DITHERS].index(dither))
        self.fps_spin.blockSignals(False)
        self.colors_combo.blockSignals(False)
        self.dither_combo.blockSignals(False)
        self._on_output_changed()

    def _on_detail_change(self):
        self._sync_preset_label()
        self._on_output_changed()

    def _on_output_changed(self):
        """输出参数变化：刷新估算；正在播放则按新参数重播。"""
        self._on_preview_param_changed()

    def _sync_preset_label(self):
        fps = self.fps_spin.value()
        colors = int(self.colors_combo.currentText())
        dither = self.dither_combo.currentData()
        self.preset_combo.blockSignals(True)
        hit = 0
        for i, (name, (f, c, d)) in enumerate(PRESETS.items(), start=1):
            if (f, c, d) == (fps, colors, dither):
                hit = i
        self.preset_combo.setCurrentIndex(hit)
        self.preset_combo.blockSignals(False)

    def _out_width(self):
        mode = self.width_combo.currentData()
        if mode == "c":
            return int(self.width_spin.value())
        return int(mode) if mode != "0" else 0

    def _crop_tuple(self):
        c = self.preview.get_crop()
        return (c.x(), c.y(), c.width(), c.height()) if c else None

    def _update_estimate(self):
        if not self.info:
            self.estimate.setText("—")
            return
        w, h = ff.output_dims(self.info["width"], self.info["height"],
                              self._crop_tuple(), self._out_width())
        if self.target_chk.isChecked():
            self.estimate.setText(
                f"目标 ≤ {self.target_spin.value():.1f} MB · {w}×{h}")
            self._est_timer.stop()
            return
        fps = self.fps_spin.value()
        colors = int(self.colors_combo.currentText())
        dither = self.dither_combo.currentData()
        dur = self._dur_sec()
        est = ff.estimate_gif_size(w, h, fps, dur, colors, dither)
        self.estimate.setText(f"约 {human_size(est)}（粗估）· {w}×{h}")
        self._est_timer.start(800)      # 防抖后试编校准，替换为实测值

    def _start_est_probe(self):
        """后台按当前完整参数试编 1 秒外推体积（“实测”标签）。"""
        if not self.video or self._busy or self._is_playing():
            return
        self._est_gen += 1
        gen = self._est_gen
        params = dict(start=self._start_sec(), duration=self._dur_sec(),
                      crop=self._crop_tuple(), width=self._out_width(),
                      fps=self.fps_spin.value(),
                      colors=int(self.colors_combo.currentText()),
                      dither=self.dither_combo.currentData(),
                      deinterlace=self._deint_mode())

        def job():
            return ff.estimate_gif_size_probe(self.video, **params)

        wk = FnWorker(job)
        self._track(wk)
        wk.gen = gen
        wk.done.connect(self._on_est_done)   # 失败不连：静默保留粗估
        wk.start()

    def _on_est_done(self, result):
        wk = self.sender()
        if getattr(wk, "gen", 0) != self._est_gen:
            return
        if self.target_chk.isChecked() or self._busy or not self.video:
            return
        est, _probe_dur = result
        w, h = ff.output_dims(self.info["width"], self.info["height"],
                              self._crop_tuple(), self._out_width())
        self.estimate.setText(f"≈ {human_size(est)}（实测）· {w}×{h}")

    # ================= 输出位置 =================
    def _resolve_outdir(self):
        if self.radio_custom.isChecked() and self.out_edit.text().strip():
            d = self.out_edit.text().strip()
            os.makedirs(d, exist_ok=True)
            return d
        return os.path.dirname(self.video)

    def _out_name(self):
        base = os.path.splitext(os.path.basename(self.video))[0]
        suffix = self.suffix_edit.text().strip() or "_gif"
        return base + suffix + ".gif"

    # ================= 预览 / 保存 =================
    def _do_preview(self):
        if not self.video or self._busy:
            return
        self._stop_playback()
        self._sel_timer.stop()
        self._replay_timer.stop()
        self._back_to_edit()        # 释放上一次预览动画的文件句柄，旧产物才能删掉
        if self._preview_file and os.path.isfile(self._preview_file):
            try:
                os.remove(self._preview_file)
            except OSError:
                pass
        try:                    # 自定义目录此刻就创建并验证，保存时才不会因目录问题失败
            self._resolve_outdir()
        except OSError as e:
            self._status("输出目录不可用：" + str(e), warn=True)
            return
        tmp_dir = os.path.join(tempfile.gettempdir(), "GifKit_preview")
        os.makedirs(tmp_dir, exist_ok=True)
        target = fsutil.unique_path(os.path.join(tmp_dir, self._out_name()))
        params = dict(video=self.video, out_path=target,
                      start=self._start_sec(),
                      duration=self._dur_sec(),    # 时长未知的文件也按界面输入截取
                      crop=self._crop_tuple(), width=self._out_width(),
                      fps=self.fps_spin.value(),
                      colors=int(self.colors_combo.currentText()),
                      dither=self.dither_combo.currentData(),
                      deinterlace=self._deint_mode(),
                      target_mb=(self.target_spin.value()
                                 if self.target_chk.isChecked() else None))
        self._est_timer.stop()
        self._preview_file = target
        self._busy = True
        self.btn_gen.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.pv_meta.setVisible(False)
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)
        self._status("正在生成 GIF（与保存产物完全一致）…")
        self._gen = GifWorker(params)
        self._gen.progress.connect(self.progress.setValue)
        self._gen.ok.connect(self._on_preview_ok)
        self._gen.failed.connect(self._on_gen_failed)
        self._gen.start()

    def _on_preview_ok(self, path, seconds, applied):
        self._busy = False
        self.btn_gen.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress.setVisible(False)
        size = applied["bytes"]
        if self.gif_mode and self.info["size"]:
            pct = max(0.0, (1 - size / self.info["size"]) * 100)
            self.cmp_label.setText(f"原 {human_size(self.info['size'])} → "
                                   f"{human_size(size)}（-{pct:.0f}%）")
        else:
            self.cmp_label.setText(human_size(size))
        self.cmp_label.setVisible(True)
        movie = QMovie(path)
        self._movie = movie
        w, h = ff.output_dims(self.info["width"], self.info["height"],
                              self._crop_tuple(), applied["width"])
        nat = QSize(w, h)
        if nat.width() <= PREVIEW_W and nat.height() <= PREVIEW_H:
            movie.setScaledSize(nat)
        else:
            movie.setScaledSize(nat.scaled(PREVIEW_W, PREVIEW_H, Qt.KeepAspectRatio))
        self.preview_label.setMovie(movie)
        movie.start()
        self.preview_stack.setCurrentIndex(1)
        dur = self._dur_sec()
        adj = ""
        if applied["adjusted"]:
            wt = applied["width"] if applied["width"] else "原始宽度"
            adj = (f"已按目标自动调整：帧率{applied['fps']} · 颜色{applied['colors']}"
                   f" · 宽度{wt}。")
        self.pv_meta.setText(
            f"{os.path.basename(path)} · {w}×{h} · {dur:.1f} 秒 · "
            f"生成用时 {seconds:.1f}s。{adj}确认后点“保存”。")
        self.pv_meta.setVisible(True)
        self.btn_save.setVisible(True)
        self.btn_discard.setVisible(True)
        if applied["adjusted"] and not applied["target_hit"]:
            self._status("已用最小参数仍超目标体积，产物为可达的最小版本", warn=True)
        else:
            self._status("生成完成，请确认后保存")

    def _on_gen_failed(self, msg):
        self._busy = False
        self.btn_gen.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress.setVisible(False)
        if msg == "已取消":
            self._status("已取消生成")
        else:
            self._status(msg, warn=True)

    def _cancel_gen(self):
        if self._gen:
            self._gen.cancel()

    def _save_preview(self):
        if not self._preview_file or not os.path.isfile(self._preview_file):
            self._status("预览产物不存在，请重新生成", warn=True)
            return
        self._back_to_edit()    # 先停掉 QMovie 释放句柄，避免 Windows 下移动文件失败
        try:
            dst = fsutil.unique_path(os.path.join(self._resolve_outdir(),
                                                  self._out_name()))
            install_preview(self._preview_file, dst)
        except OSError as e:
            self._status("保存失败：" + str(e), warn=True)
            return
        self._last_dst = dst
        self.btn_open.setVisible(True)
        self._status(f"已保存：{dst}（{human_size(os.path.getsize(dst))}）")
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)

    def _release_movie(self):
        """彻底停掉预览动画并关闭其文件句柄。

        实测 QMovie.stop()/setMovie(None) 都不会关闭内部 QFile（Qt 6.11），
        句柄不关，Windows 下 move/删除预览文件就会报 WinError 32。
        """
        movie = self.preview_label.movie()
        if movie:
            movie.stop()
            dev = movie.device()
            if dev is not None and dev.isOpen():
                dev.close()
        self.preview_label.setMovie(None)
        self._movie = None

    def _back_to_edit(self):
        self._release_movie()
        self.preview_stack.setCurrentIndex(0)
        self.cmp_label.setVisible(False)
        self.pv_meta.setVisible(False)
        self.btn_save.setVisible(False)
        self.btn_discard.setVisible(False)

    # ================= 其他 =================
    def _track(self, worker):
        self._tmp_workers.append(worker)
        worker.finished.connect(self._on_worker_finished)

    def _on_worker_finished(self):
        wk = self.sender()
        if wk in self._tmp_workers:
            self._tmp_workers.remove(wk)

    def _status(self, text, warn=False):
        self.status.setText(text)
        self.status.setStyleSheet("color:#c50f1f;" if warn else "color:#616161;")

    def _cleanup_temp(self):
        if self._preview_file:
            try:
                os.remove(self._preview_file)
            except OSError:
                pass
            self._preview_file = None
        if self._thumb_dir:
            shutil.rmtree(self._thumb_dir, ignore_errors=True)
            self._thumb_dir = None
        if self._sel_dir:
            shutil.rmtree(self._sel_dir, ignore_errors=True)
            self._sel_dir = None

    # ================= 设置持久化 =================
    def apply_settings(self):
        c = self.cfg
        i = self.width_combo.findData(str(c.get("width_mode", "720")))
        self.width_combo.setCurrentIndex(i if i >= 0 else 0)
        self.width_spin.setValue(int(c.get("width_custom", 720)))
        self.fps_spin.setValue(int(c.get("fps", 12)))
        colors = str(int(c.get("colors", 128)))
        if colors in COLORS:
            self.colors_combo.setCurrentIndex(COLORS.index(colors))
        d = str(c.get("dither", "bayer"))
        di = [v for v, _ in DITHERS].index(d) if d in [v for v, _ in DITHERS] else 0
        self.dither_combo.setCurrentIndex(di)
        dv = str(c.get("deinterlace", "auto"))
        dvi = self.deint_combo.findData(dv)
        self.deint_combo.setCurrentIndex(dvi if dvi >= 0 else 0)
        self.target_chk.setChecked(bool(c.get("target_mode", False)))
        self.target_spin.setValue(float(c.get("target_mb", 2.0)))
        self.suffix_edit.setText(str(c.get("suffix", "_gif")))
        mode = str(c.get("outdir_mode", "source"))
        (self.radio_custom if mode == "custom" else self.radio_src).setChecked(True)
        self.out_edit.setText(str(c.get("outdir", "") or ""))
        self._sync_preset_label()

    def save_settings(self):
        c = self.cfg
        c["width_mode"] = self.width_combo.currentData()
        c["width_custom"] = int(self.width_spin.value())
        c["fps"] = int(self.fps_spin.value())
        c["colors"] = int(self.colors_combo.currentText())
        c["dither"] = self.dither_combo.currentData()
        c["deinterlace"] = self.deint_combo.currentData()
        c["target_mode"] = self.target_chk.isChecked()
        c["target_mb"] = float(self.target_spin.value())
        c["suffix"] = self.suffix_edit.text().strip() or "_gif"
        c["outdir_mode"] = "custom" if self.radio_custom.isChecked() else "source"
        c["outdir"] = self.out_edit.text().strip()

    def shutdown(self):
        """退出前收尾：GifTab 是子页签，closeEvent 不会触发，由 MainWindow 调用。"""
        self._sel_timer.stop()
        self._est_timer.stop()
        self._replay_timer.stop()
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
        if self._gen and self._gen.isRunning():
            self._gen.cancel()      # cancel 会杀掉 ffmpeg，正常毫秒级退出
        shutdown_worker(self._gen, 3000)
        for wk in list(self._tmp_workers):
            shutdown_worker(wk, 1500)
        self._tmp_workers.clear()
        self._release_movie()
        self._cleanup_temp()

    def closeEvent(self, e):
        self.shutdown()
        super().closeEvent(e)


class _ProgressBar(QProgressBar):
    def __init__(self):
        super().__init__()
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setFixedHeight(10)


def _scaled_icon(path, w, h):
    img = QImage(path)
    if img.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(img.scaled(w, h, Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)))
