"""「图片压缩」页：批量拖入 → 压缩/格式转换 → 前后体积对比。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QRadioButton, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import ffmpeg as ff
from core import imglib
from core.workers import ImgWorker
from utils import fsutil
from utils.timefmt import human_size

FORMATS = [("keep", "保持原格式"), ("jpeg", "JPEG"), ("webp", "WebP（更小）"), ("png", "PNG")]
EDGES = [("0", "保持原始尺寸"), ("2560", "2560"), ("1920", "1920"),
         ("1280", "1280"), ("800", "800"), ("c", "自定义…")]


class ImageTab(QWidget):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.files = []          # 与表格行一一对应
        self._worker = None
        self._last_dst_dir = None
        self._build_ui()
        self.apply_settings()

    def _build_ui(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        right_w = QWidget()
        right_w.setFixedWidth(352)
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 0, 0)
        root.addLayout(left, 1)
        root.addWidget(right_w)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件", "原大小", "压缩后", "节省", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 80)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAcceptDrops(True)
        self.table.setWordWrap(False)
        self.table.dragEnterEvent = self._table_drag_enter
        self.table.dropEvent = self._table_drop
        left.addWidget(self.table, 1)

        brow = QHBoxLayout()
        self.btn_add = QPushButton("添加图片…")
        self.btn_add.clicked.connect(self._add_dialog)
        brow.addWidget(self.btn_add)
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        brow.addWidget(self.btn_remove)
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._clear)
        brow.addWidget(self.btn_clear)
        brow.addStretch(1)
        left.addLayout(brow)

        self.summary = QLabel("将图片拖到列表中，或点“添加图片”")
        self.summary.setStyleSheet("color:#616161;")
        left.addWidget(self.summary)

        fbox = QGroupBox("压缩 / 转换设置")
        fv = QVBoxLayout(fbox)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("输出格式"))
        self.fmt_combo = QComboBox()
        for val, name in FORMATS:
            self.fmt_combo.addItem(name, val)
        self.fmt_combo.currentIndexChanged.connect(self._on_fmt)
        fmt_row.addWidget(self.fmt_combo, 1)
        fv.addLayout(fmt_row)
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("质量"))
        self.q_slider = QSlider(Qt.Horizontal)
        self.q_slider.setRange(10, 100)
        self.q_slider.setValue(80)
        self.q_slider.valueChanged.connect(lambda v: self.q_val.setText(str(v)))
        q_row.addWidget(self.q_slider, 1)
        self.q_val = QLabel("80")
        q_row.addWidget(self.q_val)
        fv.addLayout(q_row)
        e_row = QHBoxLayout()
        e_row.addWidget(QLabel("最长边"))
        self.edge_combo = QComboBox()
        for val, name in EDGES:
            self.edge_combo.addItem(name, val)
        self.edge_combo.currentIndexChanged.connect(self._on_edge)
        e_row.addWidget(self.edge_combo, 1)
        self.edge_spin = QSpinBox()
        self.edge_spin.setRange(64, 8192)
        self.edge_spin.setValue(1920)
        self.edge_spin.setVisible(False)
        e_row.addWidget(self.edge_spin)
        fv.addLayout(e_row)
        self.quant_chk = QCheckBox("PNG 256 色量化（截图、UI 图推荐）")
        self.quant_chk.setChecked(True)
        fv.addWidget(self.quant_chk)
        self.skip_chk = QCheckBox("自动跳过“压缩后反而变大”的文件")
        self.skip_chk.setChecked(True)
        fv.addWidget(self.skip_chk)
        right.addWidget(fbox)

        obox = QGroupBox("输出位置")
        ov = QVBoxLayout(obox)
        orow = QHBoxLayout()
        self.radio_src = QRadioButton("源文件目录")
        self.radio_custom = QRadioButton("自定义…")
        grp = QButtonGroup(self)
        grp.addButton(self.radio_src)
        grp.addButton(self.radio_custom)
        orow.addWidget(self.radio_src)
        orow.addWidget(self.radio_custom)
        orow.addStretch(1)
        ov.addLayout(orow)
        drow = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("自定义输出目录")
        self.out_edit.setEnabled(False)
        drow.addWidget(self.out_edit, 1)
        self.btn_browse = QPushButton("…")
        self.btn_browse.setFixedWidth(32)
        self.btn_browse.clicked.connect(self._browse_outdir)
        drow.addWidget(self.btn_browse)
        ov.addLayout(drow)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("文件后缀"))
        self.suffix_edit = QLineEdit("_c")
        self.suffix_edit.setFixedWidth(80)
        srow.addWidget(self.suffix_edit)
        srow.addWidget(QLabel("如 photo.jpg → photo_c.jpg"))
        srow.addStretch(1)
        ov.addLayout(srow)
        right.addWidget(obox)

        gbox = QGroupBox("执行")
        gv = QVBoxLayout(gbox)
        self.btn_go = QPushButton("开始压缩")
        self.btn_go.setObjectName("genBtn")
        self.btn_go.clicked.connect(self._start)
        gv.addWidget(self.btn_go)
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.setVisible(False)
        self.btn_open.clicked.connect(
            lambda: fsutil.open_in_explorer(self._last_dst_dir))
        gv.addWidget(self.btn_open)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#616161;")
        self.status.setWordWrap(True)
        gv.addWidget(self.status)
        right.addWidget(gbox)
        right.addStretch(1)

        self.setAcceptDrops(True)

    # ---------- 添加文件 ----------
    def _add_dialog(self):
        exts = " ".join("*" + e for e in sorted(ff.IMAGE_EXTS))
        paths, _ = QFileDialog.getOpenFileNames(self, "选择图片", "",
                                                f"图片 ({exts});;所有文件 (*)")
        if paths:
            self.add_files(paths)

    def _table_drag_enter(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def _table_drop(self, e):
        self._handle_drop(e.mimeData().urls())
        e.acceptProposedAction()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self._handle_drop(e.mimeData().urls())
        e.acceptProposedAction()

    def _handle_drop(self, urls):
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        imgs = [p for p in paths if os.path.splitext(p)[1].lower() in ff.IMAGE_EXTS]
        others = len(paths) - len(imgs)
        if others:
            self._status(f"已忽略 {others} 个非图片文件")
        self.add_files(imgs)

    def add_files(self, paths):
        for p in paths:
            ap = os.path.abspath(p)
            if ap in self.files or not os.path.isfile(ap):
                continue
            self.files.append(ap)
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(os.path.basename(ap))
            name_item.setToolTip(ap)
            self.table.setItem(r, 0, name_item)
            try:
                size_txt = human_size(os.path.getsize(ap))
            except OSError:
                size_txt = "—"
            self.table.setItem(r, 1, QTableWidgetItem(size_txt))
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem("—"))
            self.table.setItem(r, 4, QTableWidgetItem("待处理"))
        self._update_summary()

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.files[r]
            self.table.removeRow(r)
        self._update_summary()

    def _clear(self):
        self.files.clear()
        self.table.setRowCount(0)
        self._update_summary()

    def _update_summary(self):
        n = len(self.files)
        self.summary.setText(f"共 {n} 个文件" if n else
                             "将图片拖到列表中，或点“添加图片”")

    # ---------- 参数 ----------
    def _on_fmt(self):
        self.q_slider.setEnabled(self.fmt_combo.currentData() != "png")

    def _on_edge(self):
        self.edge_spin.setVisible(self.edge_combo.currentData() == "c")

    def _browse_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.radio_custom.setChecked(True)

    # ---------- 执行 ----------
    def _start(self):
        if not self.files:
            self._status("请先添加图片", warn=True)
            return
        if self._worker and self._worker.isRunning():
            return
        for r in range(self.table.rowCount()):
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem("—"))
            self.table.setItem(r, 4, QTableWidgetItem("待处理"))
        opt = {
            "fmt": self.fmt_combo.currentData(),
            "quality": int(self.q_slider.value()),
            "max_edge": int(self.edge_spin.value()) if self.edge_combo.currentData() == "c"
            else int(self.edge_combo.currentData()),
            "quantize_png": self.quant_chk.isChecked(),
            "skip_larger": self.skip_chk.isChecked(),
            "suffix": self.suffix_edit.text().strip() or "_c",
            "outdir_mode": "custom" if self.radio_custom.isChecked() else "source",
            "outdir": self.out_edit.text().strip(),
        }
        self.btn_go.setEnabled(False)
        self.btn_add.setEnabled(False)      # 运行中禁用会改动行号/列表的操作，
        self.btn_remove.setEnabled(False)   # 防止结果写错行
        self.btn_clear.setEnabled(False)
        self._status("压缩中…")
        self._worker = ImgWorker(self.files, opt)
        self._worker.row.connect(self._on_row)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def _set_running(self, running):
        for b in (self.btn_add, self.btn_remove, self.btn_clear):
            b.setEnabled(not running)

    def _on_progress(self, v):
        self._status(f"压缩中… {v}%")

    def _on_worker_failed(self, msg):
        self._fail(msg)

    def _on_row(self, i, res):
        if i >= self.table.rowCount():
            return
        if "error" in res:
            self.table.setItem(i, 4, QTableWidgetItem("失败：" + res["error"][:60]))
            return
        saving = (1 - res["new"] / res["orig"]) * 100 if res["orig"] else 0
        self.table.setItem(i, 2, QTableWidgetItem(human_size(res["new"])))
        s_item = QTableWidgetItem(f"-{saving:.1f}%" if saving >= 0 else f"+{-saving:.1f}%")
        s_item.setForeground(QBrush(QColor("#0e700e") if saving >= 0 else QColor("#c50f1f")))
        self.table.setItem(i, 3, s_item)
        kind_txt = imglib.EXT_BY_KIND.get(res["kind"], res["kind"]).lstrip(".")
        self.table.setItem(i, 4, QTableWidgetItem("已跳过（未减小）" if res["skipped"]
                                                   else f"完成 → {kind_txt.upper()}"))
        self._last_dst_dir = os.path.dirname(res["dst"]) or self._last_dst_dir

    def _on_done(self, ok_n, skip_n):
        self.btn_go.setEnabled(True)
        self._set_running(False)
        self.btn_open.setVisible(True)
        self._status(f"完成：{ok_n} 个已压缩" + (f"，{skip_n} 个已跳过" if skip_n else ""))
        self._update_summary_totals()

    def _fail(self, msg):
        self.btn_go.setEnabled(True)
        self._set_running(False)
        self._status("失败：" + msg, warn=True)

    def _update_summary_totals(self):
        saved = 0
        n = 0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 3)
            if item and item.text().startswith("-"):
                try:
                    orig = self.files[r]
                    new_txt = self.table.item(r, 2).text()
                    saved += self._approx_size(orig) - self._parse_size(new_txt)
                    n += 1
                except (OSError, ValueError):
                    pass
        if n:
            self.summary.setText(f"共 {len(self.files)} 个文件，{n} 个已压缩，"
                                 f"共节省 {human_size(max(0, saved))}")

    @staticmethod
    def _approx_size(path):
        return os.path.getsize(path)

    @staticmethod
    def _parse_size(text):
        num, unit = text.split(" ")
        mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
                "TB": 1024 ** 4}[unit]
        return int(float(num) * mult)

    def _status(self, text, warn=False):
        self.status.setText(text)
        self.status.setStyleSheet("color:#c50f1f;" if warn else "color:#616161;")

    # ---------- 设置持久化 ----------
    def apply_settings(self):
        c = self.cfg
        i = self.fmt_combo.findData(str(c.get("fmt", "keep")))
        self.fmt_combo.setCurrentIndex(i if i >= 0 else 0)
        self.q_slider.setValue(int(c.get("quality", 80)))
        j = self.edge_combo.findData(str(c.get("max_edge_mode", "0")))
        self.edge_combo.setCurrentIndex(j if j >= 0 else 0)
        self.edge_spin.setValue(int(c.get("max_edge_custom", 1920)))
        self.quant_chk.setChecked(bool(c.get("quantize_png", True)))
        self.skip_chk.setChecked(bool(c.get("skip_larger", True)))
        self.suffix_edit.setText(str(c.get("suffix", "_c")))
        mode = str(c.get("outdir_mode", "source"))
        (self.radio_custom if mode == "custom" else self.radio_src).setChecked(True)
        self.out_edit.setText(str(c.get("outdir", "") or ""))

    def shutdown(self):
        """退出前收尾：等待/取消后台压缩线程，避免线程在解释器退出时仍存活。"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)

    def save_settings(self):
        c = self.cfg
        c["fmt"] = self.fmt_combo.currentData()
        c["quality"] = int(self.q_slider.value())
        c["max_edge_mode"] = self.edge_combo.currentData()
        c["max_edge_custom"] = int(self.edge_spin.value())
        c["quantize_png"] = self.quant_chk.isChecked()
        c["skip_larger"] = self.skip_chk.isChecked()
        c["suffix"] = self.suffix_edit.text().strip() or "_c"
        c["outdir_mode"] = "custom" if self.radio_custom.isChecked() else "source"
        c["outdir"] = self.out_edit.text().strip()
