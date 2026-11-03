"""Custom title bar with quick access toolbar and window controls."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION
from ..icons import app_icon, icon, pixmap
from ..theme import C
from .widgets import Avatar, ElidedLabel, ToolButton


class TitleBar(QWidget):
    open_clicked = Signal()
    save_clicked = Signal()
    undo_clicked = Signal()
    redo_clicked = Signal()
    print_clicked = Signal()
    search_requested = Signal(str)
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()
    local_clicked = Signal()
    menu_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(44)
        self._build()
        self._maximized = False

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 0, 0, 0)
        layout.setSpacing(3)

        logo = QLabel(self)
        logo.setPixmap(app_icon().pixmap(24, 24))
        logo.setFixedSize(26, 26)
        logo.setScaledContents(True)
        layout.addWidget(logo)
        app_name = QLabel(APP_NAME, self)
        app_name.setObjectName("AppName")
        app_name.setContentsMargins(2, 0, 4, 0)
        layout.addWidget(app_name)
        self.btn_menu = ToolButton("menu", color="#5C6577", size=17, parent=self)
        self.btn_menu.setFixedSize(28, 28)
        self.btn_menu.setToolTip("文件菜单与更多操作")
        self.btn_menu.clicked.connect(self.menu_clicked)
        layout.addWidget(self.btn_menu)
        self._build_rest(layout)

    def _build_rest(self, layout: QHBoxLayout) -> None:
        sep = QWidget(self)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{C.BORDER}; margin: 10px 4px;")
        layout.addWidget(sep)

        self.btn_open = self._quick("folder-open", "打开 (Ctrl+O)", self.open_clicked)
        self.btn_save = self._quick("save", "保存 (Ctrl+S)", self.save_clicked)
        self.btn_print = self._quick("printer", "打印 (Ctrl+P)", self.print_clicked)
        self.btn_undo = self._quick("undo-2", "撤销 (Ctrl+Z)", self.undo_clicked)
        self.btn_redo = self._quick("redo-2", "重做 (Ctrl+Y)", self.redo_clicked)
        for button in (self.btn_open, self.btn_save, self.btn_print, self.btn_undo, self.btn_redo):
            layout.addWidget(button)

        self.title_label = ElidedLabel("未打开文档", self)
        self.title_label.setObjectName("DocTitle")
        self.title_label.setContentsMargins(12, 0, 8, 0)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title_label, 1)

        self.search = QLineEdit(self)
        self.search.setObjectName("TitleSearch")
        self.search.setPlaceholderText("搜索文档内容  Ctrl+F")
        self.search.setFixedWidth(204)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", C.TEXT_MUTED, 15), QLineEdit.ActionPosition.LeadingPosition)
        self.search.returnPressed.connect(lambda: self.search_requested.emit(self.search.text()))
        self.search.setEnabled(False)
        layout.addWidget(self.search, 0)

        self.local_badge = QToolButton(self)
        self.local_badge.setObjectName("LocalBadge")
        self.local_badge.setText("●  本地模式")
        self.local_badge.setToolTip("所有编辑与 OCR 均在本机完成，文件不会上传")
        self.local_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.local_badge.setStyleSheet(
            "QToolButton { color:#1B8A63; background:#EAF8F1; border:1px solid #CFEDDF;"
            "border-radius:10px; padding:2px 9px; font-size:8pt; }"
            "QToolButton:hover { background:#DFF4EA; }"
        )
        self.local_badge.clicked.connect(self.local_clicked)
        layout.addWidget(self.local_badge, 0)

        avatar = Avatar("星", self)
        avatar.setToolTip("星澜 PDF 本地账户")
        layout.addWidget(avatar)
        layout.addSpacing(7)

        self.btn_min = self._window_button("minus", "最小化", self.minimize_clicked)
        self.btn_max = self._window_button("square", "最大化", self.maximize_clicked)
        self.btn_close = self._window_button("x", "关闭", self.close_clicked, close=True)
        for button in (self.btn_min, self.btn_max, self.btn_close):
            layout.addWidget(button)

    def _quick(self, icon_name: str, tip: str, signal) -> QToolButton:
        button = ToolButton(icon_name, color="#5C6577", size=17, parent=self)
        button.setFixedSize(28, 28)
        button.setToolTip(tip)
        button.clicked.connect(signal)
        return button

    def _window_button(self, icon_name: str, tip: str, signal, close: bool = False) -> QToolButton:
        button = ToolButton(icon_name, color="#4B5261", size=15, parent=self)
        button.setObjectName("CloseButton" if close else "WindowButton")
        button.setFixedSize(46, 38)
        button.setIconSize(QSize(15, 15))
        button.setToolTip(tip)
        button.clicked.connect(signal)
        return button

    # ------------------------------------------------------------------ state
    def set_document(self, title: str, dirty: bool = False, has_doc: bool = True) -> None:
        if has_doc:
            suffix = "  •" if dirty else ""
            self.title_label.setText(f"{title}{suffix}")
            self.setToolTip(f"{APP_NAME} {APP_VERSION}\n{title}")
        else:
            self.title_label.setText("未打开文档")
            self.setToolTip(f"{APP_NAME} {APP_VERSION}")
        self.search.setEnabled(has_doc)
        if not has_doc:
            self.search.clear()

    def set_history(self, can_undo: bool, can_redo: bool) -> None:
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)

    def set_maximized(self, value: bool) -> None:
        self._maximized = value
        self.btn_max.set_icon("copy" if value else "square", "#4B5261", 14)
        self.btn_max.setToolTip("还原" if value else "最大化")

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # -------------------------------------------------------------- dragging
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
