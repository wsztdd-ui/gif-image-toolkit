"""v0.3 UI 简化用的通用小组件。

Collapsible —— 箭头式折叠分区（「高级参数」「高级选项」），默认收起。
OutputLocation —— 「保存到：和源文件相同的位置 ·更改」一行，点"更改"才展开
目录单选与路径框。对外暴露 radio_src / radio_custom / out_edit，
配置字段与 v0.2 完全一致（outdir_mode / outdir），老配置升级无感。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QRadioButton, QToolButton,
                               QVBoxLayout, QWidget)


class Collapsible(QWidget):
    """「▶ 高级参数」式折叠区：标题行 + 缩进的内容容器。"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.btn = QToolButton(text=title, checkable=True, checked=False,
                               arrowType=Qt.RightArrow,
                               toolButtonStyle=Qt.ToolButtonTextBesideIcon)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(
            "QToolButton{border:none;background:transparent;color:#616161;"
            "font-weight:600;padding:2px 0;}"
            "QToolButton:hover{color:#0f6cbd;}")
        self.body = QWidget()
        self.body.setStyleSheet("background:transparent;")
        bv = QVBoxLayout(self.body)
        bv.setContentsMargins(16, 0, 0, 0)
        bv.setSpacing(6)
        self.body.setVisible(False)
        v.addWidget(self.btn)
        v.addWidget(self.body)
        self.btn.toggled.connect(self._on_toggle)
        self.add_layout = bv.addLayout
        self.add_widget = bv.addWidget

    def _on_toggle(self, on):
        self.btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)


class OutputLocation(QWidget):
    """输出位置：默认一行小字，点「更改」才展开目录单选与路径框。"""

    def __init__(self, same_text, parent=None):
        super().__init__(parent)
        self._same_text = same_text
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("保存到："))
        self.loc_label = QLabel(same_text)
        row.addWidget(self.loc_label)
        self.btn_change = QPushButton("更改")
        self.btn_change.setObjectName("linkBtn")
        self.btn_change.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_change)
        row.addStretch(1)
        v.addLayout(row)

        self.panel = QWidget()
        self.panel.setStyleSheet("background:transparent;")
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(6)
        rrow = QHBoxLayout()
        self.radio_src = QRadioButton(same_text)
        self.radio_custom = QRadioButton("自定义目录…")
        rrow.addWidget(self.radio_src)
        rrow.addWidget(self.radio_custom)
        rrow.addStretch(1)
        pv.addLayout(rrow)
        drow = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("自定义输出目录")
        self.out_edit.setEnabled(False)
        self.btn_browse = QPushButton("…")
        self.btn_browse.setFixedWidth(32)
        drow.addWidget(self.out_edit, 1)
        drow.addWidget(self.btn_browse)
        pv.addLayout(drow)
        self.panel.setVisible(False)
        v.addWidget(self.panel)

        self.btn_change.clicked.connect(self._toggle)
        self.btn_browse.clicked.connect(self._browse)
        self.radio_src.toggled.connect(self._sync)
        self.radio_custom.toggled.connect(self._sync)
        self.out_edit.textChanged.connect(self._sync)

    def _toggle(self):
        self.panel.setVisible(not self.panel.isVisible())

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.radio_custom.setChecked(True)

    def _sync(self):
        if self.radio_custom.isChecked():
            txt = self.out_edit.text().strip() or "自定义目录"
        else:
            txt = self._same_text
        self.loc_label.setText(txt)
