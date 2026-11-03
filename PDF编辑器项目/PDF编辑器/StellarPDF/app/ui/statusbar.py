"""Bottom status bar with page navigation, view modes and zoom control."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSlider,
    QWidget,
)

from ..icons import icon
from ..theme import C
from .widgets import ToolButton


class StatusBar(QFrame):
    page_requested = Signal(int)
    zoom_requested = Signal(float)
    fit_width_requested = Signal()
    fit_page_requested = Signal()
    view_mode_requested = Signal(str)
    fullscreen_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(32)
        self._count = 0
        self._page = 0
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(3)
        self.hint = QLabel("就绪", self)
        self.hint.setObjectName("StatusHint")
        layout.addWidget(self.hint, 0)
        layout.addStretch(1)

        self.btn_prev = self._button("chevron-left", "上一页", lambda: self.page_requested.emit(self._page - 1))
        self.btn_first = self._button("chevrons-left", "第一页", lambda: self.page_requested.emit(0))
        layout.addWidget(self.btn_first)
        layout.addWidget(self.btn_prev)
        self.page_edit = QLineEdit(self)
        self.page_edit.setFixedWidth(40)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.setStyleSheet(
            "QLineEdit { border:1px solid transparent; background:transparent; padding:1px;"
            "font-size:8.8pt; } QLineEdit:focus { border:1px solid #BFD2FA; background:white; }"
        )
        self.page_edit.returnPressed.connect(self._commit_page)
        self.page_total = QLabel("/ 0", self)
        self.page_total.setObjectName("PageStatus")
        layout.addWidget(self.page_edit)
        layout.addWidget(self.page_total)
        self.btn_next = self._button("chevron-right", "下一页", lambda: self.page_requested.emit(self._page + 1))
        self.btn_last = self._button("chevrons-right", "最后一页", lambda: self.page_requested.emit(self._count - 1))
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_last)
        layout.addSpacing(10)

        self.btn_view = self._button("rows-3", "连续阅读", lambda: self.view_mode_requested.emit("continuous"))
        self.btn_single = self._button("square", "单页阅读", lambda: self.view_mode_requested.emit("single"))
        self.btn_double = self._button("columns-2", "双页阅读", lambda: self.view_mode_requested.emit("double"))
        layout.addWidget(self.btn_view)
        layout.addWidget(self.btn_single)
        layout.addWidget(self.btn_double)
        layout.addSpacing(8)

        self.btn_zoom_out = self._button("zoom-out", "缩小", lambda: self.zoom_requested.emit(-1))
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setFixedWidth(96)
        self.slider.setRange(20, 400)
        self.slider.setValue(100)
        self.slider.setToolTip("缩放")
        self.slider.valueChanged.connect(self._slider_changed)
        layout.addWidget(self.btn_zoom_out)
        layout.addWidget(self.slider)
        self.btn_zoom_in = self._button("zoom-in", "放大", lambda: self.zoom_requested.emit(-2))
        layout.addWidget(self.btn_zoom_in)
        self.zoom_label = QLabel("100%", self)
        self.zoom_label.setFixedWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet("color:#4E5667; font-size:8.8pt;")
        self.zoom_label.setToolTip("点击输入缩放比例")
        layout.addWidget(self.zoom_label)
        fit_width = self._button("move-horizontal", "适合宽度", self.fit_width_requested.emit)
        fit_page = self._button("maximize-2", "适合页面", self.fit_page_requested.emit)
        full = self._button("expand", "全屏 (F11)", self.fullscreen_requested.emit)
        layout.addWidget(fit_width)
        layout.addWidget(fit_page)
        layout.addWidget(full)

    def _button(self, icon_name: str, tip: str, callback) -> ToolButton:
        button = ToolButton(icon_name, color="#5C6577", size=14, parent=self)
        button.setFixedSize(24, 24)
        button.setToolTip(tip)
        button.clicked.connect(callback)
        return button

    def _commit_page(self) -> None:
        try:
            value = int(self.page_edit.text()) - 1
        except ValueError:
            self.set_page(self._page, self._count)
            return
        self.page_requested.emit(max(0, min(value, self._count - 1)))

    def _slider_changed(self, value: int) -> None:
        self.zoom_label.setText(f"{value}%")
        if not self._updating:
            self.zoom_requested.emit(value / 100.0)

    _updating = False

    def set_page(self, page: int, count: int) -> None:
        self._page = max(0, page)
        self._count = max(0, count)
        self.page_edit.setText(str(self._page + 1) if self._count else "0")
        self.page_total.setText(f"/ {self._count}")
        self.btn_prev.setEnabled(self._page > 0)
        self.btn_first.setEnabled(self._page > 0)
        self.btn_next.setEnabled(self._page < self._count - 1)
        self.btn_last.setEnabled(self._page < self._count - 1)
        self.page_edit.setEnabled(self._count > 0)

    def set_zoom(self, zoom: float) -> None:
        value = int(round(zoom * 100))
        value = max(20, min(400, value))
        self._updating = True
        self.slider.setValue(value)
        self.zoom_label.setText(f"{value}%")
        self._updating = False

    def set_view_mode(self, mode: str) -> None:
        for key, button in (
            ("continuous", self.btn_view),
            ("single", self.btn_single),
            ("double", self.btn_double),
        ):
            button.setStyleSheet(
                "QToolButton { background:#EAF1FF; border-radius:4px; }" if key == mode else ""
            )

    def set_message(self, text: str) -> None:
        self.hint.setText(text)

    def set_busy(self, busy: bool, text: str = "正在处理…") -> None:
        if busy:
            self.hint.setText(text)
            self.setCursor(Qt.CursorShape.BusyCursor)

    def set_document_state(self, has_doc: bool) -> None:
        for child in self.findChildren(ToolButton):
            child.setEnabled(has_doc)
        self.slider.setEnabled(has_doc)
        self.page_edit.setEnabled(has_doc)
        self.zoom_label.setEnabled(has_doc)
        if not has_doc:
            self.page_edit.setText("0")
            self.page_total.setText("/ 0")
            self.set_message("本地模式 · 打开 PDF 开始编辑")
