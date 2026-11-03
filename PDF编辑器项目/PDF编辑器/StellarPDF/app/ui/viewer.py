"""High-performance continuous PDF canvas with text selection and tools."""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pymupdf
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QTextBlockFormat,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QRubberBand,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, pdf_font_family_and_file
from ..core.document import AnnotInfo, ImageBlock, PdfDocument, TextBlock, TextSpan
from ..theme import C


@dataclass
class PageLayout:
    index: int
    x: float
    y: float
    w: float
    h: float


class SelectionToolbar(QFrame):
    edit_clicked = Signal()
    highlight_clicked = Signal()
    copy_clicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("SelectionToolbar")
        self.setStyleSheet(
            "QFrame#SelectionToolbar { background:#FFFFFF; border:1px solid #D5DCE8;"
            "border-radius:6px; } QPushButton { border:none; padding:3px 7px;"
            "font-size:8.3pt; color:#3B4252; border-radius:3px; }"
            "QPushButton:hover { background:#EAF1FF; color:#1F55D6; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(1)
        for text, signal in (
            ("编辑文字", self.edit_clicked),
            ("高亮", self.highlight_clicked),
            ("复制", self.copy_clicked),
        ):
            button = QPushButton(text, self)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(signal)
            layout.addWidget(button)
        self.hide()


class InlineTextEditor(QTextEdit):
    """Transparent, borderless editor laid directly over the PDF text.

    The white page-colored backdrop is a sibling behind this widget, so the
    user sees the blinking caret in the document itself rather than a separate
    dialog or card.
    """

    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        text: str,
        *,
        font_size: float,
        color: str,
        font_family: str = "Microsoft YaHei UI",
        line_height: float = 1.3,
    ) -> None:
        super().__init__(parent)
        self._finished = False
        self.setPlainText(text)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setContentsMargins(0, 0, 0, 0)
        self.document().setDocumentMargin(0)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font = QFont(font_family)
        font.setPointSizeF(max(6.5, font_size))
        self.setFont(font)
        self.setStyleSheet(
            "QTextEdit { font-family:'%s'; font-size:%.2fpt;"
            "background-color:transparent; color:%s;"
            "border:none; padding:0; margin:0;"
            "selection-background-color:rgba(70,130,255,90); }"
            % (font_family.replace("'", ""), max(6.5, font_size), color)
        )
        self.document().setDefaultFont(font)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("transparent"))
        palette.setColor(QPalette.ColorRole.Text, QColor(color))
        self.setPalette(palette)
        self.setToolTip("就在原文字上修改 · Ctrl+Enter 应用 · Esc 取消 · 点击页面其他位置也会应用")
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        try:
            block_format.setLineHeight(
                max(0.68, min(1.8, float(line_height))) * 100,
                QTextBlockFormat.LineHeightTypes.ProportionalHeight,
            )
        except Exception:
            pass
        cursor.mergeBlockFormat(block_format)

    def place_caret(self, point: QPoint) -> None:
        cursor = self.cursorForPosition(point)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._finished = True
            self.cancel_requested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._commit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        QTimer.singleShot(0, self._commit_if_unfocused)

    def _commit_if_unfocused(self) -> None:
        if not self._finished and not self.hasFocus():
            self._commit()

    def _commit(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.commit_requested.emit(self.toPlainText())


class InlineEditorPanel(QFrame):
    """Opaque inline editor with explicit Apply / Cancel actions."""

    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(
        self,
        parent: QWidget,
        text: str,
        *,
        font_size: float,
        color: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InlineEditorPanel")
        self.setStyleSheet(
            "QFrame#InlineEditorPanel { background:#FFFFFF; border:2px solid #2F6BFF;"
            "border-radius:5px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 4)
        layout.setSpacing(3)
        self.editor = InlineTextEditor(self, text, font_size=font_size, color=color)
        layout.addWidget(self.editor, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        hint = QLabel("Ctrl+Enter 应用 · Esc 取消", self)
        hint.setStyleSheet("color:#7A8294; font-size:7.8pt;")
        footer.addWidget(hint)
        footer.addStretch(1)
        cancel = QPushButton("取消", self)
        cancel.setFixedHeight(22)
        cancel.setStyleSheet("QPushButton { padding:1px 10px; font-size:8pt; }")
        cancel.clicked.connect(self.cancel_requested)
        apply = QPushButton("应用", self)
        apply.setFixedHeight(22)
        apply.setObjectName("Primary")
        apply.setStyleSheet(
            "QPushButton { padding:1px 12px; font-size:8pt; background:#2F6BFF;"
            "color:white; border:none; border-radius:4px; }"
        )
        apply.clicked.connect(lambda: self.commit_requested.emit(self.editor.toPlainText()))
        footer.addWidget(cancel)
        footer.addWidget(apply)
        layout.addLayout(footer)
        self.editor.commit_requested.connect(self.commit_requested)
        self.editor.cancel_requested.connect(self.cancel_requested)


class PdfView(QAbstractScrollArea):
    page_changed = Signal(int)
    zoom_changed = Signal(float)
    selection_changed = Signal(str)
    status_message = Signal(str)
    text_edit_requested = Signal(object)
    text_block_commit = Signal(object, str)
    text_insert_requested = Signal(int, object)
    image_insert_requested = Signal(int, object)
    markup_requested = Signal(str, int, object)
    shape_requested = Signal(str, int, object, object)
    ink_requested = Signal(int, object)
    sticky_requested = Signal(int, object)
    stamp_requested = Signal(int, object)
    signature_requested = Signal(int, object)
    link_requested = Signal(int, object)
    redact_requested = Signal(int, object)
    form_requested = Signal(str, int, object)
    object_action = Signal(str, object)
    screenshot_taken = Signal(QImage)
    cursor_page_changed = Signal(int)
    tool_changed = Signal(str)
    paste_requested = Signal(int)

    MIN_ZOOM = 0.15
    MAX_ZOOM = 6.0
    MARGIN = 26
    GAP = 18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.setBackgroundRole(self.backgroundRole())
        self.viewport().setMouseTracking(True)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.verticalScrollBar().setSingleStep(36)
        self.horizontalScrollBar().setSingleStep(36)

        self.doc: PdfDocument | None = None
        self.zoom = 1.0
        self.view_mode = "continuous"
        self.current_page = 0
        self.tool = "select"
        self.annotation_color = "#FFD84D"
        self.line_width = 2.0
        self.stamp_text = "已批准"
        self.stamp_subtitle = "星澜 PDF"
        self.signature_bytes: bytes | None = None
        self.form_kind = "text"

        self._layouts: list[PageLayout] = []
        self._content_w = 0.0
        self._content_h = 0.0
        self._pix_cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._max_cache = 14
        self._layout_dirty = True

        self._press: QPointF | None = None
        self._press_pdf: pymupdf.Point | None = None
        self._press_page = -1
        self._drag_pdf_rect: pymupdf.Rect | None = None
        self._preview_rect: QRectF | None = None
        self._ink_stroke: list[tuple[float, float]] = []
        self._ink_strokes: list[list[tuple[float, float]]] = []
        self._ink_page = -1
        self._panning = False
        self._pan_origin = QPointF()
        self._pan_h = 0
        self._pan_v = 0
        self._did_pan = False

        self.selected_text = ""
        self._selection_rects: list[QRectF] = []
        self._selection_page = -1
        self._selected_span: TextSpan | None = None
        self._selected_annots: list[AnnotInfo] = []
        self._selected_image: ImageBlock | None = None
        self._selected_widget: Any = None
        self._drag_selecting = False
        self._inline_editor: InlineTextEditor | None = None
        self._inline_backdrop: QWidget | None = None
        self._inline_block: TextBlock | None = None
        self._inline_min_height = 18
        self.selection_toolbar = SelectionToolbar(self.viewport())
        self.selection_toolbar.edit_clicked.connect(self.edit_selected_block)
        self.selection_toolbar.highlight_clicked.connect(self._highlight_selection)
        self.selection_toolbar.copy_clicked.connect(self.copy_selection)

        self.search_hits: list[tuple[int, pymupdf.Rect]] = []
        self.active_hit = -1
        self.show_form_fields = False
        self._measure_points: list[tuple[int, pymupdf.Point]] = []
        self._measure_text = ""

        self._current_page_timer = None
        self._last_cursor_page = -1
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ setup
    def set_document(self, doc: PdfDocument | None) -> None:
        self._close_inline(commit=False)
        self.doc = doc
        self.current_page = min(doc.page if doc else 0, max(0, (doc.page_count - 1) if doc else 0))
        self._pix_cache.clear()
        self._clear_selection()
        self.search_hits.clear()
        self.active_hit = -1
        self._layout_dirty = True
        self._relayout()
        self.viewport().update()
        self.zoom_changed.emit(self.zoom)

    def refresh(self, keep_scroll: bool = True) -> None:
        self._pix_cache.clear()
        self._layout_dirty = True
        self._relayout()
        self.viewport().update()
        if self.doc:
            self.current_page = min(self.current_page, self.doc.page_count - 1)

    def invalidate(self) -> None:
        self._pix_cache.clear()
        self.viewport().update()

    def set_view_mode(self, mode: str) -> None:
        self._close_inline(commit=True)
        if mode == self.view_mode:
            return
        old_page = self.current_page
        self.view_mode = "double" if mode == "book" else mode
        self._layout_dirty = True
        self._relayout()
        self.goto_page(old_page, ensure_visible=True)
        self.viewport().update()

    def set_tool(self, tool: str) -> None:
        self._close_inline(commit=True)
        self.selection_toolbar.hide()
        self.tool = tool
        self._preview_rect = None
        self._ink_stroke = []
        self._measure_points = []
        self._measure_text = ""
        self._selected_span = None
        self._selected_annots = []
        self._selected_image = None
        self._selected_widget = None
        self._clear_text_selection(emit=False)
        if tool in ("hand",):
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool in ("select",):
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        elif tool in ("measure", "area"):
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif tool in ("screenshot",):
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.viewport().update()
        self.tool_changed.emit(tool)

    def set_annotation_color(self, color: str) -> None:
        self.annotation_color = color

    def set_line_width(self, width: float) -> None:
        self.line_width = max(0.5, float(width))

    def set_signature(self, data: bytes | None) -> None:
        self.signature_bytes = data

    def set_stamp(self, text: str, subtitle: str = "") -> None:
        self.stamp_text = text
        self.stamp_subtitle = subtitle

    def set_form_kind(self, kind: str) -> None:
        self.form_kind = kind

    def set_show_form_fields(self, value: bool) -> None:
        self.show_form_fields = value
        self.viewport().update()

    # ----------------------------------------------------------------- layout
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._close_inline(commit=True)
        page = self.current_page
        self._layout_dirty = True
        self._relayout()
        self.goto_page(page, ensure_visible=False)
        self.viewport().update()

    def _page_dims(self, index: int) -> tuple[float, float]:
        if not self.doc:
            return 595 * self.zoom, 842 * self.zoom
        try:
            w, h = self.doc.page_size(index)
            return w * self.zoom, h * self.zoom
        except Exception:
            return 595 * self.zoom, 842 * self.zoom

    def _relayout(self) -> None:
        if not self.doc or self.doc.page_count == 0:
            self._layouts = []
            self._content_w = self._content_h = 0
            self.horizontalScrollBar().setRange(0, 0)
            self.verticalScrollBar().setRange(0, 0)
            return
        vw = max(120, self.viewport().width())
        vh = max(120, self.viewport().height())
        pages = self.doc.page_count
        layouts: list[PageLayout] = []
        margin = self.MARGIN
        gap = self.GAP
        if self.view_mode == "single":
            index = max(0, min(self.current_page, pages - 1))
            w, h = self._page_dims(index)
            x = max(margin, (vw - w) / 2)
            y = max(margin, (vh - h) / 2)
            layouts.append(PageLayout(index, x, y, w, h))
            content_w = max(vw, w + margin * 2)
            content_h = max(vh, h + margin * 2)
        elif self.view_mode in ("double", "book"):
            rows: list[list[int]] = []
            if self.view_mode == "book" and pages > 0:
                rows.append([0])
                start = 1
            else:
                start = 0
            while start < pages:
                rows.append(list(range(start, min(start + 2, pages))))
                start += 2
            y = margin
            max_w = 0.0
            for row in rows:
                dims = [self._page_dims(i) for i in row]
                row_w = sum(d[0] for d in dims) + gap * (len(row) - 1)
                max_w = max(max_w, row_w)
            content_w = max(vw, max_w + margin * 2)
            for row in rows:
                dims = [self._page_dims(i) for i in row]
                row_w = sum(d[0] for d in dims) + gap * (len(row) - 1)
                row_h = max(d[1] for d in dims)
                x = (content_w - row_w) / 2
                for index, (w, h) in zip(row, dims):
                    layouts.append(PageLayout(index, x, y + max(0, (row_h - h) / 2), w, h))
                    x += w + gap
                y += row_h + gap
            content_h = max(vh, y - gap + margin)
        else:
            y = margin
            max_w = max((self._page_dims(i)[0] for i in range(pages)), default=0)
            content_w = max(vw, max_w + margin * 2)
            for i in range(pages):
                w, h = self._page_dims(i)
                x = (content_w - w) / 2
                layouts.append(PageLayout(i, x, y, w, h))
                y += h + gap
            content_h = max(vh, y - gap + margin)
        self._layouts = layouts
        self._content_w = content_w
        self._content_h = content_h
        self.horizontalScrollBar().setPageStep(max(1, int(vw)))
        self.horizontalScrollBar().setRange(0, max(0, int(content_w - vw)))
        self.verticalScrollBar().setPageStep(max(1, int(vh)))
        self.verticalScrollBar().setRange(0, max(0, int(content_h - vh)))
        self._layout_dirty = False

    def _offset(self) -> tuple[float, float]:
        vw = self.viewport().width()
        vh = self.viewport().height()
        ox = -self.horizontalScrollBar().value()
        if self._content_w < vw:
            ox = (vw - self._content_w) / 2
        oy = -self.verticalScrollBar().value()
        if self._content_h < vh:
            oy = (vh - self._content_h) / 2
        return ox, oy

    def _layout_for(self, index: int) -> PageLayout | None:
        for layout in self._layouts:
            if layout.index == index:
                return layout
        return None

    def page_screen_rect(self, index: int) -> QRectF:
        layout = self._layout_for(index)
        if not layout:
            return QRectF()
        ox, oy = self._offset()
        return QRectF(layout.x + ox, layout.y + oy, layout.w, layout.h)

    def _page_at(self, pos: QPointF) -> tuple[int, PageLayout] | tuple[None, None]:
        for layout in self._layouts:
            rect = self.page_screen_rect(layout.index)
            if rect.adjusted(-2, -2, 2, 2).contains(pos):
                return layout.index, layout
        return None, None

    def _screen_to_pdf(self, pos: QPointF, page_index: int) -> pymupdf.Point | None:
        if not self.doc:
            return None
        rect = self.page_screen_rect(page_index)
        if rect.isEmpty():
            return None
        x = (pos.x() - rect.x()) / self.zoom
        y = (pos.y() - rect.y()) / self.zoom
        page = self.doc.require_doc()[page_index]
        point = pymupdf.Point(x, y)
        if page.rotation:
            point = point * page.derotation_matrix
        return point

    def _pdf_rect_to_screen(self, page_index: int, rect: pymupdf.Rect) -> QRectF:
        page = self.doc.require_doc()[page_index]
        rr = pymupdf.Rect(rect)
        if page.rotation:
            rr = rr * page.rotation_matrix
        origin = self.page_screen_rect(page_index)
        return QRectF(
            origin.x() + rr.x0 * self.zoom,
            origin.y() + rr.y0 * self.zoom,
            max(0.5, (rr.x1 - rr.x0) * self.zoom),
            max(0.5, (rr.y1 - rr.y0) * self.zoom),
        )

    def _screen_drag_to_pdf_rect(
        self, start: QPointF, end: QPointF, page_index: int
    ) -> pymupdf.Rect | None:
        p1 = self._screen_to_pdf(start, page_index)
        p2 = self._screen_to_pdf(end, page_index)
        if p1 is None or p2 is None:
            return None
        page = self.doc.require_doc()[page_index]
        if page.rotation:
            # Transform all corners so a screen-axis-aligned rectangle becomes
            # the correct unrotated page rectangle.
            corners = [
                p1,
                p2,
                pymupdf.Point(p1.x, p2.y),
                pymupdf.Point(p2.x, p1.y),
            ]
            rects = [pymupdf.Rect(c, c) for c in corners]
            r = rects[0]
            for rr in rects[1:]:
                r |= rr
            return r
        return pymupdf.Rect(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))

    # ----------------------------------------------------------------- render
    def _pixmap_for(self, index: int) -> QPixmap:
        if not self.doc:
            return QPixmap()
        dpr = max(1.0, self.devicePixelRatioF())
        key = (index, round(self.zoom, 4), self.doc.page_rotation(index), round(dpr, 2))
        cached = self._pix_cache.get(key)
        if cached is not None:
            self._pix_cache.move_to_end(key)
            return cached
        try:
            pix = self.doc.render(index, self.zoom * dpr, annots=True)
            fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            qpix = QPixmap.fromImage(image)
            qpix.setDevicePixelRatio(dpr)
        except Exception:
            qpix = QPixmap()
        self._pix_cache[key] = qpix
        if len(self._pix_cache) > self._max_cache:
            self._pix_cache.popitem(last=False)
        return qpix

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.viewport().rect(), QColor(C.CANVAS))
        if not self.doc or not self._layouts:
            painter.end()
            return
        vp_rect = QRectF(self.viewport().rect())
        for layout in self._layouts:
            rect = self.page_screen_rect(layout.index)
            if rect.bottom() < vp_rect.top() - 80 or rect.top() > vp_rect.bottom() + 80:
                continue
            self._draw_page(painter, layout, rect)
        # Overlays (search, selection, form fields, selected objects).
        self._draw_overlays(painter)
        self._draw_preview(painter)
        painter.end()

    def _draw_page(self, painter: QPainter, layout: PageLayout, rect: QRectF) -> None:
        # Soft drop shadow.
        shadow = rect.translated(1.5, 2.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(60, 80, 120, 26))
        painter.drawRoundedRect(shadow.adjusted(-1, -1, 3, 4), 2, 2)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#DCE2EC"), 0.8))
        painter.drawRect(rect)
        pix = self._pixmap_for(layout.index)
        if not pix.isNull():
            painter.drawPixmap(rect, pix, QRectF(pix.rect()))
        if layout.index == self.current_page:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(C.PRIMARY), 1.2))
            painter.drawRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5))

    def _draw_overlays(self, painter: QPainter) -> None:
        if not self.doc:
            return
        # Search highlights.
        if self.search_hits:
            for i, (pno, rect) in enumerate(self.search_hits):
                if pno == self._press_page and False:
                    continue
                screen = self._pdf_rect_to_screen(pno, rect)
                if not self.viewport().rect().intersects(screen.toRect().adjusted(-20, -20, 20, 20)):
                    continue
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 205, 40, 105 if i != self.active_hit else 165))
                painter.drawRoundedRect(screen.adjusted(-1, -1, 1, 1), 2, 2)
                if i == self.active_hit:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor("#F0A400"), 1.5))
                    painter.drawRoundedRect(screen.adjusted(-2, -2, 2, 2), 2, 2)
        # Form field highlights.
        if self.show_form_fields:
            for pno in range(self.doc.page_count):
                try:
                    widgets = list(self.doc.require_doc()[pno].widgets() or [])
                except Exception:
                    continue
                for widget in widgets:
                    screen = self._pdf_rect_to_screen(pno, pymupdf.Rect(widget.rect))
                    if not screen.isValid():
                        continue
                    painter.setPen(QPen(QColor(47, 107, 255, 150), 1, Qt.PenStyle.DashLine))
                    painter.setBrush(QColor(47, 107, 255, 18))
                    painter.drawRoundedRect(screen.adjusted(-1, -1, 1, 1), 2, 2)
        # Text selection.
        if self._selection_rects:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(47, 107, 255, 80))
            for rect in self._selection_rects:
                painter.drawRect(rect)
        # Selected text span.
        if self._selected_span:
            rect = self._pdf_rect_to_screen(self._selected_span.page, self._selected_span.bbox)
            painter.setBrush(QColor(47, 107, 255, 25))
            painter.setPen(QPen(QColor(C.PRIMARY), 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
        # Selected annotations.
        for annot in self._selected_annots:
            rect = self._pdf_rect_to_screen(annot.page, annot.rect)
            painter.setBrush(QColor(47, 107, 255, 18))
            painter.setPen(QPen(QColor(C.PRIMARY), 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
            self._draw_handles(painter, rect)
        if self._selected_image:
            rect = self._pdf_rect_to_screen(self._selected_image.page, self._selected_image.bbox)
            painter.setBrush(QColor(24, 166, 111, 18))
            painter.setPen(QPen(QColor(C.SUCCESS), 1.5, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
            self._draw_handles(painter, rect)

    def _draw_handles(self, painter: QPainter, rect: QRectF) -> None:
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor(C.PRIMARY), 1.2))
        for point in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
            painter.drawRect(QRectF(point.x() - 2.5, point.y() - 2.5, 5, 5))

    def _draw_preview(self, painter: QPainter) -> None:
        if self._preview_rect:
            painter.setBrush(QColor(47, 107, 255, 30))
            painter.setPen(QPen(QColor(C.PRIMARY), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self._preview_rect)
        if self._ink_stroke:
            path = QPainterPath()
            first = True
            for x, y in self._ink_stroke:
                point = self._pdf_point_to_screen(self._ink_page, x, y)
                if first:
                    path.moveTo(point)
                    first = False
                else:
                    path.lineTo(point)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.annotation_color), self.line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        if self._measure_points:
            for pno, point in self._measure_points:
                screen = self._pdf_point_to_screen(pno, point.x, point.y)
                painter.setPen(QPen(QColor("#E5484D"), 1.4))
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawEllipse(screen, 3, 3)
            if len(self._measure_points) == 2 and self._measure_points[0][0] == self._measure_points[1][0]:
                p1 = self._pdf_point_to_screen(self._measure_points[0][0], *self._measure_points[0][1])
                p2 = self._pdf_point_to_screen(self._measure_points[1][0], *self._measure_points[1][1])
                painter.setPen(QPen(QColor("#E5484D"), 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(p1, p2)
                if self._measure_text:
                    mid = (p1 + p2) / 2
                    metrics = QFontMetrics(QFont("Microsoft YaHei UI", 9))
                    width = metrics.horizontalAdvance(self._measure_text) + 12
                    box = QRectF(mid.x() - width / 2, mid.y() - 26, width, 22)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(35, 40, 51, 225))
                    painter.drawRoundedRect(box, 4, 4)
                    painter.setPen(QColor("white"))
                    painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._measure_text)

    def _pdf_point_to_screen(self, page_index: int, x: float, y: float) -> QPointF:
        page = self.doc.require_doc()[page_index]
        point = pymupdf.Point(x, y)
        if page.rotation:
            point = point * page.rotation_matrix
        origin = self.page_screen_rect(page_index)
        return QPointF(origin.x() + point.x * self.zoom, origin.y() + point.y * self.zoom)

    # ------------------------------------------------------------------ zoom
    def set_zoom(self, zoom: float, *, anchor: QPointF | None = None, emit: bool = True) -> None:
        self._close_inline(commit=True)
        self.selection_toolbar.hide()
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
        if abs(zoom - self.zoom) < 0.001:
            return
        if self.doc and self._layouts:
            anchor = anchor or QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
            pno, layout = self._page_at(anchor)
            if pno is not None:
                before = self._screen_to_pdf(anchor, pno)
            else:
                before = None
                pno = self.current_page
            self.zoom = zoom
            self._layout_dirty = True
            self._relayout()
            if before is not None:
                point = self._pdf_point_to_screen(pno, before.x, before.y)
                dx = point.x() - anchor.x()
                dy = point.y() - anchor.y()
                self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + dx))
                self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + dy))
        else:
            self.zoom = zoom
            self._layout_dirty = True
            self._relayout()
        self._pix_cache.clear()
        self.viewport().update()
        if emit:
            self.zoom_changed.emit(self.zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.2)

    def fit_width(self) -> None:
        if not self.doc:
            return
        w, _ = self.doc.page_size(self.current_page)
        available = max(100, self.viewport().width() - self.MARGIN * 2)
        self.set_zoom(available / max(1.0, w))

    def fit_page(self) -> None:
        if not self.doc:
            return
        w, h = self.doc.page_size(self.current_page)
        available_w = max(100, self.viewport().width() - self.MARGIN * 2)
        available_h = max(100, self.viewport().height() - self.MARGIN * 2)
        self.set_zoom(min(available_w / max(1.0, w), available_h / max(1.0, h)))

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    # -------------------------------------------------------------- navigation
    def goto_page(self, index: int, *, ensure_visible: bool = True) -> None:
        self._close_inline(commit=True)
        self.selection_toolbar.hide()
        if not self.doc:
            return
        index = max(0, min(index, self.doc.page_count - 1))
        changed = index != self.current_page
        self.current_page = index
        if self.view_mode == "single":
            self._relayout()
            self.viewport().update()
        elif ensure_visible:
            layout = self._layout_for(index)
            if layout:
                self.verticalScrollBar().setValue(max(0, int(layout.y - 12)))
        if changed:
            self.page_changed.emit(index)
        self.viewport().update()

    def next_page(self) -> None:
        if self.doc:
            self.goto_page(self.current_page + 1)

    def prev_page(self) -> None:
        self.goto_page(self.current_page - 1)

    def _on_scroll(self, value: int) -> None:
        self.selection_toolbar.hide()
        if self._inline_editor is not None:
            self._close_inline(commit=True)
        self.viewport().update()
        if not self.doc or not self._layouts:
            return
        if self.view_mode in ("single", "double", "book"):
            # Keep current page in sync with the page nearest the viewport center.
            center = self.viewport().height() / 2
            best = None
            best_dist = 1e9
            for layout in self._layouts:
                rect = self.page_screen_rect(layout.index)
                if rect.top() <= center <= rect.bottom():
                    best = layout.index
                    break
                dist = min(abs(rect.top() - center), abs(rect.bottom() - center))
                if dist < best_dist:
                    best, best_dist = layout.index, dist
            if best is not None and best != self.current_page:
                self.current_page = best
                self.page_changed.emit(best)
        else:
            center = self.viewport().height() * 0.35
            best = self.current_page
            for layout in self._layouts:
                rect = self.page_screen_rect(layout.index)
                if rect.top() <= center <= rect.bottom():
                    best = layout.index
                    break
            if best != self.current_page:
                self.current_page = best
                self.page_changed.emit(best)

    # --------------------------------------------------------------- selection
    def _clear_text_selection(self, emit: bool = True) -> None:
        self._selection_rects = []
        self._selection_page = -1
        self.selected_text = ""
        self.selection_toolbar.hide()
        if emit:
            self.selection_changed.emit("")
        self.viewport().update()

    def _show_selection_toolbar(self) -> None:
        if not self._selection_rects:
            self.selection_toolbar.hide()
            return
        bounds = QRectF(self._selection_rects[0])
        for rect in self._selection_rects[1:]:
            bounds = bounds.united(rect)
        self.selection_toolbar.adjustSize()
        width = self.selection_toolbar.width()
        height = self.selection_toolbar.height()
        x = max(6, min(int(bounds.center().x() - width / 2), self.viewport().width() - width - 6))
        y = int(bounds.top() - height - 7)
        if y < 6:
            y = min(self.viewport().height() - height - 6, int(bounds.bottom() + 7))
        self.selection_toolbar.move(x, max(6, y))
        self.selection_toolbar.show()
        self.selection_toolbar.raise_()

    def edit_selected_block(self) -> bool:
        if not self.doc or not self.selected_text or not self._selection_rects:
            return False
        page = self._selection_page
        if page < 0:
            return False
        bounds = QRectF(self._selection_rects[0])
        for rect in self._selection_rects[1:]:
            bounds = bounds.united(rect)
        best = None
        best_area = 0.0
        for block in self.doc.text_blocks(page):
            screen = self._pdf_rect_to_screen(page, block.bbox)
            overlap = screen.intersected(bounds)
            area = max(0.0, overlap.width()) * max(0.0, overlap.height())
            if area > best_area:
                best_area = area
                best = block
        if best is None:
            # Fallback for selections whose word rectangles straddle a block
            # boundary: test a few centers directly.
            for rect in self._selection_rects[:6]:
                point = self._screen_to_pdf(rect.center(), page)
                if point is None:
                    continue
                best = self.doc.block_at(page, point)
                if best is not None:
                    break
        if best is None:
            return False
        self.selection_toolbar.hide()
        self._begin_inline_edit(best, bounds.center())
        return True

    def _highlight_selection(self) -> None:
        if not self.selected_text or not self._selection_rects:
            return
        rects = self._selection_rects_to_pdf()
        if rects:
            self.markup_requested.emit("highlight", self._selection_page, rects)
            self.selection_toolbar.hide()

    def _clear_selection(self) -> None:
        self._selected_span = None
        self._selected_annots = []
        self._selected_image = None
        self._selected_widget = None
        self._clear_text_selection(emit=False)
        self.viewport().update()

    def _update_text_selection(self, start: QPointF, end: QPointF, page_index: int) -> None:
        if not self.doc:
            return
        self.selection_toolbar.hide()
        drag = QRectF(start, end).normalized()
        try:
            words = self.doc.require_doc()[page_index].get_text("words")
        except Exception:
            return
        rects: list[QRectF] = []
        pieces: list[str] = []
        last_line = None
        for word in words:
            rect = pymupdf.Rect(word[:4])
            screen = self._pdf_rect_to_screen(page_index, rect)
            if drag.intersects(screen):
                rects.append(screen)
                if last_line is not None and word[6] != last_line:
                    pieces.append("\n")
                elif pieces and not pieces[-1].endswith(("\n", " ")):
                    pieces.append(" ")
                pieces.append(str(word[4]))
                last_line = word[6]
        self._selection_rects = rects
        self._selection_page = page_index
        self.selected_text = "".join(pieces).strip()
        self.selection_changed.emit(self.selected_text)
        self.viewport().update()
        if self.selected_text:
            QTimer.singleShot(0, self._maybe_show_selection_toolbar)

    def _maybe_show_selection_toolbar(self) -> None:
        if (
            self.selected_text
            and not self._drag_selecting
            and QApplication.mouseButtons() == Qt.MouseButton.NoButton
        ):
            self._show_selection_toolbar()

    def copy_selection(self) -> None:
        if self.selected_text:
            QApplication.clipboard().setText(self.selected_text)
            self.status_message.emit(f"已复制 {len(self.selected_text)} 个字符")
        else:
            self.status_message.emit("请先在页面上选择文字")

    def select_all_text(self) -> None:
        if not self.doc:
            return
        page_index = self.current_page
        words = self.doc.require_doc()[page_index].get_text("words")
        rects = [self._pdf_rect_to_screen(page_index, pymupdf.Rect(w[:4])) for w in words]
        self._selection_rects = rects
        self._selection_page = page_index
        self.selected_text = "\n".join(str(w[4]) for w in words)
        self.selection_changed.emit(self.selected_text)
        self.viewport().update()

    def _span_at(self, page_index: int, point: pymupdf.Point) -> TextSpan | None:
        if not self.doc:
            return None
        for span in self.doc.spans(page_index):
            if span.bbox.contains(point):
                return span
        return None

    def _annot_at(self, page_index: int, point: pymupdf.Point) -> AnnotInfo | None:
        if not self.doc:
            return None
        for annot in reversed(self.doc.annotations(page_index)):
            if annot.rect.contains(point):
                return annot
        return None

    def _image_at(self, page_index: int, point: pymupdf.Point) -> ImageBlock | None:
        if not self.doc:
            return None
        for image in reversed(self.doc.images(page_index)):
            if image.bbox.contains(point):
                return image
        return None

    # ----------------------------------------------------------------- events
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_origin = pos
            self._pan_h = self.horizontalScrollBar().value()
            self._pan_v = self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self.doc:
            return
        self.viewport().setFocus()
        page_index, layout = self._page_at(pos)
        if page_index is None:
            self._clear_selection()
            return
        point = self._screen_to_pdf(pos, page_index)
        if point is None:
            return
        self._press = pos
        self._press_pdf = point
        self._press_page = page_index
        self._drag_pdf_rect = None
        self._did_pan = False
        tool = self.tool
        if tool == "hand":
            self._panning = True
            self._pan_origin = pos
            self._pan_h = self.horizontalScrollBar().value()
            self._pan_v = self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if tool == "edit_text":
            block = self.doc.block_at(page_index, point)
            if block:
                self._begin_inline_edit(block, pos)
            else:
                self.text_insert_requested.emit(page_index, point)
            self.viewport().update()
            return
        if tool == "image":
            self.image_insert_requested.emit(page_index, self._default_image_rect(page_index, point))
            return
        if tool == "select":
            annot = self._annot_at(page_index, point)
            image = self._image_at(page_index, point)
            if annot:
                self._selected_annots = [annot]
                self._selected_image = None
                self._selected_span = None
                self.object_action.emit("select_annot", {"page": page_index, "xref": annot.xref})
                self.viewport().update()
                return
            if image:
                self._selected_image = image
                self._selected_annots = []
                self._selected_span = None
                self.object_action.emit(
                    "select_image", {"page": page_index, "xref": image.xref, "rect": image.bbox}
                )
                self.viewport().update()
                return
            self._selected_annots = []
            self._selected_image = None
            self._drag_selecting = True
            self._clear_text_selection(emit=False)
            return
        if tool in ("highlight", "underline", "strike", "squiggly"):
            self._drag_selecting = True
            return
        if tool == "area_highlight":
            self._preview_rect = QRectF(pos, pos)
            return
        if tool in ("rect", "ellipse", "arrow", "line", "textbox", "link", "redact", "screenshot", "area"):
            self._preview_rect = QRectF(pos, pos)
            return
        if tool == "ink":
            self._ink_page = page_index
            self._ink_stroke = [(point.x, point.y)]
            self._ink_strokes = []
            return
        if tool in ("text", "sticky", "stamp", "signature", "note", "measure"):
            if tool == "text":
                self.text_insert_requested.emit(page_index, point)
            elif tool == "sticky":
                self.sticky_requested.emit(page_index, point)
            elif tool == "stamp":
                rect = self._default_stamp_rect(page_index, point)
                self.stamp_requested.emit(page_index, rect)
            elif tool == "signature":
                rect = self._default_signature_rect(page_index, point)
                self.signature_requested.emit(page_index, rect)
            elif tool == "note":
                self.sticky_requested.emit(page_index, point)
            elif tool == "measure":
                if self._measure_points and self._measure_points[0][0] == page_index:
                    self._measure_points.append((page_index, point))
                    self._update_measure()
                    self.viewport().update()
                    if len(self._measure_points) >= 2:
                        self._measure_points = []
                        self._measure_text = ""
                else:
                    self._measure_points = [(page_index, point)]
                    self._measure_text = ""
                    self.viewport().update()
            return
        if tool in ("form_text", "form_checkbox", "form_radio", "form_dropdown", "form_signature"):
            self._preview_rect = QRectF(pos, pos)
            return
        self._drag_selecting = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if self._panning:
            delta = pos - self._pan_origin
            self.horizontalScrollBar().setValue(int(self._pan_h - delta.x()))
            self.verticalScrollBar().setValue(int(self._pan_v - delta.y()))
            self._did_pan = True
            return
        if not self.doc:
            return
        page_index, _ = self._page_at(pos)
        if page_index is not None and page_index != self._last_cursor_page:
            self._last_cursor_page = page_index
            self.cursor_page_changed.emit(page_index)
        if self._drag_selecting and self._press is not None:
            if self.tool == "select":
                self._update_text_selection(self._press, pos, self._press_page)
            elif self.tool in ("highlight", "underline", "strike", "squiggly"):
                self._preview_rect = QRectF(self._press, pos).normalized()
                self.viewport().update()
            return
        if self._preview_rect is not None and self._press is not None:
            self._preview_rect = QRectF(self._press, pos).normalized()
            self.viewport().update()
            return
        if self.tool == "ink" and self._ink_stroke and page_index == self._ink_page:
            point = self._screen_to_pdf(pos, page_index)
            if point:
                self._ink_stroke.append((point.x, point.y))
                self.viewport().update()
            return
        if self.tool == "measure" and self._measure_points:
            point = self._screen_to_pdf(pos, page_index) if page_index is not None else None
            self._measure_text = ""
            self.viewport().update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return
        if self._panning:
            self._panning = False
            self.viewport().setCursor(
                Qt.CursorShape.OpenHandCursor if self.tool == "hand" else Qt.CursorShape.IBeamCursor
            )
            return
        if not self.doc:
            return
        tool = self.tool
        if self._drag_selecting:
            self._drag_selecting = False
            if tool in ("highlight", "underline", "strike", "squiggly") and self._press:
                rects = self._markup_rects(self._press, pos, self._press_page)
                if not rects and self._preview_rect:
                    rect = self._screen_drag_to_pdf_rect(self._press, pos, self._press_page)
                    if rect:
                        rects = [rect]
                if rects:
                    self.markup_requested.emit(tool, self._press_page, rects)
                self._preview_rect = None
                self._press = None
                self.viewport().update()
                return
            if tool == "select":
                self._show_selection_toolbar()
                self._press = None
                return
        if self._preview_rect is not None and self._press is not None:
            rect = QRectF(self._press, pos).normalized()
            self._preview_rect = None
            start = self._press
            self._press = None
            if rect.width() < 3 and rect.height() < 3:
                rect = QRectF(pos.x() - 1, pos.y() - 1, 2, 2)
            pdf_rect = self._screen_drag_to_pdf_rect(rect.topLeft(), rect.bottomRight(), self._press_page)
            if pdf_rect is None:
                self.viewport().update()
                return
            if tool == "area_highlight":
                self.markup_requested.emit("area", self._press_page, [pdf_rect])
            elif tool in ("rect", "ellipse", "arrow", "line"):
                p1 = self._screen_to_pdf(rect.topLeft(), self._press_page)
                p2 = self._screen_to_pdf(rect.bottomRight(), self._press_page)
                self.shape_requested.emit(tool, self._press_page, pdf_rect, [p1, p2] if p1 and p2 else [])
            elif tool == "textbox":
                self.text_insert_requested.emit(self._press_page, pdf_rect)
            elif tool == "link":
                self.link_requested.emit(self._press_page, pdf_rect)
            elif tool == "redact":
                self.redact_requested.emit(self._press_page, pdf_rect)
            elif tool == "screenshot":
                self._capture_region(self._press_page, pdf_rect)
            elif tool == "area":
                area = pdf_rect.width * pdf_rect.height
                self.status_message.emit(
                    f"选区面积：{area:,.0f} pt²（约 {area * 0.3528 * 0.3528:,.1f} mm²）"
                )
            elif tool.startswith("form_"):
                kind = tool.replace("form_", "")
                if rect.width() < 12:
                    pdf_rect = pymupdf.Rect(pdf_rect.x0, pdf_rect.y0, pdf_rect.x0 + 150, pdf_rect.y0 + 26)
                self.form_requested.emit(kind, self._press_page, pdf_rect)
            self.viewport().update()
        if tool == "ink" and self._ink_stroke:
            points = list(self._ink_stroke)
            self._ink_stroke = []
            if len(points) >= 2:
                self.ink_requested.emit(self._ink_page, points)
            self.viewport().update()
        self._press = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.doc or event.button() != Qt.MouseButton.LeftButton:
            return
        page_index, _ = self._page_at(event.position())
        if page_index is None:
            return
        point = self._screen_to_pdf(event.position(), page_index)
        if point is None:
            return
        block = self.doc.block_at(page_index, point)
        if block:
            self._begin_inline_edit(block, event.position())
            self.viewport().update()
        else:
            self.text_insert_requested.emit(page_index, point)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if not self.doc:
            return
        pos = event.pos()
        page_index, _ = self._page_at(pos)
        point = self._screen_to_pdf(pos, page_index) if page_index is not None else None
        menu = QMenu(self)
        has_selection = bool(self.selected_text)
        if has_selection:
            menu.addAction("复制文字").triggered.connect(self.copy_selection)
            menu.addAction("高亮选中文字").triggered.connect(
                lambda: self.markup_requested.emit("highlight", self._selection_page, self._selection_rects_to_pdf())
            )
            menu.addSeparator()
        if point is not None:
            span = self._span_at(page_index, point)
            block = self.doc.block_at(page_index, point)
            annot = self._annot_at(page_index, point)
            image = self._image_at(page_index, point)
            if block:
                menu.addAction("编辑这段文字").triggered.connect(
                    lambda: self._begin_inline_edit(block, QPointF(pos))
                )
            if span:
                menu.addAction("高亮这段文字").triggered.connect(
                    lambda: self._emit_word_highlight(page_index, span)
                )
            if block or span:
                menu.addSeparator()
            if annot:
                menu.addAction("编辑批注").triggered.connect(
                    lambda: self.object_action.emit(
                        "edit_annot", {"page": page_index, "xref": annot.xref, "content": annot.content}
                    )
                )
                menu.addAction("删除批注").triggered.connect(
                    lambda: self.object_action.emit("delete_annot", {"page": page_index, "xref": annot.xref})
                )
                menu.addSeparator()
            if image:
                menu.addAction("替换图片").triggered.connect(
                    lambda: self.object_action.emit(
                        "replace_image", {"page": page_index, "xref": image.xref}
                    )
                )
                menu.addAction("删除图片").triggered.connect(
                    lambda: self.object_action.emit(
                        "delete_image", {"page": page_index, "xref": image.xref}
                    )
                )
                menu.addSeparator()
        menu.addAction("插入文本框").triggered.connect(
            lambda: self.text_insert_requested.emit(page_index or 0, point or pymupdf.Point(72, 72))
        )
        menu.addAction("添加便签").triggered.connect(
            lambda: self.sticky_requested.emit(page_index or 0, point or pymupdf.Point(72, 72))
        )
        menu.addSeparator()
        menu.addAction("粘贴文字").triggered.connect(self.paste_text)
        menu.exec(event.globalPos())

    def _emit_word_highlight(self, page_index: int, span: TextSpan) -> None:
        self.markup_requested.emit("highlight", page_index, [span.bbox])

    def _selection_rects_to_pdf(self) -> list[pymupdf.Rect]:
        if not self.doc or not self._selection_rects:
            return []
        page = self._selection_page
        out = []
        origin = self.page_screen_rect(page)
        for screen in self._selection_rects:
            x0 = (screen.x() - origin.x()) / self.zoom
            y0 = (screen.y() - origin.y()) / self.zoom
            x1 = (screen.right() - origin.x()) / self.zoom
            y1 = (screen.bottom() - origin.y()) / self.zoom
            out.append(pymupdf.Rect(x0, y0, x1, y1))
        return out

    def _markup_rects(self, start: QPointF, end: QPointF, page_index: int) -> list[pymupdf.Rect]:
        if not self.doc:
            return []
        drag = QRectF(start, end).normalized()
        rects: list[pymupdf.Rect] = []
        try:
            for word in self.doc.require_doc()[page_index].get_text("words"):
                rect = pymupdf.Rect(word[:4])
                if drag.intersects(self._pdf_rect_to_screen(page_index, rect)):
                    rects.append(rect)
        except Exception:
            return []
        return rects

    def paste_text(self) -> None:
        if QApplication.clipboard().text() and self.doc:
            self.paste_requested.emit(self.current_page)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._preview_rect = None
            self._ink_stroke = []
            self._measure_points = []
            self._measure_text = ""
            self._clear_selection()
            if self.tool not in ("select", "hand"):
                self.set_tool("select")
                self.status_message.emit("已退出当前工具，回到选择模式")
            self.viewport().update()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all_text()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selected_annots or self._selected_image:
                self.object_action.emit("delete_selection", {})
                return
        if event.key() in (Qt.Key.Key_PageDown,):
            self.next_page()
            return
        if event.key() in (Qt.Key.Key_PageUp,):
            self.prev_page()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._inline_editor is not None:
            self.status_message.emit("请先按 Ctrl+Enter 应用或 Esc 取消文字修改，再滚动页面")
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                factor = 1.12 if delta > 0 else 1 / 1.12
                self.set_zoom(self.zoom * factor, anchor=event.position())
            event.accept()
            return
        pixel = event.pixelDelta()
        angle = event.angleDelta()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            amount = pixel.x() if not pixel.x() == 0 else int(angle.x() / 120 * 110)
            if amount == 0:
                amount = int(angle.y() / 120 * 110)
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - amount)
        else:
            amount = pixel.y() if pixel.y() else int(angle.y() / 120 * 110)
            if amount == 0:
                amount = int(angle.x() / 120 * 110)
            # A whole mouse notch scrolls 110 px (roughly half a page at
            # typical zoom), matching the responsiveness of office viewers.
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - amount)
        event.accept()

    # ---------------------------------------------------------------- helpers
    def _sample_page_background(self, block: TextBlock) -> QColor:
        """Sample the page behind a paragraph so the in-place editor blends in.

        White office pages stay white; text on a blue cover keeps its blue
        background instead of showing a white edit box.
        """
        try:
            pix = self._pixmap_for(block.page)
            if pix.isNull():
                return QColor("#FFFFFF")
            image = pix.toImage()
            dpr = max(1.0, pix.devicePixelRatio())
            line = block.line_height or block.size * 1.3
            candidates = [
                (block.bbox.x0 - 3, block.bbox.y0 + line / 2),
                (block.bbox.x0 - 3, block.bbox.y1 - line / 2),
                (block.bbox.x1 + 3, block.bbox.y0 + line / 2),
                (block.bbox.x0 + 3, block.bbox.y0 - 3),
            ]
            values = []
            for x, y in candidates:
                px = int(max(0, min(image.width() - 1, x * self.zoom * dpr)))
                py = int(max(0, min(image.height() - 1, y * self.zoom * dpr)))
                color = image.pixelColor(px, py)
                if color.isValid():
                    values.append(color)
            if not values:
                return QColor("#FFFFFF")
            red = sum(c.red() for c in values) // len(values)
            green = sum(c.green() for c in values) // len(values)
            blue = sum(c.blue() for c in values) // len(values)
            return QColor(red, green, blue)
        except Exception:
            return QColor("#FFFFFF")

    def _begin_inline_edit(self, block: TextBlock, anchor: QPointF | None = None) -> None:
        if self._inline_editor is not None:
            self._close_inline(commit=True)
        screen = self._pdf_rect_to_screen(block.page, block.bbox)
        if screen.isEmpty():
            return
        vw = self.viewport().width()
        vh = self.viewport().height()
        # Keep the editor exactly on the paragraph, without a border, shadow or
        # footer.  Only a page-colored backdrop hides the original glyphs.
        page_width, _ = self.doc.page_size(block.page)
        short_line = block.line_count <= 1 and block.bbox.width < page_width * 0.55
        if short_line:
            width = max(240, min(int(screen.width()) + 150, vw - 4))
        else:
            width = max(28, min(int(screen.width()) + 6, vw - 4))
        height = max(18, min(int(screen.height()) + 6, vh - 4))
        x = max(2, min(int(screen.x()) - 2, vw - width - 2))
        y = max(2, min(int(screen.y()) - 2, vh - height - 2))
        color = "#%02X%02X%02X" % tuple(max(0, min(255, int(c * 255))) for c in block.color)
        family, _ = pdf_font_family_and_file(
            block.font, bold=block.bold, italic=block.italic
        )
        # QTextEdit's proportional line height is relative to Qt's normal line
        # spacing (roughly 1.2 * font size), while the PDF value is a multiple
        # of the font size.  Convert so the edited lines occupy the same
        # vertical rhythm as the original PDF.
        line_height = (
            block.line_height / (block.size * 1.6) if block.size else 0.86
        )
        backdrop = QWidget(self.viewport())
        background = self._sample_page_background(block)
        backdrop.setStyleSheet(f"background-color:{background.name()};")
        backdrop.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        backdrop.setGeometry(x, y, width, height)
        backdrop.show()
        editor = InlineTextEditor(
            self.viewport(),
            block.text,
            font_size=block.size * self.zoom,
            color=color,
            font_family=family,
            line_height=line_height,
        )
        editor.setGeometry(x, y, width, height)
        editor.commit_requested.connect(self._on_inline_commit)
        editor.cancel_requested.connect(self._on_inline_cancel)
        editor.textChanged.connect(self._fit_inline_editor)
        self._inline_backdrop = backdrop
        self._inline_editor = editor
        self._inline_block = block
        self._inline_min_height = height
        backdrop.raise_()
        editor.show()
        editor.raise_()
        editor.setFocus()
        local = (anchor - QPointF(x, y)) if anchor is not None else QPointF(0, 0)
        editor.place_caret(local.toPoint())
        QTimer.singleShot(0, self._fit_inline_editor)
        self.statusbar_hint = "直接在文字上修改 · Ctrl+Enter 应用 · Esc 取消 · 点击页面其他位置也会应用"
        self.status_message.emit(self.statusbar_hint)

    def _fit_inline_editor(self) -> None:
        editor = self._inline_editor
        backdrop = self._inline_backdrop
        if editor is None or backdrop is None:
            return
        document_height = int(editor.document().size().height()) + 8
        available = max(24, self.viewport().height() - editor.y() - 3)
        height = min(available, max(self._inline_min_height, document_height))
        editor.setFixedHeight(height)
        editor.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if document_height > available
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        backdrop.setGeometry(editor.geometry())

    def _on_inline_commit(self, text: str) -> None:
        block = self._inline_block
        editor = self._inline_editor
        backdrop = self._inline_backdrop
        self._inline_editor = None
        self._inline_backdrop = None
        self._inline_block = None
        if editor is not None:
            editor._finished = True
            editor.hide()
            editor.deleteLater()
        if backdrop is not None:
            backdrop.hide()
            backdrop.deleteLater()
        if block is not None:
            self.text_block_commit.emit(block, text)

    def _on_inline_cancel(self) -> None:
        editor = self._inline_editor
        backdrop = self._inline_backdrop
        self._inline_editor = None
        self._inline_backdrop = None
        self._inline_block = None
        if editor is not None:
            editor._finished = True
            editor.hide()
            editor.deleteLater()
        if backdrop is not None:
            backdrop.hide()
            backdrop.deleteLater()
        self.status_message.emit("已取消文字修改")

    def _close_inline(self, *, commit: bool) -> None:
        if self._inline_editor is None:
            return
        if commit:
            text = self._inline_editor.toPlainText()
            self._on_inline_commit(text)
        else:
            self._on_inline_cancel()

    def _default_image_rect(self, page_index: int, point: pymupdf.Point) -> pymupdf.Rect:
        w = 240.0
        h = 160.0
        page = self.doc.require_doc()[page_index]
        x = min(max(0, point.x), max(0, page.rect.width - w))
        y = min(max(0, point.y), max(0, page.rect.height - h))
        return pymupdf.Rect(x, y, x + w, y + h)

    def _default_stamp_rect(self, page_index: int, point: pymupdf.Point) -> pymupdf.Rect:
        w = 150.0
        h = 62.0
        page = self.doc.require_doc()[page_index]
        x = min(max(0, point.x - w / 2), max(0, page.rect.width - w))
        y = min(max(0, point.y - h / 2), max(0, page.rect.height - h))
        return pymupdf.Rect(x, y, x + w, y + h)

    def _default_signature_rect(self, page_index: int, point: pymupdf.Point) -> pymupdf.Rect:
        w = 160.0
        h = 64.0
        page = self.doc.require_doc()[page_index]
        x = min(max(0, point.x - w / 2), max(0, page.rect.width - w))
        y = min(max(0, point.y - h / 2), max(0, page.rect.height - h))
        return pymupdf.Rect(x, y, x + w, y + h)

    def _capture_region(self, page_index: int, pdf_rect: pymupdf.Rect) -> None:
        if not self.doc:
            return
        page = self.doc.require_doc()[page_index]
        clip = pymupdf.Rect(pdf_rect)
        if page.rotation:
            clip = clip * page.rotation_matrix
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            QApplication.clipboard().setImage(image)
            self.screenshot_taken.emit(image)
            self.status_message.emit("截图已复制到剪贴板")
        except Exception as exc:
            self.status_message.emit(f"截图失败：{exc}")

    def _update_measure(self) -> None:
        if len(self._measure_points) >= 2:
            pno1, p1 = self._measure_points[-2]
            pno2, p2 = self._measure_points[-1]
            if pno1 == pno2:
                dist = math.hypot(p2.x - p1.x, p2.y - p1.y)
                self._measure_text = f"{dist:.1f} pt  /  {dist * 0.3528:.1f} mm"

    def selected_object(self) -> dict[str, Any]:
        if self._selected_annots:
            annot = self._selected_annots[0]
            return {"kind": "annot", "page": annot.page, "xref": annot.xref, "rect": annot.rect, "content": annot.content}
        if self._selected_image:
            return {"kind": "image", "page": self._selected_image.page, "xref": self._selected_image.xref, "rect": self._selected_image.bbox}
        if self._selected_span:
            span = self._selected_span
            return {"kind": "text", "page": span.page, "span": span, "rect": span.bbox}
        return {}

    def clear_object_selection(self) -> None:
        self._selected_annots = []
        self._selected_image = None
        self._selected_span = None
        self.viewport().update()

    def select_annotation(self, page_index: int, xref: int) -> None:
        if not self.doc:
            return
        for annot in self.doc.annotations(page_index):
            if annot.xref == xref:
                self._selected_annots = [annot]
                self._selected_image = None
                self._selected_span = None
                self.goto_page(page_index)
                self.viewport().update()
                return

    def set_search_hits(self, hits: list[tuple[int, pymupdf.Rect]], active: int = -1) -> None:
        self.search_hits = list(hits)
        self.active_hit = active
        self.viewport().update()

    def focus_hit(self, index: int) -> None:
        if 0 <= index < len(self.search_hits):
            page_index, rect = self.search_hits[index]
            self.active_hit = index
            self.goto_page(page_index)
            screen = self._pdf_rect_to_screen(page_index, rect)
            layout = self._layout_for(page_index)
            if layout:
                self.verticalScrollBar().setValue(
                    max(0, int(layout.y + screen.center().y() - self.viewport().height() / 2))
                )
            self.viewport().update()

    def page_thumbnail(self, index: int, width: int = 124) -> QPixmap:
        if not self.doc:
            return QPixmap()
        try:
            w, h = self.doc.page_size(index)
            zoom = width / max(1.0, w)
            pix = self.doc.render(index, zoom, annots=False)
            fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            return QPixmap.fromImage(image)
        except Exception:
            return QPixmap()
