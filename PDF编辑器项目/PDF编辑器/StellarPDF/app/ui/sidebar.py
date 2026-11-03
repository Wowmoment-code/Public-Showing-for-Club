"""Left navigation rail and task panes (thumbnails, bookmarks, comments, search)."""
from __future__ import annotations

import os
from typing import Any, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.document import AnnotInfo, SearchHit, WidgetInfo
from ..icons import icon, pixmap
from ..theme import C
from .widgets import ToolButton


class RailButton(ToolButton):
    def __init__(self, icon_name: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(icon_name, color=C.TEXT_SUB, size=19, checkable=True, parent=parent)
        self.setObjectName("RailButton")
        self.setFixedSize(40, 40)
        self.setToolTip(text)
        self.setIconSize(QSize(19, 19))


class Sidebar(QWidget):
    page_selected = Signal(int)
    pages_selected = Signal(list)
    add_page_requested = Signal()
    delete_pages_requested = Signal()
    rotate_page_requested = Signal()
    page_reordered = Signal(int, int)
    page_order_changed = Signal(list)
    extract_pages_requested = Signal()
    bookmark_selected = Signal(int)
    bookmark_add_requested = Signal()
    bookmark_delete_requested = Signal()
    annot_selected = Signal(int, int)
    annot_delete_requested = Signal()
    annot_export_requested = Signal()
    attachment_add_requested = Signal()
    attachment_save_requested = Signal(str)
    attachment_delete_requested = Signal(str)
    search_requested = Signal(str)
    search_hit_selected = Signal(int)
    form_fill_requested = Signal()
    form_manage_requested = Signal()
    panel_toggled = Signal(bool)

    PANELS = [
        ("thumbs", "页面缩略图", "layout-grid", "页面"),
        ("bookmarks", "书签", "bookmark", "书签"),
        ("annots", "批注", "message-square-text", "批注"),
        ("forms", "表单", "text-cursor-input", "表单"),
        ("attachments", "附件", "paperclip", "附件"),
        ("search", "搜索", "search", "搜索"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarHost")
        self._thumb_queue: list[int] = []
        self._rendered_thumbs: set[int] = set()
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(30)
        self._thumb_timer.timeout.connect(self._render_next_thumb)
        self._current_panel = "thumbs"
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        rail = QWidget(self)
        rail.setObjectName("LeftRail")
        rail.setFixedWidth(48)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(4, 8, 4, 8)
        rail_layout.setSpacing(1)
        self.rail_buttons: dict[str, RailButton] = {}
        for key, label, icon_name, short in self.PANELS:
            button = RailButton(icon_name, label, rail)
            button.clicked.connect(lambda checked=False, k=key: self._on_rail(k))
            rail_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.rail_buttons[key] = button
        rail_layout.addSpacing(6)
        line = QFrame(rail)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{C.BORDER}; margin:3px 8px;")
        rail_layout.addWidget(line)
        zoom_btn = RailButton("maximize-2", "适合宽度", rail)
        zoom_btn.setCheckable(False)
        zoom_btn.clicked.connect(lambda: self.page_selected.emit(-1))
        rail_layout.addWidget(zoom_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        rail_layout.addStretch(1)
        layout.addWidget(rail)

        self.panel = QWidget(self)
        self.panel.setObjectName("SidePanel")
        self.panel.setFixedWidth(216)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(8, 10, 8, 8)
        panel_layout.setSpacing(6)
        header = QHBoxLayout()
        self.panel_title = QLabel("页面", self.panel)
        self.panel_title.setObjectName("PanelTitle")
        header.addWidget(self.panel_title)
        header.addStretch(1)
        self.panel_count = QLabel("", self.panel)
        self.panel_count.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8pt;")
        header.addWidget(self.panel_count)
        self.hide_btn = ToolButton("chevron-left", color=C.TEXT_MUTED, size=14, parent=self.panel)
        self.hide_btn.setFixedSize(22, 22)
        self.hide_btn.setToolTip("收起侧栏")
        self.hide_btn.clicked.connect(self.collapse)
        header.addWidget(self.hide_btn)
        panel_layout.addLayout(header)

        self.stack = QStackedWidget(self.panel)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self._build_thumbs())
        self.stack.addWidget(self._build_bookmarks())
        self.stack.addWidget(self._build_annots())
        self.stack.addWidget(self._build_forms())
        self.stack.addWidget(self._build_attachments())
        self.stack.addWidget(self._build_search())
        panel_layout.addWidget(self.stack, 1)
        layout.addWidget(self.panel)
        self.rail_buttons["thumbs"].setChecked(True)
        self.set_document(None)

    # ------------------------------------------------------------------ tabs
    def _build_thumbs(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.thumb_list = QListWidget(page)
        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setIconSize(QSize(128, 162))
        self.thumb_list.setGridSize(QSize(172, 194))
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumb_list.setMovement(QListWidget.Movement.Static)
        self.thumb_list.setSpacing(2)
        self.thumb_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumb_list.setUniformItemSizes(True)
        self.thumb_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumb_list.verticalScrollBar().setSingleStep(32)
        self.thumb_list.setDragEnabled(True)
        self.thumb_list.setAcceptDrops(True)
        self.thumb_list.setDropIndicatorShown(True)
        self.thumb_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.thumb_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._reordering = False
        self.thumb_list.model().rowsMoved.connect(self._on_rows_moved)
        self.thumb_list.setStyleSheet(
            "QListWidget { background:transparent; }"
            "QListWidget::item { border:1px solid transparent; border-radius:5px; padding:4px; }"
            "QListWidget::item:selected { background:#EAF1FF; border:1px solid #9CC0FF; color:#1F4FC4; }"
        )
        self.thumb_list.currentRowChanged.connect(self._thumb_current)
        self.thumb_list.itemSelectionChanged.connect(self._thumb_selection)
        self.thumb_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumb_list.customContextMenuRequested.connect(self._thumb_menu)
        self.thumb_list.verticalScrollBar().valueChanged.connect(self._queue_visible_thumbs)
        layout.addWidget(self.thumb_list, 1)
        row = QHBoxLayout()
        row.setSpacing(4)
        add = ToolButton("plus", color=C.TEXT_SUB, size=16, parent=page)
        add.setFixedSize(28, 26)
        add.setToolTip("插入页面")
        add.clicked.connect(self.add_page_requested)
        delete = ToolButton("trash-2", color=C.TEXT_SUB, size=16, parent=page)
        delete.setFixedSize(28, 26)
        delete.setToolTip("删除选中页面")
        delete.clicked.connect(self.delete_pages_requested)
        rotate = ToolButton("rotate-cw", color=C.TEXT_SUB, size=16, parent=page)
        rotate.setFixedSize(28, 26)
        rotate.setToolTip("旋转选中页面")
        rotate.clicked.connect(self.rotate_page_requested)
        row.addStretch(1)
        row.addWidget(add)
        row.addWidget(delete)
        row.addWidget(rotate)
        layout.addLayout(row)
        return page

    def _build_bookmarks(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.bookmark_tree = QTreeWidget(page)
        self.bookmark_tree.setHeaderHidden(True)
        self.bookmark_tree.setIndentation(14)
        self.bookmark_tree.setStyleSheet("QTreeWidget { background:transparent; }")
        self.bookmark_tree.itemDoubleClicked.connect(self._bookmark_clicked)
        layout.addWidget(self.bookmark_tree, 1)
        row = QHBoxLayout()
        add = QPushButton("添加书签", page)
        add.clicked.connect(self.bookmark_add_requested)
        delete = QPushButton("删除", page)
        delete.clicked.connect(self.bookmark_delete_requested)
        row.addWidget(add)
        row.addWidget(delete)
        layout.addLayout(row)
        return page

    def _build_annots(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.annot_filter = QComboBox(page)
        self.annot_filter.addItems(["全部批注", "文本标注", "便签批注", "手绘与图形"])
        self.annot_filter.currentIndexChanged.connect(self._filter_annots)
        layout.addWidget(self.annot_filter)
        self.annot_list = QListWidget(page)
        self.annot_list.setStyleSheet(
            "QListWidget { background:transparent; }"
            "QListWidget::item { border:1px solid #EDF0F5; border-radius:6px; padding:7px; margin:2px 0; }"
            "QListWidget::item:selected { background:#EAF1FF; border-color:#BFD4FF; }"
        )
        self.annot_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.annot_list.itemClicked.connect(self._annot_clicked)
        layout.addWidget(self.annot_list, 1)
        row = QHBoxLayout()
        export = QPushButton("导出", page)
        export.clicked.connect(self.annot_export_requested)
        delete = QPushButton("删除", page)
        delete.clicked.connect(self.annot_delete_requested)
        row.addWidget(export)
        row.addWidget(delete)
        layout.addLayout(row)
        return page

    def _build_forms(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.form_list = QListWidget(page)
        self.form_list.setStyleSheet("QListWidget { background:transparent; }")
        self.form_list.itemDoubleClicked.connect(lambda _: self.form_fill_requested.emit())
        layout.addWidget(self.form_list, 1)
        row = QHBoxLayout()
        fill = QPushButton("填写表单", page)
        fill.setObjectName("Primary")
        fill.clicked.connect(self.form_fill_requested)
        manage = QPushButton("字段信息", page)
        manage.clicked.connect(self.form_manage_requested)
        row.addWidget(fill)
        row.addWidget(manage)
        layout.addLayout(row)
        return page

    def _build_attachments(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.attach_list = QListWidget(page)
        self.attach_list.setStyleSheet("QListWidget { background:transparent; }")
        self.attach_list.itemDoubleClicked.connect(
            lambda item: self.attachment_save_requested.emit(item.data(Qt.ItemDataRole.UserRole) or "")
        )
        layout.addWidget(self.attach_list, 1)
        row = QHBoxLayout()
        add = QPushButton("添加", page)
        add.clicked.connect(self.attachment_add_requested)
        save = QPushButton("保存", page)
        save.clicked.connect(
            lambda: self.attachment_save_requested.emit(
                (self.attach_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.attach_list.currentItem() else "")
            )
        )
        delete = QPushButton("删除", page)
        delete.clicked.connect(
            lambda: self.attachment_delete_requested.emit(
                (self.attach_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.attach_list.currentItem() else "")
            )
        )
        row.addWidget(add)
        row.addWidget(save)
        row.addWidget(delete)
        layout.addLayout(row)
        return page

    def _build_search(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QHBoxLayout()
        self.search_edit = QLineEdit(page)
        self.search_edit.setPlaceholderText("搜索文档内容")
        self.search_edit.returnPressed.connect(self._do_search)
        search_btn = QPushButton("搜索", page)
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(self.search_edit, 1)
        row.addWidget(search_btn)
        layout.addLayout(row)
        self.search_info = QLabel("输入关键词开始搜索", page)
        self.search_info.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8pt;")
        layout.addWidget(self.search_info)
        self.search_list = QListWidget(page)
        self.search_list.setStyleSheet(
            "QListWidget { background:transparent; }"
            "QListWidget::item { padding:7px; border-bottom:1px solid #EEF1F6; }"
            "QListWidget::item:selected { background:#EAF1FF; }"
        )
        self.search_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.search_list.itemClicked.connect(self._search_clicked)
        layout.addWidget(self.search_list, 1)
        return page

    # ---------------------------------------------------------------- public
    def set_document(self, doc) -> None:
        self._doc = doc
        self._thumb_timer.stop()
        self._thumb_queue.clear()
        self._rendered_thumbs.clear()
        self.thumb_list.clear()
        self.bookmark_tree.clear()
        self.annot_list.clear()
        self.form_list.clear()
        self.attach_list.clear()
        self.search_list.clear()
        self.panel_count.setText("")
        if doc is None:
            self.panel_count.setText("—")
            return
        self.panel_count.setText(f"{doc.page_count} 页")
        for i in range(doc.page_count):
            item = QListWidgetItem(f"{i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(166, 190))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setIcon(QIcon(pixmap("file", "#C4CCDA", 42)))
            self.thumb_list.addItem(item)
        current = doc.page if hasattr(doc, "page") else 0
        self._thumb_queue = []
        self._queue_thumb_range(0, min(10, doc.page_count - 1))
        self._queue_thumb_range(current - 3, current + 3)
        self._render_next_thumb()
        if self._thumb_queue:
            self._thumb_timer.start()
        self.set_current_page(current)
        self.refresh_bookmarks()
        self.refresh_annotations()
        self.refresh_forms()
        self.refresh_attachments()
        self.panel_count.setText(f"{doc.page_count} 页")

    def set_current_page(self, index: int) -> None:
        if index < 0 or index >= self.thumb_list.count():
            return
        self.thumb_list.blockSignals(True)
        self.thumb_list.setCurrentRow(index)
        self.thumb_list.blockSignals(False)
        self.thumb_list.scrollToItem(self.thumb_list.item(index), QAbstractItemView.ScrollHint.EnsureVisible)

    def selected_pages(self) -> list[int]:
        return sorted(
            self.thumb_list.row(item) for item in self.thumb_list.selectedItems()
        )

    def _queue_thumb_range(self, start: int, end: int) -> None:
        if not getattr(self, "_doc", None):
            return
        count = self.thumb_list.count()
        for index in range(max(0, int(start)), min(count, int(end) + 1)):
            if index in self._rendered_thumbs or index in self._thumb_queue:
                continue
            self._thumb_queue.append(index)

    def _queue_visible_thumbs(self) -> None:
        if not getattr(self, "_doc", None) or not self.thumb_list.count():
            return
        viewport = self.thumb_list.viewport()
        first = self.thumb_list.row(self.thumb_list.itemAt(12, 10)) if self.thumb_list.itemAt(12, 10) else 0
        bottom_item = self.thumb_list.itemAt(12, viewport.height() - 12)
        last = self.thumb_list.row(bottom_item) if bottom_item else min(self.thumb_list.count() - 1, first + 3)
        self._queue_thumb_range(first - 2, last + 2)
        current = getattr(self._doc, "page", 0)
        self._queue_thumb_range(current - 2, current + 2)
        if self._thumb_queue and not self._thumb_timer.isActive():
            self._thumb_timer.start()

    def _render_thumb_icon(self, index: int):
        if not getattr(self, "_doc", None):
            return None
        try:
            from PySide6.QtGui import QImage

            pix = self._doc.render(index, 0.18, annots=False)
            fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            qpix = QPixmap.fromImage(image)
            # Add a small paper border without destroying the page image.
            framed = QPixmap(qpix.width() + 4, qpix.height() + 4)
            framed.fill(QColor("#FFFFFF"))
            painter = QPainter(framed)
            painter.setPen(QColor("#DDE3EC"))
            painter.drawRect(0, 0, framed.width() - 1, framed.height() - 1)
            painter.drawPixmap(2, 2, qpix)
            painter.end()
            return QIcon(framed)
        except Exception:
            return None

    def _render_next_thumb(self) -> None:
        if not self._thumb_queue or not getattr(self, "_doc", None):
            self._thumb_timer.stop()
            return
        index = self._thumb_queue.pop(0)
        if index in self._rendered_thumbs:
            return
        icon = self._render_thumb_icon(index)
        if icon is not None:
            item = self.thumb_list.item(index)
            if item:
                item.setIcon(icon)
            self._rendered_thumbs.add(index)
        if not self._thumb_queue:
            self._thumb_timer.stop()

    def refresh_page(self, index: int) -> None:
        if not getattr(self, "_doc", None) or index < 0 or index >= self.thumb_list.count():
            return
        icon = self._render_thumb_icon(index)
        if icon is not None:
            item = self.thumb_list.item(index)
            if item:
                item.setIcon(icon)
            self._rendered_thumbs.add(index)

    def refresh_thumbnails(self) -> None:
        """Invalidate page previews and redraw only visible/current pages.

        Rendering every page in a large document synchronously was the main
        cause of UI stutter when opening or editing a file.
        """
        if not getattr(self, "_doc", None):
            return
        self._thumb_timer.stop()
        self._thumb_queue = []
        self._rendered_thumbs.clear()
        for i in range(self.thumb_list.count()):
            item = self.thumb_list.item(i)
            if item:
                item.setIcon(QIcon(pixmap("file", "#C4CCDA", 42)))
        self._queue_visible_thumbs()
        self._queue_thumb_range(0, min(8, self._doc.page_count - 1))
        self._render_next_thumb()
        if self._thumb_queue:
            self._thumb_timer.start()
        self.set_current_page(self._doc.page)

    def refresh_bookmarks(self) -> None:
        self.bookmark_tree.clear()
        if not getattr(self, "_doc", None):
            return
        entries = self._doc.outline()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for row in entries:
            try:
                level, title, page_number = int(row[0]), str(row[1]), int(row[2])
            except Exception:
                continue
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, max(0, page_number - 1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.bookmark_tree.addTopLevelItem(item)
            stack.append((level, item))
        self.bookmark_tree.expandAll()

    def refresh_annotations(self) -> None:
        self.annot_list.clear()
        if not getattr(self, "_doc", None):
            return
        self._annot_rows: list[AnnotInfo] = []
        for annot in self._doc.all_annotations():
            self._annot_rows.append(annot)
        self._filter_annots()

    def _filter_annots(self) -> None:
        if not hasattr(self, "_annot_rows"):
            return
        mode = self.annot_filter.currentIndex() if hasattr(self, "annot_filter") else 0
        self.annot_list.clear()
        for annot in self._annot_rows:
            if mode == 1 and annot.type not in ("高亮", "下划线", "删除线", "波浪线"):
                continue
            if mode == 2 and annot.type not in ("文本注释", "文本框"):
                continue
            if mode == 3 and annot.type not in ("手绘", "矩形", "椭圆", "线条"):
                continue
            content = (annot.content or "").strip().replace("\n", " ")
            if len(content) > 40:
                content = content[:40] + "…"
            label = f"{annot.type}  ·  第 {annot.page + 1} 页"
            if content:
                label += f"\n{content}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (annot.page, annot.xref))
            item.setSizeHint(QSize(190, 56))
            self.annot_list.addItem(item)
        if getattr(self, "_current_panel", "") == "annots":
            self.panel_count.setText(f"{len(self._annot_rows)} 条")

    def refresh_forms(self) -> None:
        self.form_list.clear()
        if not getattr(self, "_doc", None):
            return
        try:
            widgets = self._doc.widgets()
        except Exception:
            widgets = []
        for widget in widgets:
            value = str(widget.value or "")
            if len(value) > 26:
                value = value[:26] + "…"
            label = f"{widget.name}  ·  第 {widget.page + 1} 页"
            if value:
                label += f"\n{value}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, widget.xref)
            item.setSizeHint(QSize(190, 54))
            self.form_list.addItem(item)
        if getattr(self, "_current_panel", "") == "forms":
            self.panel_count.setText(f"{len(widgets)} 个字段")

    def refresh_attachments(self) -> None:
        self.attach_list.clear()
        if not getattr(self, "_doc", None):
            return
        try:
            attachments = self._doc.attachments()
        except Exception:
            attachments = []
        for entry in attachments:
            name = entry.get("name", "")
            size = entry.get("size", 0)
            item = QListWidgetItem(f"{name}\n{size / 1024:.0f} KB" if size else name)
            item.setIcon(QIcon(pixmap("paperclip", C.TEXT_MUTED, 16)))
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.attach_list.addItem(item)

    def set_search_results(self, hits: Sequence[SearchHit], snippets: Sequence[str] | None = None) -> None:
        self.search_list.clear()
        for i, hit in enumerate(hits):
            text = snippets[i] if snippets and i < len(snippets) else hit.text
            item = QListWidgetItem(f"第 {hit.page + 1} 页\n{text}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(190, 50))
            self.search_list.addItem(item)
        self.search_info.setText(f"找到 {len(hits)} 处结果" if hits else "未找到匹配内容")
        self.panel_count.setText(str(len(hits)))

    def set_annotations_count(self, count: int) -> None:
        self.panel_count.setText(f"{count} 条")

    # --------------------------------------------------------------- internal
    def _on_rail(self, key: str) -> None:
        button = self.rail_buttons[key]
        if self.panel.isVisible() and button.isChecked() and self._current_panel == key:
            self.collapse()
            return
        self.show_panel(key)

    def show_panel(self, key: str) -> None:
        keys = [p[0] for p in self.PANELS]
        if key not in keys:
            return
        index = keys.index(key)
        self._current_panel = key
        self.stack.setCurrentIndex(index)
        self.panel_title.setText({p[0]: p[3] for p in self.PANELS}[key])
        for k, button in self.rail_buttons.items():
            button.blockSignals(True)
            button.setChecked(k == key)
            button.blockSignals(False)
        if not self.panel.isVisible():
            self.panel.show()
            self.panel_toggled.emit(True)
        if key == "search":
            self.search_edit.setFocus()
        if key == "annots":
            self.refresh_annotations()

    def collapse(self) -> None:
        self.panel.hide()
        for button in self.rail_buttons.values():
            button.setChecked(False)
        self.panel_toggled.emit(False)

    def toggle(self) -> None:
        if self.panel.isVisible():
            self.collapse()
        else:
            self.show_panel(self._current_panel)

    def _on_rows_moved(self, parent, start: int, end: int, destination, row: int) -> None:
        if self._reordering:
            return
        order: list[int] = []
        for i in range(self.thumb_list.count()):
            item = self.thumb_list.item(i)
            if item is None:
                return
            value = item.data(Qt.ItemDataRole.UserRole)
            if value is None:
                return
            order.append(int(value))
        if sorted(order) != list(range(len(order))):
            return
        self._reordering = True
        try:
            self.page_order_changed.emit(order)
        finally:
            self._reordering = False

    def _thumb_current(self, row: int) -> None:
        if row >= 0:
            self.page_selected.emit(row)

    def _thumb_selection(self) -> None:
        pages = self.selected_pages()
        if pages:
            self.pages_selected.emit(pages)

    def _thumb_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("插入空白页").triggered.connect(self.add_page_requested)
        menu.addAction("删除选中页面").triggered.connect(self.delete_pages_requested)
        menu.addAction("旋转选中页面").triggered.connect(self.rotate_page_requested)
        menu.addSeparator()
        menu.addAction("提取选中页面").triggered.connect(self.extract_pages_requested)
        menu.exec(self.thumb_list.mapToGlobal(pos))

    def _bookmark_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            self.bookmark_selected.emit(int(page))

    def _annot_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.annot_selected.emit(int(data[0]), int(data[1]))

    def _do_search(self) -> None:
        text = self.search_edit.text().strip()
        if text:
            self.search_requested.emit(text)

    def _search_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.search_hit_selected.emit(int(index))
