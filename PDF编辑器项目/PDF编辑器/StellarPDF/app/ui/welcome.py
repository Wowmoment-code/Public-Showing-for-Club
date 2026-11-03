"""Welcome / recent documents start page."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_SLOGAN, APP_VERSION
from ..icons import app_icon, icon, pixmap
from ..store import Store
from ..theme import C
from .widgets import ToolButton


class HeroBanner(QWidget):
    open_clicked = Signal()
    new_clicked = Signal()
    merge_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(196)
        self.setObjectName("HeroBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(34, 26, 30, 24)
        layout.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(5)
        badge = QLabel("本地离线 · 无需会员", self)
        badge.setObjectName("Badge")
        badge.setFixedWidth(136)
        left.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        title = QLabel(APP_NAME, self)
        title.setObjectName("WelcomeTitle")
        left.addWidget(title)
        subtitle = QLabel(APP_SLOGAN + "，文字、图片、注释、页面与转换一站完成。", self)
        subtitle.setObjectName("WelcomeSub")
        left.addWidget(subtitle)
        left.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(9)
        open_btn = QPushButton("打开 PDF", self)
        open_btn.setObjectName("Primary")
        open_btn.setFixedHeight(36)
        open_btn.setMinimumWidth(122)
        open_btn.setIcon(icon("folder-open", "white", 17))
        open_btn.clicked.connect(self.open_clicked)
        new_btn = QPushButton("新建 PDF", self)
        new_btn.setFixedHeight(36)
        new_btn.setIcon(icon("file-plus", C.TEXT_SUB, 16))
        new_btn.clicked.connect(self.new_clicked)
        merge_btn = QPushButton("合并 PDF", self)
        merge_btn.setFixedHeight(36)
        merge_btn.setIcon(icon("combine", C.TEXT_SUB, 16))
        merge_btn.clicked.connect(self.merge_clicked)
        row.addWidget(open_btn)
        row.addWidget(new_btn)
        row.addWidget(merge_btn)
        row.addStretch(1)
        left.addLayout(row)
        left.addStretch(1)
        layout.addLayout(left, 1)

        art = QLabel(self)
        art.setFixedSize(190, 142)
        art.setPixmap(app_icon().pixmap(142, 142))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(art, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor("#EEF4FF"))
        gradient.setColorAt(0.55, QColor("#F5F8FF"))
        gradient.setColorAt(1.0, QColor("#FBF7FF"))
        painter.fillRect(rect, gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(47, 107, 255, 16))
        painter.drawEllipse(QPointF(rect.width() - 130, 18), 118, 118)
        painter.setBrush(QColor(122, 90, 248, 12))
        painter.drawEllipse(QPointF(rect.width() - 38, 138), 78, 78)
        painter.setBrush(QColor(255, 255, 255, 150))
        painter.drawEllipse(QPointF(rect.width() - 235, 152), 36, 36)
        painter.end()


class FeatureCard(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        action: str,
        icon_name: str,
        title: str,
        subtitle: str,
        color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.action = action
        self.setObjectName("WelcomeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(11)
        badge = QLabel(self)
        badge.setPixmap(pixmap(icon_name, color, 24))
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background:{color}14; border-radius:9px;")
        layout.addWidget(badge)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title_label = QLabel(title, self)
        title_label.setStyleSheet("font-weight:600; color:#2B3140; font-size:9.6pt;")
        sub_label = QLabel(subtitle, self)
        sub_label.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.2pt;")
        text_layout.addWidget(title_label)
        text_layout.addWidget(sub_label)
        layout.addLayout(text_layout, 1)
        arrow = QLabel(self)
        arrow.setPixmap(pixmap("chevron-right", C.TEXT_MUTED, 15))
        layout.addWidget(arrow)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.action)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(
            "QFrame#WelcomeCard { background:#F8FAFF; border:1px solid #C9DAFF; border-radius:12px; }"
        )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet("")
        super().leaveEvent(event)


class RecentCard(QFrame):
    open_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, entry: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("WelcomeCard")
        self.setFixedWidth(208)
        self.setMinimumHeight(206)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        thumb = QLabel(self)
        thumb.setFixedHeight(112)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("background:#F3F5F9; border-radius:6px; border:1px solid #E8ECF3;")
        thumb_path = entry.get("thumb")
        if thumb_path and os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(180, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                thumb.setPixmap(pixmap("file-pdf", "#B7C1D2", 38))
        else:
            thumb.setPixmap(pixmap("file-pdf", "#B7C1D2", 38))
        layout.addWidget(thumb)
        title = QLabel(entry.get("title") or os.path.basename(entry.get("path", "")), self)
        title.setWordWrap(False)
        title.setStyleSheet("font-weight:600; color:#2B3140; font-size:9.2pt;")
        title.setToolTip(entry.get("title", ""))
        layout.addWidget(title)
        path_label = QLabel(entry.get("path", ""), self)
        path_label.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:7.8pt;")
        path_label.setToolTip(entry.get("path", ""))
        layout.addWidget(path_label)
        meta = QLabel(self)
        opened = entry.get("opened", 0)
        try:
            stamp = time.strftime("%m-%d %H:%M", time.localtime(opened)) if opened else ""
        except Exception:
            stamp = ""
        size = entry.get("size", 0)
        size_text = f"{size / 1024 / 1024:.1f} MB" if size else ""
        meta.setText("  ·  ".join(x for x in (stamp, size_text) if x) or "本地文件")
        meta.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:7.6pt;")
        layout.addWidget(meta)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("打开").triggered.connect(lambda: self.open_requested.emit(self.entry["path"]))
        menu.addAction("从列表移除").triggered.connect(lambda: self.remove_requested.emit(self.entry["path"]))
        menu.exec(self.mapToGlobal(pos))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.entry["path"])
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(
            "QFrame#WelcomeCard { background:#F8FAFF; border:1px solid #C9DAFF; border-radius:12px; }"
        )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet("")
        super().leaveEvent(event)


class WelcomePage(QScrollArea):
    open_requested = Signal()
    new_requested = Signal()
    merge_requested = Signal()
    recent_open = Signal(str)
    recent_remove = Signal(str)
    tool_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { background:#F5F7FB; }")
        self._root = QWidget()
        self._root.setObjectName("WelcomeRoot")
        self._root.setStyleSheet("QWidget#WelcomeRoot { background:#F5F7FB; }")
        self.layout = QVBoxLayout(self._root)
        self.layout.setContentsMargins(26, 22, 26, 24)
        self.layout.setSpacing(18)
        self.setWidget(self._root)

        self.hero = HeroBanner(self._root)
        self.hero.open_clicked.connect(self.open_requested)
        self.hero.new_clicked.connect(self.new_requested)
        self.hero.merge_clicked.connect(self.merge_requested)
        self.layout.addWidget(self.hero)

        self._build_quick_tools()
        self._build_recent()

        footer = QLabel(
            f"{APP_NAME} {APP_VERSION}   ·   本地处理，文件不上传   ·   支持 Windows 10 / 11",
            self._root,
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8pt; padding-top:6px;")
        self.layout.addWidget(footer)
        self.layout.addStretch(1)

    def _build_quick_tools(self) -> None:
        header = QHBoxLayout()
        title = QLabel("常用工具", self._root)
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        hint = QLabel("无需打开文档，直接选择文件即可", self._root)
        hint.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.2pt;")
        header.addWidget(hint)
        self.layout.addLayout(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cards = [
            ("convert.word_pdf", "file-text", "Word 转 PDF", "保留版式，快速输出", C.PRIMARY),
            ("convert.excel_pdf", "file-spreadsheet", "Excel 转 PDF", "表格数据一键排版", C.SUCCESS),
            ("convert.images_pdf", "images", "图片转 PDF", "多图合并为文档", C.ACCENT_WARM),
            ("tools.ocr", "scan-text", "OCR 文字识别", "扫描件变可编辑文字", C.ACCENT),
            ("tools.compress", "archive", "压缩 PDF", "减小体积便于分享", "#0E9CB4"),
            ("protect.encrypt", "lock-keyhole", "加密保护", "密码与权限控制", "#E5484D"),
        ]
        for i, (action, icon_name, title_text, sub, color) in enumerate(cards):
            card = FeatureCard(action, icon_name, title_text, sub, color, self._root)
            card.clicked.connect(self._on_feature)
            grid.addWidget(card, i // 3, i % 3)
        self.layout.addLayout(grid)

    def _on_feature(self, action: str) -> None:
        self.tool_requested.emit(action)

    def _build_recent(self) -> None:
        header = QHBoxLayout()
        title = QLabel("最近打开", self._root)
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.recent_count = QLabel("", self._root)
        self.recent_count.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.2pt;")
        header.addWidget(self.recent_count)
        clear = QPushButton("清空列表", self._root)
        clear.setObjectName("LinkButton")
        clear.clicked.connect(self._clear_recent)
        header.addWidget(clear)
        self.layout.addLayout(header)
        self.recent_container = QWidget(self._root)
        self.recent_layout = QHBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(10)
        self.recent_layout.addStretch(1)
        self.layout.addWidget(self.recent_container)
        self.empty_recent = QFrame(self._root)
        self.empty_recent.setObjectName("WelcomeCard")
        self.empty_recent.setMinimumHeight(110)
        empty_layout = QVBoxLayout(self.empty_recent)
        empty_layout.setContentsMargins(20, 18, 20, 18)
        empty_layout.setSpacing(4)
        empty_title = QLabel("还没有最近文档", self.empty_recent)
        empty_title.setStyleSheet("font-weight:600; color:#495266;")
        empty_sub = QLabel("打开一个 PDF，或把文件拖到窗口中，即可开始。", self.empty_recent)
        empty_sub.setStyleSheet(f"color:{C.TEXT_MUTED};")
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_sub)
        open_btn = QPushButton("选择 PDF 文件", self.empty_recent)
        open_btn.setFixedWidth(132)
        open_btn.clicked.connect(self.open_requested)
        empty_layout.addWidget(open_btn)
        self.layout.addWidget(self.empty_recent)

    def _clear_recent(self) -> None:
        self.recent_remove.emit("__clear__")

    def set_recent(self, entries: Sequence[dict[str, Any]]) -> None:
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not entries:
            self.empty_recent.show()
            self.recent_container.hide()
            self.recent_count.setText("")
            self.recent_layout.addStretch(1)
            return
        self.empty_recent.hide()
        self.recent_container.show()
        for entry in entries[:6]:
            card = RecentCard(entry, self.recent_container)
            card.open_requested.connect(self.recent_open)
            card.remove_requested.connect(self.recent_remove)
            self.recent_layout.addWidget(card)
        self.recent_layout.addStretch(1)
        self.recent_count.setText(f"{len(entries)} 个文档")

    def refresh(self, store: Store) -> None:
        self.set_recent(store.recent)
