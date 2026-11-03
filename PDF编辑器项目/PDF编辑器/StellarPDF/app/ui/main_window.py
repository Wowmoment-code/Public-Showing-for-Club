"""Main window: WPS-inspired ribbon shell and all command handlers."""
from __future__ import annotations

import base64
import csv
import ctypes
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pymupdf
from PySide6.QtCore import QByteArray, QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from PIL import Image

from ..config import (
    APP_NAME,
    APP_NAME_EN,
    APP_VERSION,
    DATA_DIR,
    EXPORT_DIR,
    SUPPORTED_IMAGES,
    SUPPORTED_OPEN,
    cjk_font_file,
    ensure_dirs,
)
from ..core import ai as ai_core
from ..core import compare as compare_core
from ..core import convert as convert_core
from ..core import ocr as ocr_core
from ..core import operations as ops
from ..core.document import PasswordInvalid, PasswordRequired, PdfDocument, PdfError, TextSpan
from ..icons import app_icon, icon, pixmap
from ..store import store
from ..theme import C
from .imageutil import qimage_png
from .dialogs import (
    AboutDialog,
    AIDialog,
    BackgroundDialog,
    BatchConvertDialog,
    BlankPageDialog,
    BookmarkDialog,
    CompareDialog,
    ConvertOptionsDialog,
    CropDialog,
    EncryptDialog,
    FormFieldDialog,
    FormFillDialog,
    HeaderFooterDialog,
    ImageToPdfDialog,
    InsertPagesDialog,
    LinkDialog,
    MergeDialog,
    MetadataDialog,
    MovePageDialog,
    OcrDialog,
    PageNumberDialog,
    PageSizeDialog,
    PasswordDialog,
    PermissionDialog,
    PropertiesDialog,
    ReplaceDialog,
    ShortcutsDialog,
    SignatureDialog,
    SplitDialog,
    StampDialog,
    TaskProgressDialog,
    TextEditDialog,
    TextInsertDialog,
    TextResultDialog,
    WatermarkDialog,
    parse_page_ranges,
)
from .ribbon import RibbonBar
from .sidebar import Sidebar
from .statusbar import StatusBar
from .titlebar import TitleBar
from .viewer import PdfView
from .welcome import WelcomePage
from .widgets import Toast
from .worker import FunctionWorker


ALWAYS_ACTIONS = {
    "file.open",
    "file.new",
    "convert.word_pdf",
    "convert.excel_pdf",
    "convert.ppt_pdf",
    "convert.images_pdf",
    "convert.batch",
    "help.shortcuts",
    "ai.about",
    "ai.local",
}

TOOL_ACTIONS = {
    "tool.select": "select",
    "tool.hand": "hand",
    "annot.highlight": "highlight",
    "annot.underline": "underline",
    "annot.strike": "strike",
    "annot.squiggly": "squiggly",
    "annot.area_highlight": "area_highlight",
    "annot.sticky": "sticky",
    "annot.note": "note",
    "annot.textbox": "textbox",
    "annot.ink": "ink",
    "annot.rect": "rect",
    "annot.ellipse": "ellipse",
    "annot.arrow": "arrow",
    "annot.line": "line",
    "annot.stamp": "stamp",
    "annot.signature": "signature",
    "edit.text": "edit_text",
    "edit.image": "image",
    "edit.textbox": "textbox",
    "edit.link": "link",
    "tools.measure": "measure",
    "tools.area": "area",
    "tools.screenshot": "screenshot",
    "protect.redact": "redact",
    "form.text": "form_text",
    "form.checkbox": "form_checkbox",
    "form.radio": "form_radio",
    "form.dropdown": "form_dropdown",
    "form.signature": "form_signature",
}

VIEW_ACTIONS = {
    "view.continuous": "continuous",
    "view.single": "single",
    "view.double": "double",
}


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (0.1, 0.1, 0.1)
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


class ViewerHost(QWidget):
    """Container that keeps floating actions above the canvas."""

    ai_clicked = Signal()
    exit_fullscreen_clicked = Signal()

    def __init__(self, viewer: PdfView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(viewer)
        self.viewer = viewer
        self.ai_button = QToolButton(self)
        self.ai_button.setText("AI 助手")
        self.ai_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.ai_button.setIcon(icon("sparkles", "white", 16))
        self.ai_button.setIconSize(QSize(16, 16))
        self.ai_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_button.setFixedSize(102, 34)
        self.ai_button.setStyleSheet(
            "QToolButton { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #6A4DFF, stop:1 #2F6BFF); color:white; border:none; border-radius:17px;"
            "font-weight:600; font-size:9pt; padding-left:8px; }"
            "QToolButton:hover { background:#3B63F3; }"
        )
        self.ai_button.clicked.connect(self.ai_clicked)
        self.ai_button.raise_()
        self.exit_fullscreen_button = QToolButton(self)
        self.exit_fullscreen_button.setText("退出全屏  Esc")
        self.exit_fullscreen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_fullscreen_button.setFixedSize(112, 32)
        self.exit_fullscreen_button.setStyleSheet(
            "QToolButton { background:rgba(30,35,46,205); color:white; border:none;"
            "border-radius:16px; font-size:9pt; }"
            "QToolButton:hover { background:#2F6BFF; }"
        )
        self.exit_fullscreen_button.clicked.connect(self.exit_fullscreen_clicked)
        self.exit_fullscreen_button.hide()

    def set_fullscreen(self, active: bool) -> None:
        self.exit_fullscreen_button.setVisible(active)
        if active:
            self.exit_fullscreen_button.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.ai_button.move(max(12, self.width() - 122), max(12, self.height() - 56))
        self.ai_button.raise_()
        self.exit_fullscreen_button.move(max(12, self.width() - 134), 14)
        self.exit_fullscreen_button.raise_()


class MainWindow(QMainWindow):
    def __init__(self, startup_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)
        self.doc_model = PdfDocument()
        self.store = store()
        self._current_path: str | None = None
        self._last_dir = self.store.settings.get("last_dir") or str(Path.home())
        self._search_hits: list = []
        self._active_worker: FunctionWorker | None = None
        self._pending_text: str | None = None
        self._text_box_mode = False
        self._fullscreen = False
        self._fullscreen_state: dict[str, bool] = {}
        self._saved_geometry_before_fullscreen = None
        self._shape_color = "#2F6BFF"
        self._resize_edges = Qt.Edge(0)
        self._annot_colors = {
            "highlight": "#FFD84D",
            "underline": "#2F6BFF",
            "strike": "#E5484D",
            "squiggly": "#EE8A2E",
            "area": "#FFD84D",
            "ink": "#E5484D",
        }
        self._current_annot_kind = "highlight"
        self._last_autosave = 0.0
        ensure_dirs()
        self._build_ui()
        self._wire_signals()
        self._build_shortcuts()
        self._restore_geometry()
        self._update_document_actions(False)
        self.show_welcome()
        if startup_path:
            QTimer.singleShot(120, lambda: self.open_path(startup_path))

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("RootWindow")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.titlebar = TitleBar(root)
        outer.addWidget(self.titlebar)
        self.ribbon = RibbonBar(root)
        self.ribbon.setSizePolicy(self.ribbon.sizePolicy().horizontalPolicy(), self.ribbon.sizePolicy().verticalPolicy())
        outer.addWidget(self.ribbon)

        body = QWidget(root)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.sidebar = Sidebar(body)
        body_layout.addWidget(self.sidebar)

        self.content_stack = QStackedWidget(body)
        self.welcome = WelcomePage(self.content_stack)
        self.content_stack.addWidget(self.welcome)
        self.viewer = PdfView(self.content_stack)
        self.viewer_host = ViewerHost(self.viewer, self.content_stack)
        self.content_stack.addWidget(self.viewer_host)
        body_layout.addWidget(self.content_stack, 1)
        outer.addWidget(body, 1)

        self.statusbar = StatusBar(root)
        outer.addWidget(self.statusbar)
        # A visible native size grip is a reliable fallback on frameless
        # windows, where custom edge hit-testing can be intercepted by DWM.
        self.size_grip = QSizeGrip(self.statusbar)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setToolTip("拖动调整窗口大小")
        self.statusbar.layout().addWidget(self.size_grip)
        self.toast = Toast(self)
        self.sidebar.hide()

    def _wire_signals(self) -> None:
        self.titlebar.open_clicked.connect(self.open_pdf_dialog)
        self.titlebar.save_clicked.connect(self.save_document)
        self.titlebar.print_clicked.connect(self.print_document)
        self.titlebar.undo_clicked.connect(self.undo)
        self.titlebar.redo_clicked.connect(self.redo)
        self.titlebar.search_requested.connect(self._title_search)
        self.titlebar.minimize_clicked.connect(self.minimize_window)
        self.titlebar.maximize_clicked.connect(self.toggle_maximize)
        self.titlebar.close_clicked.connect(self.close)
        self.titlebar.local_clicked.connect(lambda: self.toast.show_message("本地离线处理，文件不会上传到网络"))
        self.titlebar.menu_clicked.connect(self._show_app_menu)

        self.ribbon.command.connect(self.handle_command)
        self.ribbon.tabbar.currentChanged.connect(self._on_tab_changed)

        self.welcome.open_requested.connect(self.open_pdf_dialog)
        self.welcome.new_requested.connect(self.new_document)
        self.welcome.merge_requested.connect(self.merge_documents_dialog)
        self.welcome.recent_open.connect(self.open_path)
        self.welcome.recent_remove.connect(self._remove_recent)
        self.welcome.tool_requested.connect(self.handle_command)

        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.zoom_changed.connect(self._on_zoom_changed)
        self.viewer.selection_changed.connect(self._on_selection_changed)
        self.viewer.status_message.connect(self._toast_status)
        self.viewer.text_edit_requested.connect(self._edit_span)
        self.viewer.text_block_commit.connect(self._replace_text_block)
        self.viewer.text_insert_requested.connect(self._insert_text_at)
        self.viewer.image_insert_requested.connect(self._insert_image_at)
        self.viewer.markup_requested.connect(self._add_markup)
        self.viewer.shape_requested.connect(self._add_shape)
        self.viewer.ink_requested.connect(self._add_ink)
        self.viewer.sticky_requested.connect(self._add_sticky)
        self.viewer.stamp_requested.connect(self._add_stamp_at)
        self.viewer.signature_requested.connect(self._add_signature_at)
        self.viewer.link_requested.connect(self._add_link_at)
        self.viewer.redact_requested.connect(self._redact_at)
        self.viewer.form_requested.connect(self._add_form_at)
        self.viewer.object_action.connect(self._on_object_action)
        self.viewer.screenshot_taken.connect(lambda _: None)
        self.viewer.paste_requested.connect(self._paste_text)
        self.viewer.cursor_page_changed.connect(lambda p: self.statusbar.set_message(f"第 {p + 1} 页"))
        self.viewer.tool_changed.connect(self._on_tool_changed)
        self.viewer_host.ai_clicked.connect(lambda: self.handle_command("ai.qa"))
        self.viewer_host.exit_fullscreen_clicked.connect(self.toggle_fullscreen)

        self.sidebar.page_selected.connect(self._sidebar_page_selected)
        self.sidebar.pages_selected.connect(self._sidebar_pages_selected)
        self.sidebar.page_order_changed.connect(self._reorder_pages)
        self.sidebar.extract_pages_requested.connect(self._extract_pages)
        self.sidebar.add_page_requested.connect(lambda: self.handle_command("page.insert_blank"))
        self.sidebar.delete_pages_requested.connect(lambda: self.handle_command("page.delete"))
        self.sidebar.rotate_page_requested.connect(lambda: self.handle_command("page.rotate_right"))
        self.sidebar.bookmark_selected.connect(self._goto_page)
        self.sidebar.bookmark_add_requested.connect(self._add_bookmark)
        self.sidebar.bookmark_delete_requested.connect(self._delete_bookmark)
        self.sidebar.annot_selected.connect(self._goto_annotation)
        self.sidebar.annot_delete_requested.connect(self._delete_selected_annotation)
        self.sidebar.annot_export_requested.connect(self._export_annotations)
        self.sidebar.attachment_add_requested.connect(self._add_attachment)
        self.sidebar.attachment_save_requested.connect(self._save_attachment)
        self.sidebar.attachment_delete_requested.connect(self._delete_attachment)
        self.sidebar.search_requested.connect(self._perform_search)
        self.sidebar.search_hit_selected.connect(self._select_search_hit)
        self.sidebar.form_fill_requested.connect(lambda: self.handle_command("form.fill"))
        self.sidebar.form_manage_requested.connect(lambda: self.handle_command("form.manage"))

        self.statusbar.page_requested.connect(self._goto_page)
        self.statusbar.zoom_requested.connect(self._status_zoom)
        self.statusbar.fit_width_requested.connect(self.viewer.fit_width)
        self.statusbar.fit_page_requested.connect(self.viewer.fit_page)
        self.statusbar.view_mode_requested.connect(self._set_view_mode)
        self.statusbar.fullscreen_requested.connect(self.toggle_fullscreen)

    def _build_shortcuts(self) -> None:
        shortcuts = {
            "Ctrl+N": "file.new",
            "Ctrl+O": "file.open",
            "Ctrl+S": "file.save",
            "Ctrl+Shift+S": "file.save_as",
            "Ctrl+P": "file.print",
            "Ctrl+Z": "edit.undo",
            "Ctrl+Y": "edit.redo",
            "Ctrl+Shift+Z": "edit.redo",
            "Ctrl+F": "edit.find",
            "Ctrl+H": "edit.replace",
            "Ctrl+W": "file.close",
            "Ctrl+0": "view.fit_page",
            "Ctrl+1": "view.actual_size",
            "Ctrl++": "view.zoom_in",
            "Ctrl+=": "view.zoom_in",
            "Ctrl+-": "view.zoom_out",
            "F11": "view.fullscreen",
            "Alt+F10": "window.maximize",
            "Alt+F9": "window.minimize",
            "F1": "help.shortcuts",
        }
        self._shortcuts = []
        for key, action in shortcuts.items():
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(lambda a=action: self.handle_command(a))
            self._shortcuts.append(sc)
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.setContext(Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self._escape)
        self._shortcuts.append(esc)

    def _on_tab_changed(self, index: int) -> None:
        # Keep the status hint contextual without stealing focus.
        key = self.ribbon.current_tab()
        hints = {
            "home": "首页 · 打开、保存、阅读视图与缩放",
            "edit": "编辑 · 直接修改文字、图片与页面装饰",
            "page": "页面 · 插入、删除、旋转、拆分与合并",
            "annot": "注释 · 高亮、批注、图章与手写签名",
            "tools": "工具 · OCR、压缩、比较、测量与批量处理",
            "fill": "填写与签署 · 表单填写、控件与签名",
            "protect": "保护 · 密码、权限、密文与水印",
            "convert": "转换 · PDF 与 Office、图片、HTML 互转",
            "ai": "AI · 本地摘要、问答与关键词",
        }
        self.statusbar.set_message(hints.get(key, "就绪"))

    def _restore_geometry(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1440, 900)
        restored = False
        geometry = self.store.settings.get("geometry")
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
                restored = True
            except Exception:
                pass
        if not restored:
            width = min(1440, max(1000, available.width() - 60))
            height = min(900, max(680, available.height() - 100))
            self.resize(width, height)
        # A geometry saved on a larger/other monitor must never put the window
        # controls or ribbon outside the current screen.
        max_width = max(900, available.width() - 20)
        max_height = max(620, available.height() - 40)
        if self.width() > max_width or self.height() > max_height:
            self.resize(min(self.width(), max_width), min(self.height(), max_height))
        frame = self.frameGeometry()
        if not available.intersects(frame) or not available.contains(frame.center()):
            self.move(
                available.x() + max(0, (available.width() - self.width()) // 2),
                available.y() + max(0, (available.height() - self.height()) // 2),
            )

    # ------------------------------------------------------------- lifecycle
    def _startup(self) -> None:
        self.welcome.refresh(self.store)

    def show_welcome(self) -> None:
        self.content_stack.setCurrentWidget(self.welcome)
        self.sidebar.hide()
        self.welcome.refresh(self.store)
        self.titlebar.set_document("", False, False)
        self.statusbar.set_document_state(False)
        self.setWindowTitle(APP_NAME)
        self._current_path = None

    def open_pdf_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF", self._last_dir, SUPPORTED_OPEN)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            self.toast.show_message("文件不存在")
            return False
        if not self._maybe_save():
            return False
        password = None
        for _ in range(4):
            try:
                self.doc_model.open(path, password)
                break
            except PasswordRequired:
                dlg = PasswordDialog(
                    self,
                    "打开受保护的 PDF",
                    f"“{os.path.basename(path)}” 需要密码才能打开。",
                )
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return False
                password = dlg.value()
            except PasswordInvalid:
                QMessageBox.warning(self, "密码错误", "密码不正确，请重新输入。")
                password = None
            except PdfError as exc:
                QMessageBox.critical(self, "无法打开 PDF", str(exc))
                return False
        else:
            return False
        self._last_dir = os.path.dirname(path)
        self._current_path = path
        self.doc_model.page = 0
        self.viewer.set_document(self.doc_model)
        self.content_stack.setCurrentWidget(self.viewer_host)
        self.sidebar.show()
        try:
            self.sidebar.set_document(self.doc_model)
        except Exception as exc:
            self._log_ui_error("sidebar", exc)
        self.viewer.set_view_mode(self.store.settings.get("view_mode", "continuous"))
        self._set_view_mode(self.store.settings.get("view_mode", "continuous"))
        self.statusbar.set_document_state(True)
        self._update_document_actions(True)
        self.set_tool("select")
        try:
            self._post_open()
        except Exception as exc:
            self._log_ui_error("post_open", exc)
        # Always finish with a fully usable shell, even if an optional panel
        # (bookmarks, thumbnails, attachments) on an unusual PDF failed.
        self._update_document_actions(True)
        self._update_document_ui()
        try:
            self.viewer.fit_width()
            self.viewer.verticalScrollBar().setValue(0)
        except Exception as exc:
            self._log_ui_error("fit_width", exc)
        return True

    @staticmethod
    def _log_ui_error(where: str, exc: Exception) -> None:
        try:
            ensure_dirs()
            with open(DATA_DIR / "startup.log", "a", encoding="utf-8") as fh:
                fh.write(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')}  UI {where} failed: "
                    f"{type(exc).__name__}: {exc}\n"
                )
        except Exception:
            pass

    def _post_open(self) -> None:
        if not self.doc_model.is_open:
            return
        self.viewer.goto_page(0)
        self.sidebar.set_current_page(0)
        self._update_document_ui()
        self._remember_thumbnail()
        self.statusbar.set_message("就绪 · 双击文字可直接编辑")
        if self.doc_model.is_encrypted:
            self.toast.show_message("已打开受保护的 PDF")

    def _remember_thumbnail(self) -> None:
        if not self.doc_model.is_open or not self.doc_model.path:
            return
        try:
            pix = self.doc_model.render(0, 0.45, annots=False)
            data = pix.tobytes("png")
            self.store.touch_recent(
                self.doc_model.path,
                self.doc_model.title,
                self.viewer.current_page,
                data,
            )
        except Exception:
            pass

    def _update_document_ui(self) -> None:
        has_doc = self.doc_model.is_open
        self._update_document_actions(has_doc)
        self.titlebar.set_document(
            self.doc_model.file_name if has_doc else "",
            self.doc_model.dirty if has_doc else False,
            has_doc,
        )
        self.titlebar.set_history(
            self.doc_model.can_undo() if has_doc else False,
            self.doc_model.can_redo() if has_doc else False,
        )
        count = self.doc_model.page_count if has_doc else 0
        self.statusbar.set_page(self.viewer.current_page, count)
        self.statusbar.set_zoom(self.viewer.zoom)
        self.setWindowTitle(
            f"{self.doc_model.file_name} - {APP_NAME}" if has_doc else APP_NAME
        )

    def _update_document_actions(self, has_doc: bool) -> None:
        # Keep every ribbon command clickable at all times.  Commands that need
        # a document show a clear "请先打开 PDF" hint instead of silently doing
        # nothing, and an odd document can never leave the whole ribbon greyed
        # out.  This is deliberately more forgiving than Windows ribbon apps.
        for action, buttons in self.ribbon._buttons.items():
            for button in buttons:
                button.setEnabled(True)
        self.titlebar.search.setEnabled(bool(has_doc))
        if not has_doc:
            self.titlebar.search.clear()

    def _maybe_save(self) -> bool:
        if not self.doc_model.is_open or not self.doc_model.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("保存更改")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"是否保存对“{self.doc_model.file_name}”的更改？")
        box.setInformativeText("未保存的修改将会丢失。")
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.raise_()
        box.activateWindow()
        save = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save_document()
        if box.clickedButton() is discard:
            return True
        return False

    def save_document(self) -> bool:
        if not self.doc_model.is_open:
            return False
        if not self.doc_model.path:
            return self.save_document_as()
        return self._save_to(self.doc_model.path)

    def save_document_as(self) -> bool:
        if not self.doc_model.is_open:
            return False
        default = self.doc_model.path or os.path.join(self._last_dir, "未命名文档.pdf")
        if default.lower().endswith(".pdf"):
            default = default[:-4] + "_已编辑.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "另存为", default, "PDF 文件 (*.pdf)")
        if not path:
            return False
        return self._save_to(path)

    def _save_to(self, target: str) -> bool:
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            current_page = self.viewer.current_page
            saved = self.doc_model.save(target)
            QApplication.restoreOverrideCursor()
            self._current_path = saved
            self._last_dir = os.path.dirname(saved)
            self.viewer.refresh()
            self.viewer.goto_page(min(current_page, self.doc_model.page_count - 1))
            self.sidebar.set_document(self.doc_model)
            self._update_document_ui()
            self._remember_thumbnail()
            self.toast.show_message("已保存")
            return True
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "保存失败", str(exc))
            return False

    def new_document(self) -> None:
        if not self._maybe_save():
            return
        self.doc_model.new_blank()
        self.doc_model.dirty = True
        self._current_path = None
        self.doc_model.page = 0
        self.viewer.set_document(self.doc_model)
        self.sidebar.set_document(self.doc_model)
        self.content_stack.setCurrentWidget(self.viewer_host)
        self.sidebar.show()
        self.statusbar.set_document_state(True)
        self._update_document_actions(True)
        self._set_view_mode("continuous")
        self.set_tool("select")
        QTimer.singleShot(40, self.viewer.fit_page)
        self._update_document_ui()
        self.toast.show_message("已新建空白 PDF")

    def close_document(self) -> None:
        if not self.doc_model.is_open:
            return
        if not self._maybe_save():
            return
        self.doc_model.close()
        self._current_path = None
        self.viewer.set_document(None)
        self.sidebar.set_document(None)
        self.show_welcome()

    def _show_app_menu(self) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("新建 PDF", lambda: self.handle_command("file.new")).setShortcut(QKeySequence("Ctrl+N"))
        menu.addAction("打开 PDF…", self.open_pdf_dialog).setShortcut(QKeySequence("Ctrl+O"))
        menu.addSeparator()
        menu.addAction("保存", self.save_document).setShortcut(QKeySequence("Ctrl+S"))
        menu.addAction("另存为…", self.save_document_as).setShortcut(QKeySequence("Ctrl+Shift+S"))
        menu.addAction("打印…", self.print_document).setShortcut(QKeySequence("Ctrl+P"))
        menu.addAction("文档属性", lambda: self.handle_command("file.properties"))
        menu.addSeparator()
        recent_menu = menu.addMenu("最近打开")
        if self.store.recent:
            for entry in self.store.recent[:8]:
                action = recent_menu.addAction(entry.get("title") or os.path.basename(entry["path"]))
                action.triggered.connect(lambda checked=False, p=entry["path"]: self.open_path(p))
            recent_menu.addSeparator()
            recent_menu.addAction("清空列表", lambda: self._remove_recent("__clear__"))
        else:
            recent_menu.addAction("暂无最近文档").setEnabled(False)
        menu.addSeparator()
        menu.addAction("快捷键与帮助", lambda: self.handle_command("help.shortcuts"))
        menu.addAction(f"关于 {APP_NAME}", lambda: AboutDialog(self).exec())
        menu.addSeparator()
        menu.addAction("退出", self.close)
        menu.exec(self.titlebar.btn_menu.mapToGlobal(QPoint(0, self.titlebar.btn_menu.height())))

    def _remove_recent(self, path: str) -> None:
        if path == "__clear__":
            self.store.clear_recent()
        else:
            self.store.remove_recent(path)
        self.welcome.refresh(self.store)

    def _title_search(self, query: str) -> None:
        if not self.doc_model.is_open:
            return
        self.sidebar.show_panel("search")
        self.sidebar.search_edit.setText(query)
        self._perform_search(query)

    # --------------------------------------------------------------- window
    def toggle_maximize(self) -> None:
        if self.isMaximized() or bool(self.windowState() & Qt.WindowState.WindowMaximized):
            self.showNormal()
        else:
            self.showMaximized()

    def minimize_window(self) -> None:
        self.showMinimized()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())

    def toggle_fullscreen(self) -> None:
        if not self._fullscreen:
            self._fullscreen_state = {
                "title": self.titlebar.isVisible(),
                "ribbon": self.ribbon.isVisible(),
                "sidebar": self.sidebar.isVisible(),
                "status": self.statusbar.isVisible(),
            }
            self.titlebar.hide()
            self.ribbon.hide()
            self.sidebar.hide()
            self.statusbar.hide()
            self.showFullScreen()
            self._fullscreen = True
            self.viewer_host.set_fullscreen(True)
            self.toast.show_message("全屏阅读模式 · 按 Esc 或 F11，或点击右上角退出", 3200)
        else:
            self.showNormal()
            self.titlebar.setVisible(self._fullscreen_state.get("title", True))
            self.ribbon.setVisible(self._fullscreen_state.get("ribbon", True))
            self.sidebar.setVisible(self._fullscreen_state.get("sidebar", False) and self.doc_model.is_open)
            self.statusbar.setVisible(self._fullscreen_state.get("status", True))
            self._fullscreen = False
            self.viewer_host.set_fullscreen(False)

    def _escape(self) -> None:
        if self._fullscreen:
            self.toggle_fullscreen()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._maybe_save():
            event.ignore()
            return
        try:
            self.store.settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.store.settings["view_mode"] = self.viewer.view_mode
            self.store.settings["zoom"] = self.viewer.zoom
            self.store.settings["last_dir"] = self._last_dir
            self.store.save_settings()
            self.store.save_recent()
        except Exception:
            pass
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.cancel()
            self._active_worker.wait(1500)
        self.doc_model.close()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and not self.isMaximized() and not self.isFullScreen():
            try:
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    pos = self.mapFromGlobal(QPoint(x, y))
                    # Never steal clicks from the three window control buttons.
                    if pos.y() < 44 and pos.x() > self.width() - 160:
                        return super().nativeEvent(event_type, message)
                    border = 6
                    left = pos.x() < border
                    right = pos.x() >= self.width() - border
                    top = pos.y() < border
                    bottom = pos.y() >= self.height() - border
                    if top and left:
                        return True, 13
                    if top and right:
                        return True, 14
                    if bottom and left:
                        return True, 16
                    if bottom and right:
                        return True, 17
                    if left:
                        return True, 10
                    if right:
                        return True, 11
                    if top:
                        return True, 12
                    if bottom:
                        return True, 15
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # --------------------------------------------------------------- drag/drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_path(path)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    # ------------------------------------------------------------- UI state
    def _on_page_changed(self, index: int) -> None:
        if not self.doc_model.is_open:
            return
        self.doc_model.page = index
        self.sidebar.set_current_page(index)
        self.statusbar.set_page(index, self.doc_model.page_count)
        self.statusbar.set_message(f"第 {index + 1} 页 · {self.viewer.view_mode}")

    def _on_zoom_changed(self, zoom: float) -> None:
        self.statusbar.set_zoom(zoom)
        self.statusbar.set_message(f"缩放 {int(zoom * 100)}%")

    def _on_selection_changed(self, text: str) -> None:
        if text:
            self.statusbar.set_message(f"已选择 {len(text)} 个字符 · Ctrl+C 复制")
        else:
            self.statusbar.set_message("就绪 · 双击文字可直接编辑")

    def _toast_status(self, message: str) -> None:
        self.statusbar.set_message(message)
        self.toast.show_message(message)

    def _goto_page(self, index: int) -> None:
        if self.doc_model.is_open:
            self.viewer.goto_page(index)

    def _status_zoom(self, value: float) -> None:
        if value == -1:
            self.viewer.zoom_out()
        elif value == -2:
            self.viewer.zoom_in()
        else:
            self.viewer.set_zoom(value)

    def _set_view_mode(self, mode: str) -> None:
        if not self.doc_model.is_open:
            return
        self.viewer.set_view_mode(mode)
        self.statusbar.set_view_mode(self.viewer.view_mode)
        self.store.settings["view_mode"] = self.viewer.view_mode
        for action, value in VIEW_ACTIONS.items():
            self.ribbon.set_checked(action, value == self.viewer.view_mode)
        self.statusbar.set_message(
            {"continuous": "连续阅读", "single": "单页阅读", "double": "双页阅读"}.get(
                self.viewer.view_mode, "阅读"
            )
        )

    def set_tool(self, tool: str, action: str | None = None) -> None:
        if not self.doc_model.is_open:
            return
        self.viewer.set_tool(tool)
        if action is None:
            action = next((a for a, t in TOOL_ACTIONS.items() if t == tool), None)
        for a in TOOL_ACTIONS:
            self.ribbon.set_checked(a, a == action)
        hints = {
            "select": "选择工具 · 拖动选择文字，双击编辑文字",
            "hand": "手型工具 · 拖动画布",
            "highlight": "高亮 · 拖动选择文字",
            "underline": "下划线 · 拖动选择文字",
            "strike": "删除线 · 拖动选择文字",
            "squiggly": "波浪线 · 拖动选择文字",
            "area_highlight": "区域高亮 · 框选页面区域",
            "sticky": "便签 · 点击页面放置",
            "note": "文本注释 · 点击页面放置",
            "textbox": "文本框 · 拖动绘制文字区域",
            "ink": "手绘 · 在页面上按住鼠标绘制",
            "rect": "矩形 · 拖动绘制",
            "ellipse": "椭圆 · 拖动绘制",
            "arrow": "箭头 · 拖动绘制",
            "line": "直线 · 拖动绘制",
            "stamp": "图章 · 点击页面放置",
            "signature": "签名 · 点击页面放置",
            "redact": "密文 · 框选要永久移除的内容",
            "measure": "测量 · 依次点击两点",
            "area": "面积 · 框选测量区域",
            "screenshot": "截图 · 框选页面区域并复制",
            "image": "插入图片 · 点击页面放置图片",
            "edit_text": "编辑文字 · 点击要修改的文字",
            "link": "链接 · 框选区域后设置链接",
            "form_text": "表单文本域 · 拖动绘制",
            "form_checkbox": "复选框 · 拖动绘制",
            "form_radio": "单选按钮 · 拖动绘制",
            "form_dropdown": "下拉列表 · 拖动绘制",
            "form_signature": "签名域 · 拖动绘制",
        }
        self.statusbar.set_message(hints.get(tool, "就绪"))

    def _on_tool_changed(self, tool: str) -> None:
        action = next((a for a, t in TOOL_ACTIONS.items() if t == tool), None)
        for a in TOOL_ACTIONS:
            self.ribbon.set_checked(a, a == action)

    def _sidebar_page_selected(self, index: int) -> None:
        if index < 0:
            self.viewer.fit_width()
            return
        self.viewer.goto_page(index)

    def _sidebar_pages_selected(self, pages: list[int]) -> None:
        if pages:
            self.statusbar.set_message(f"已选择 {len(pages)} 页 · 可删除、旋转或导出")

    def _reorder_pages(self, order: list[int]) -> None:
        # Defer until QListWidget has finished its own drop handling; rebuilding
        # the model inside rowsMoved can invalidate the active drag operation.
        QTimer.singleShot(0, lambda: self._apply_page_order(order))

    def _apply_page_order(self, order: list[int]) -> None:
        if not self.doc_model.is_open or sorted(order) != list(range(self.doc_model.page_count)):
            return
        try:
            self.doc_model.checkpoint()
            self.doc_model.require_doc().select(order)
            self.doc_model.mark_dirty()
            current = min(self.viewer.current_page, self.doc_model.page_count - 1)
            self._after_edit("页面顺序已调整", rebuild=True)
            self.viewer.goto_page(current)
        except Exception as exc:
            QMessageBox.critical(self, "调整页面顺序失败", str(exc))
            self.sidebar.set_document(self.doc_model)

    def undo(self) -> None:
        if not self.doc_model.is_open:
            return
        if self.doc_model.undo():
            self.viewer.refresh()
            self.sidebar.set_document(self.doc_model)
            self._update_document_ui()
            self.toast.show_message("已撤销")
        else:
            self.toast.show_message("没有可撤销的操作")

    def redo(self) -> None:
        if not self.doc_model.is_open:
            return
        if self.doc_model.redo():
            self.viewer.refresh()
            self.sidebar.set_document(self.doc_model)
            self._update_document_ui()
            self.toast.show_message("已重做")
        else:
            self.toast.show_message("没有可重做的操作")

    def _after_edit(
        self,
        message: str,
        *,
        rebuild: bool = False,
        rebuild_thumbs: bool = False,
        rebuild_annots: bool = True,
    ) -> None:
        if not self.doc_model.is_open:
            return
        self.doc_model.page = self.viewer.current_page
        self.viewer.refresh()
        if rebuild:
            self.sidebar.set_document(self.doc_model)
        else:
            if rebuild_thumbs:
                self.sidebar.refresh_thumbnails()
            else:
                self.sidebar.refresh_page(self.viewer.current_page)
            if rebuild_annots:
                self.sidebar.refresh_annotations()
            # Only parse the whole outline/form set when that panel is actually
            # visible; doing it after every text edit made large PDFs feel stuck.
            if getattr(self.sidebar, "_current_panel", "") == "bookmarks":
                self.sidebar.refresh_bookmarks()
            if getattr(self.sidebar, "_current_panel", "") == "forms":
                self.sidebar.refresh_forms()
        self._update_document_ui()
        self.statusbar.set_message(message)
        self.toast.show_message(message)

    # ------------------------------------------------------------- commands
    def handle_command(self, action: str) -> None:
        try:
            self._dispatch_command(action)
        except Exception as exc:
            self._log_ui_error(f"command:{action}", exc)
            self.statusbar.set_message(f"操作失败：{exc}")
            self.toast.show_message(f"操作失败：{exc}", 4200)

    def _dispatch_command(self, action: str) -> None:
        if not self.doc_model.is_open and action not in ALWAYS_ACTIONS:
            # A checkable toolbar button toggles before the command reaches us;
            # undo that visual state when there is no document to act on.
            for tool_action in TOOL_ACTIONS:
                self.ribbon.set_checked(tool_action, False)
            for view_action in VIEW_ACTIONS:
                self.ribbon.set_checked(view_action, False)
            self.ribbon.set_checked("view.fullscreen", False)
            self.toast.show_message("请先打开一个 PDF 文档")
            return
        # File
        if action == "file.open":
            self.open_pdf_dialog()
        elif action == "file.save":
            self.save_document()
        elif action == "file.save_as":
            self.save_document_as()
        elif action == "file.print":
            self.print_document()
        elif action == "file.new":
            self.new_document()
        elif action == "file.close":
            self.close_document()
        elif action == "file.properties":
            self._show_properties()
        elif action in ("file.recent", "file.welcome"):
            if self._maybe_save():
                self.doc_model.close()
                self.show_welcome()
        # Edit
        elif action == "edit.undo":
            self.undo()
        elif action == "edit.redo":
            self.redo()
        elif action == "edit.copy":
            self.viewer.copy_selection()
        elif action == "edit.select_all":
            self.viewer.select_all_text()
        elif action == "edit.find":
            self._show_search()
        elif action == "edit.replace":
            self._replace_dialog()
        elif action == "edit.replace_all":
            self._replace_dialog(all_pages=True)
        elif action == "edit.text":
            if self.viewer.selected_text and self.viewer.edit_selected_block():
                self.ribbon.set_checked(action, False)
                self.statusbar.set_message("已打开选中文字的内嵌编辑器")
            else:
                self.set_tool("edit_text", action)
                self.toast.show_message("请点击文档中要修改的文字，光标会直接出现在原文上", 3200)
        elif action == "edit.image":
            self.set_tool("image", action)
        elif action == "edit.textbox":
            self._text_box_mode = True
            self.set_tool("textbox", action)
        elif action == "edit.link":
            self.set_tool("link", action)
        elif action in ("edit.shape_rect", "edit.shape_ellipse", "edit.shape_arrow", "edit.shape_line"):
            chosen = QColorDialog.getColor(QColor(self._shape_color), self, "形状颜色")
            if chosen.isValid():
                self._shape_color = chosen.name()
            mapping = {
                "edit.shape_rect": ("rect", "rect"),
                "edit.shape_ellipse": ("ellipse", "ellipse"),
                "edit.shape_arrow": ("arrow", "arrow"),
                "edit.shape_line": ("line", "line"),
            }
            tool, _ = mapping[action]
            self.set_tool(tool, None)
        elif action == "edit.watermark":
            self._add_watermark()
        elif action == "edit.background":
            self._background_dialog()
        elif action == "edit.header":
            self._header_footer_dialog(footer=False)
        elif action == "edit.footer":
            self._header_footer_dialog(footer=True)
        elif action == "edit.page_number":
            self._page_number_dialog()
        elif action == "edit.delete_object":
            self._delete_selected_object()
        elif action == "edit.flatten":
            self._flatten_document()
        elif action == "edit.metadata":
            self._metadata_dialog()
        elif action == "edit.fonts":
            self._font_info()
        elif action == "edit.object_properties":
            self._object_properties()
        # View
        elif action in VIEW_ACTIONS:
            self._set_view_mode(VIEW_ACTIONS[action])
        elif action == "view.fullscreen":
            self.toggle_fullscreen()
        elif action == "window.maximize":
            self.toggle_maximize()
        elif action == "window.minimize":
            self.minimize_window()
        elif action == "view.zoom_in":
            self.viewer.zoom_in()
        elif action == "view.zoom_out":
            self.viewer.zoom_out()
        elif action == "view.fit_width":
            self.viewer.fit_width()
        elif action == "view.fit_page":
            self.viewer.fit_page()
        elif action == "view.actual_size":
            self.viewer.actual_size()
        # Tools / annotation tool activation
        elif action in TOOL_ACTIONS:
            tool = TOOL_ACTIONS[action]
            if action == "annot.textbox":
                self._text_box_mode = True
            if action == "annot.color":
                return
            self.set_tool(tool, action)
        elif action == "annot.color":
            color = QColorDialog.getColor(QColor(self.viewer.annotation_color), self, "选择标注颜色")
            if color.isValid():
                self.viewer.set_annotation_color(color.name())
                self.toast.show_message("标注颜色已更新")
        elif action == "annot.width":
            value, ok = QInputDialog.getDouble(self, "线宽", "请输入线宽（pt）：", self.viewer.line_width, 0.5, 20, 1)
            if ok:
                self.viewer.set_line_width(value)
        elif action == "annot.date":
            self._pending_text = time.strftime("%Y-%m-%d")
            self.set_tool("text", None)
        elif action == "annot.manage":
            self.sidebar.show_panel("annots")
        elif action == "annot.delete":
            self._delete_selected_annotation()
        elif action == "annot.export":
            self._export_annotations()
        elif action == "annot.flatten":
            self._flatten_document()
        # Pages
        elif action == "page.insert_blank":
            self._insert_blank_pages()
        elif action == "page.insert_file":
            self._insert_pdf_dialog()
        elif action == "page.delete":
            self._delete_pages()
        elif action == "page.duplicate":
            self._duplicate_page()
        elif action == "page.move":
            self._move_page_dialog()
        elif action == "page.rotate_left":
            self._rotate_selected(-90)
        elif action == "page.rotate_right":
            self._rotate_selected(90)
        elif action == "page.crop":
            self._crop_dialog()
        elif action == "page.size":
            self._page_size_dialog()
        elif action == "page.orientation":
            self._rotate_selected(90)
        elif action == "page.extract":
            self._extract_pages()
        elif action == "page.split":
            self._split_document()
        elif action == "page.merge":
            self.merge_documents_dialog()
        elif action == "page.export":
            self._extract_pages()
        elif action == "page.replace":
            self._replace_page_dialog()
        elif action == "page.background":
            self._background_dialog()
        elif action == "page.properties":
            self._show_properties()
        elif action == "page.select_all":
            self.sidebar.thumb_list.selectAll()
        elif action == "page.invert_selection":
            for i in range(self.sidebar.thumb_list.count()):
                item = self.sidebar.thumb_list.item(i)
                item.setSelected(not item.isSelected())
        # Tools
        elif action in ("tools.search",):
            self._show_search()
        elif action == "tools.bookmark":
            self.sidebar.show_panel("bookmarks")
        elif action == "tools.attachment":
            self.sidebar.show_panel("attachments")
        elif action == "tools.properties":
            self._show_properties()
        elif action in ("tools.compress", "convert.compress", "tools.optimize"):
            self._compress_dialog()
        elif action == "tools.ocr":
            self._ocr_dialog()
        elif action == "tools.compare":
            self._compare_dialog()
        elif action == "tools.measure":
            self.set_tool("measure", action)
        elif action == "tools.area":
            self.set_tool("area", action)
        elif action == "tools.screenshot":
            self.set_tool("screenshot", action)
        elif action == "tools.export_images":
            self._export_images()
        elif action == "tools.extract_images":
            self._extract_images()
        elif action == "tools.export_text":
            self._export_text()
        elif action == "tools.print":
            self.print_document()
        elif action == "tools.batch":
            self._batch_convert()
        elif action == "tools.repair":
            self._repair_document()
        elif action == "tools.metadata_clean":
            self._clear_metadata()
        # Fill & sign
        elif action == "form.fill":
            self._fill_forms()
        elif action == "form.manage":
            self._manage_forms()
        elif action == "form.export":
            self._export_form_data()
        elif action == "form.reset":
            self._reset_forms()
        elif action in ("form.text", "form.checkbox", "form.radio", "form.dropdown", "form.signature"):
            kind = action.replace("form.", "")
            self.viewer.set_form_kind(kind)
            self.set_tool(f"form_{kind}", action)
        elif action == "sign.draw":
            self._signature_dialog()
        elif action == "sign.upload":
            self._upload_signature()
        elif action == "sign.date":
            self._pending_text = time.strftime("%Y-%m-%d")
            self.set_tool("text", None)
        elif action == "sign.stamp":
            self._stamp_dialog()
        elif action == "sign.initials":
            self._initials_signature()
        # Protect
        elif action == "protect.encrypt":
            self._encrypt_dialog()
        elif action == "protect.permissions":
            self._permissions_dialog()
        elif action == "protect.decrypt":
            self._decrypt_dialog()
        elif action == "protect.info":
            self._show_properties(security=True)
        elif action == "protect.certificate":
            self._show_signature_info()
        elif action == "protect.redact":
            self.set_tool("redact", action)
        elif action == "protect.find_redact":
            self._find_redact()
        elif action == "protect.metadata":
            self._clear_metadata()
        elif action == "protect.flatten":
            self._flatten_document()
        elif action == "protect.watermark":
            self._add_watermark()
        elif action == "protect.watermark_image":
            self._add_watermark(image=True)
        elif action == "protect.watermark_manage":
            self._add_watermark()
        elif action == "protect.sign":
            self._signature_dialog()
        elif action == "protect.timestamp":
            self._insert_timestamp()
        # Convert
        elif action.startswith("convert."):
            self._handle_convert_action(action)
        # AI
        elif action.startswith("ai."):
            self._handle_ai_action(action)
        elif action == "help.shortcuts":
            ShortcutsDialog(self).exec()
        else:
            self.toast.show_message(f"功能入口已就绪：{action}")

    # --------------------------------------------------------- text & images
    def _edit_span(self, span: TextSpan) -> None:
        if not self.doc_model.is_open:
            return
        dlg = TextEditDialog(self, span)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        try:
            if not values["text"].strip():
                confirm = QMessageBox.question(
                    self, "删除文字", "文字内容为空，是否删除这段文字？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    return
            ops.replace_text(
                self.doc_model,
                span,
                values["text"],
                size=values["size"],
                color=_hex_to_rgb(values["color"]),
                bold=values["bold"],
                align=values["align"],
            )
            self._after_edit("文字已更新")
        except Exception as exc:
            QMessageBox.critical(self, "编辑文字失败", str(exc))

    def _replace_text_block(self, block, text: str) -> None:
        if not self.doc_model.is_open:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusbar.set_message("正在写入文字…")
        QApplication.processEvents()
        try:
            ops.replace_text_block(self.doc_model, block, text)
            self._after_edit(
                "文字已更新（修改前页面快照已保存，可 Ctrl+Z 撤销）",
                rebuild_thumbs=False,
                rebuild_annots=False,
            )
            self.set_tool("select")
        except Exception as exc:
            self._log_ui_error("replace_text_block", exc)
            self.toast.show_message(f"文字修改失败：{exc}", 4200)
        finally:
            QApplication.restoreOverrideCursor()

    def _insert_text_at(self, page_index: int, target: Any) -> None:
        if not self.doc_model.is_open:
            return
        is_rect = isinstance(target, pymupdf.Rect) and target.width > 4 and target.height > 4
        dlg = TextInsertDialog(
            self,
            box=is_rect or self._text_box_mode,
            default_text=self._pending_text or "",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        text = values["text"]
        if not text.strip():
            return
        try:
            if is_rect:
                rect = pymupdf.Rect(target)
            else:
                point = target
                size = values["size"]
                width = max(260.0, len(text) * size * 0.95)
                rect = pymupdf.Rect(point.x, point.y - size * 1.2, point.x + width, point.y + size * 0.25)
            ops.insert_text(
                self.doc_model,
                page_index,
                rect,
                text,
                size=values["size"],
                color=_hex_to_rgb(values["color"]),
                bold=values["bold"],
                align=values["align"],
                box=is_rect or self._text_box_mode,
            )
            self._pending_text = None
            self._text_box_mode = False
            self._after_edit("已插入文字")
            self.set_tool("select")
        except Exception as exc:
            QMessageBox.critical(self, "插入文字失败", str(exc))

    def _paste_text(self, page_index: int) -> None:
        text = QApplication.clipboard().text()
        if not text:
            self.toast.show_message("剪贴板中没有文字")
            return
        dlg = TextInsertDialog(self, box=True, default_text=text)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["text"].strip():
            return
        try:
            width = min(420.0, max(220.0, self.doc_model.page_size(page_index)[0] - 120))
            height = max(80.0, min(300.0, 30 + values["text"].count("\n") * values["size"] * 1.5))
            rect = pymupdf.Rect(72, 100, 72 + width, 100 + height)
            ops.insert_text(
                self.doc_model, page_index, rect, values["text"],
                size=values["size"], color=_hex_to_rgb(values["color"]),
                bold=values["bold"], align=values["align"], box=True,
            )
            self._after_edit("已粘贴文字")
            self.set_tool("select")
        except Exception as exc:
            QMessageBox.critical(self, "粘贴文字失败", str(exc))

    def _insert_image_at(self, page_index: int, rect: Any) -> None:
        if not self.doc_model.is_open:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", self._last_dir, SUPPORTED_IMAGES)
        if not path:
            return
        try:
            from PIL import Image

            with Image.open(path) as image:
                iw, ih = image.size
            width = max(40.0, float(rect.width))
            height = width * ih / max(1, iw)
            if height > 500:
                height = 500
                width = height * iw / max(1, ih)
            target = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + width, rect.y0 + height)
            ops.insert_image(self.doc_model, page_index, target, path)
            self._after_edit("已插入图片")
            self.set_tool("select")
        except Exception as exc:
            QMessageBox.critical(self, "插入图片失败", str(exc))

    # ------------------------------------------------------------ annotations
    def _add_markup(self, kind: str, page_index: int, rects: list[pymupdf.Rect]) -> None:
        if not self.doc_model.is_open or not rects:
            return
        try:
            if kind == "area":
                ops.add_text_markup(
                    self.doc_model, page_index, rects, "highlight",
                    _hex_to_rgb(self._annot_colors["area"]), opacity=0.32,
                )
            else:
                color = self._annot_colors.get(kind, self.viewer.annotation_color)
                ops.add_text_markup(
                    self.doc_model, page_index, rects, kind, _hex_to_rgb(color),
                    opacity=0.42 if kind == "highlight" else 0.9,
                )
            self._after_edit("已添加批注")
        except Exception as exc:
            QMessageBox.critical(self, "添加批注失败", str(exc))

    def _add_shape(self, kind: str, page_index: int, rect: pymupdf.Rect, points: list[Any]) -> None:
        if not self.doc_model.is_open:
            return
        try:
            point_pairs = [(p.x, p.y) for p in points if p is not None]
            ops.add_shape(
                self.doc_model,
                page_index,
                kind,
                rect,
                stroke=_hex_to_rgb(self._shape_color),
                fill=None,
                width=self.viewer.line_width,
                points=point_pairs,
            )
            self._after_edit("已添加形状")
        except Exception as exc:
            QMessageBox.critical(self, "添加形状失败", str(exc))

    def _add_ink(self, page_index: int, points: list[tuple[float, float]]) -> None:
        if not self.doc_model.is_open:
            return
        try:
            ops.add_ink(
                self.doc_model, page_index, [points],
                color=_hex_to_rgb(self.viewer.annotation_color),
                width=max(1.0, self.viewer.line_width),
            )
            self._after_edit("已添加手绘标注")
        except Exception as exc:
            QMessageBox.critical(self, "手绘失败", str(exc))

    def _add_sticky(self, page_index: int, point: pymupdf.Point) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "添加便签", "批注内容：", "")
        if not ok or not text.strip():
            return
        try:
            ops.add_sticky_note(self.doc_model, page_index, point, text)
            self._after_edit("已添加便签")
        except Exception as exc:
            QMessageBox.critical(self, "添加便签失败", str(exc))

    def _add_stamp_at(self, page_index: int, rect: pymupdf.Rect) -> None:
        try:
            ops.add_stamp(
                self.doc_model, page_index, rect,
                self.viewer.stamp_text, color=self._stamp_color_string(),
                subtitle=self.viewer.stamp_subtitle,
            )
            self._after_edit("已放置图章")
        except Exception as exc:
            QMessageBox.critical(self, "添加图章失败", str(exc))

    def _stamp_color_string(self) -> str:
        return getattr(self, "_stamp_color", "#D93B3B")

    def _add_signature_at(self, page_index: int, rect: pymupdf.Rect) -> None:
        data = self.viewer.signature_bytes or self.store.load_signature()
        if not data:
            dlg = SignatureDialog(self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.png()
            self.viewer.set_signature(data)
            self.store.save_signature(data)
        try:
            ops.sign_page(self.doc_model, page_index, rect, image_bytes=data)
            self._after_edit("签名已放置")
        except Exception as exc:
            QMessageBox.critical(self, "签名失败", str(exc))

    def _add_link_at(self, page_index: int, rect: pymupdf.Rect) -> None:
        dlg = LinkDialog(self, self.doc_model.page_count, page_index)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["uri"] and values["page"] is None:
            self.toast.show_message("请输入网址或选择目标页面")
            return
        try:
            ops.add_link(
                self.doc_model, page_index, rect,
                uri=values["uri"] or None, target_page=values["page"],
            )
            self._after_edit("已添加链接")
        except Exception as exc:
            QMessageBox.critical(self, "添加链接失败", str(exc))

    def _redact_at(self, page_index: int, rect: pymupdf.Rect) -> None:
        confirm = QMessageBox.warning(
            self,
            "密文涂黑",
            "此操作会永久移除框选区域内的文字、图片或图形，且无法通过撤销以外的方式恢复。\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            ops.redact_area(self.doc_model, page_index, rect, fill=(0, 0, 0))
            self._after_edit("内容已永久移除", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "密文处理失败", str(exc))

    def _add_form_at(self, kind: str, page_index: int, rect: pymupdf.Rect) -> None:
        dlg = FormFieldDialog(self, kind)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        try:
            ops.add_form_field(
                self.doc_model, page_index, values["kind"], rect,
                name=values["name"], value=values["value"], options=values["options"],
                font_size=values["size"],
            )
            self._after_edit("已添加表单控件")
            self.sidebar.show_panel("forms")
            self.set_tool("select")
        except Exception as exc:
            QMessageBox.critical(self, "添加表单控件失败", str(exc))

    def _on_object_action(self, action: str, data: dict) -> None:
        if action in ("select_annot", "select_image"):
            self.statusbar.set_message("已选中对象 · 按 Delete 删除，或右键查看更多")
            return
        if action == "edit_annot":
            page = int(data.get("page", 0))
            xref = int(data.get("xref", 0))
            content = str(data.get("content", ""))
            text, ok = QInputDialog.getMultiLineText(self, "编辑批注", "批注内容：", content)
            if not ok:
                return
            try:
                ops.update_annotation(self.doc_model, page, xref, content=text)
                self._after_edit("批注已更新")
            except Exception as exc:
                QMessageBox.critical(self, "更新批注失败", str(exc))
            return
        if action == "delete_annot":
            try:
                ops.delete_annotation(self.doc_model, int(data.get("page", 0)), int(data.get("xref", 0)))
                self.viewer.clear_object_selection()
                self._after_edit("批注已删除")
            except Exception as exc:
                QMessageBox.critical(self, "删除批注失败", str(exc))
            return
        if action == "replace_image":
            page = int(data.get("page", 0))
            xref = int(data.get("xref", 0))
            path, _ = QFileDialog.getOpenFileName(self, "替换图片", self._last_dir, SUPPORTED_IMAGES)
            if not path:
                return
            try:
                ops.replace_image(self.doc_model, page, xref, path)
                self.viewer.clear_object_selection()
                self._after_edit("图片已替换", rebuild_thumbs=True)
            except Exception as exc:
                QMessageBox.critical(self, "替换图片失败", str(exc))
            return
        if action == "delete_image":
            page = int(data.get("page", 0))
            xref = int(data.get("xref", 0))
            try:
                ops.delete_image(self.doc_model, page, xref)
                self.viewer.clear_object_selection()
                self._after_edit("图片已删除", rebuild_thumbs=True)
            except Exception as exc:
                QMessageBox.critical(self, "删除图片失败", str(exc))
            return
        if action == "delete_selection":
            self._delete_selected_object()

    def _delete_selected_object(self) -> None:
        selected = self.viewer.selected_object()
        if not selected:
            self.toast.show_message("请先选中一个批注或图片")
            return
        if selected["kind"] == "annot":
            try:
                ops.delete_annotation(self.doc_model, selected["page"], selected["xref"])
                self.viewer.clear_object_selection()
                self._after_edit("批注已删除")
            except Exception as exc:
                QMessageBox.critical(self, "删除失败", str(exc))
        elif selected["kind"] == "image":
            try:
                ops.delete_image(self.doc_model, selected["page"], selected["xref"])
                self.viewer.clear_object_selection()
                self._after_edit("图片已删除", rebuild_thumbs=True)
            except Exception as exc:
                QMessageBox.critical(self, "删除失败", str(exc))
        else:
            self.toast.show_message("文字对象请双击后编辑")

    def _object_properties(self) -> None:
        selected = self.viewer.selected_object()
        if not selected:
            self.toast.show_message("请先选中一个对象")
            return
        if selected["kind"] == "text":
            span = selected["span"]
            text = (
                f"类型：文字\n页面：第 {span.page + 1} 页\n字号：{span.size:.1f} pt\n"
                f"字体：{span.font}\n颜色：rgb{tuple(round(c * 255) for c in span.color)}\n"
                f"位置：({span.bbox.x0:.1f}, {span.bbox.y0:.1f}) - ({span.bbox.x1:.1f}, {span.bbox.y1:.1f})"
            )
        else:
            rect = selected.get("rect")
            text = (
                f"类型：{'批注' if selected['kind'] == 'annot' else '图片'}\n"
                f"页面：第 {selected['page'] + 1} 页\n对象编号：{selected.get('xref', '—')}\n"
                f"位置：({rect.x0:.1f}, {rect.y0:.1f}) - ({rect.x1:.1f}, {rect.y1:.1f})"
            )
        TextResultDialog(self, "对象属性", text, 480).exec()

    def _flatten_document(self) -> None:
        confirm = QMessageBox.question(
            self, "拼合内容",
            "拼合会将批注和标注栅格化到页面中，之后不能再单独编辑。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            ops.flatten_annotations(self.doc_model)
            QApplication.restoreOverrideCursor()
            self._after_edit("批注已拼合到页面", rebuild_thumbs=True)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "拼合失败", str(exc))

    # ------------------------------------------------------------ decorations
    def _add_watermark(self, image: bool = False) -> None:
        dlg = WatermarkDialog(self, self.doc_model.page_count, self.viewer.current_page, image=image)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        try:
            if image:
                if not values["path"] or not os.path.exists(values["path"]):
                    self.toast.show_message("请选择有效的水印图片")
                    return
                ops.add_watermark_image(
                    self.doc_model, values["path"], opacity=values["opacity"], pages=values["pages"]
                )
            else:
                if not values["text"].strip():
                    self.toast.show_message("请输入水印文字")
                    return
                ops.add_watermark_text(
                    self.doc_model, values["text"], size=values["size"],
                    color=_hex_to_rgb(values["color"]), opacity=values["opacity"],
                    angle=values["angle"], tiled=values["tiled"], pages=values["pages"],
                )
            self._after_edit("水印已添加", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "添加水印失败", str(exc))

    def _background_dialog(self) -> None:
        dlg = BackgroundDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        if values["image"] and not os.path.exists(values["image"]):
            self.toast.show_message("背景图片不存在")
            return
        try:
            ops.add_background(
                self.doc_model, color=values["color"], image_path=values["image"],
                opacity=values["opacity"], pages=values["pages"],
            )
            self._after_edit("页面背景已更新", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "设置背景失败", str(exc))

    def _header_footer_dialog(self, *, footer: bool) -> None:
        dlg = HeaderFooterDialog(self, self.doc_model.page_count, self.viewer.current_page, footer=footer)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        try:
            ops.add_header_footer(
                self.doc_model, values["text"], position=values["position"],
                size=values["size"], color=_hex_to_rgb(values["color"]),
                margin=values["margin"], pages=values["pages"],
            )
            self._after_edit("页脚已添加" if footer else "页眉已添加", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "添加失败", str(exc))

    def _page_number_dialog(self) -> None:
        dlg = PageNumberDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        try:
            ops.add_page_numbers(
                self.doc_model, position=values["position"], fmt=values["fmt"],
                size=values["size"], color=_hex_to_rgb(values["color"]),
                start=values["start"], pages=values["pages"],
            )
            self._after_edit("页码已添加", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "添加页码失败", str(exc))

    # --------------------------------------------------------------- metadata
    def _metadata_dialog(self) -> None:
        dlg = MetadataDialog(self, self.doc_model.metadata())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.doc_model.checkpoint()
            self.doc_model.set_metadata(dlg.values())
            self._after_edit("文档属性已更新")
        except Exception as exc:
            QMessageBox.critical(self, "更新属性失败", str(exc))

    def _clear_metadata(self) -> None:
        if QMessageBox.question(
            self, "清除元数据",
            "将清除作者、标题、关键词、创建程序等元数据，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.doc_model.checkpoint()
            self.doc_model.set_metadata({k: "" for k in (
                "title", "author", "subject", "keywords", "creator", "producer",
            )})
            self._after_edit("元数据已清除")
        except Exception as exc:
            QMessageBox.critical(self, "清除元数据失败", str(exc))

    def _show_properties(self, security: bool = False) -> None:
        if not self.doc_model.is_open:
            return
        meta = self.doc_model.metadata()
        meta["_path"] = self.doc_model.path or ""
        size = os.path.getsize(self.doc_model.path) if self.doc_model.path and os.path.exists(self.doc_model.path) else 0
        dlg = PropertiesDialog(
            self, meta,
            page_count=self.doc_model.page_count,
            file_size=_format_size(size),
            fonts=self.doc_model.font_list(),
            encrypted=self.doc_model.is_encrypted,
            permissions=self.doc_model.permissions,
        )
        if security:
            tabs = dlg.findChild(QTabWidget)
            if tabs is not None:
                tabs.setCurrentIndex(2)
        dlg.exec()

    def _font_info(self) -> None:
        fonts = self.doc_model.font_list()
        text = "文档中检测到的字体\n\n" + ("\n".join(f"• {f}" for f in fonts) if fonts else "未检测到嵌入字体。")
        TextResultDialog(self, "字体信息", text, 540).exec()

    def _show_signature_info(self) -> None:
        text = (
            "签名与认证\n\n"
            "• 本软件支持手写签名、输入签名和图片签名，签名会以透明图层写入 PDF。\n"
            "• 签名属于视觉签名，不包含证书链或可信时间戳。\n"
            "• 如需具有法律效力的数字证书签名，请使用具备 CA 证书的专用签章系统。\n\n"
            "当前文档中的表单签名域可在“填写与签署”中查看。"
        )
        TextResultDialog(self, "签名信息", text, 560).exec()

    # ---------------------------------------------------------------- pages
    def _target_pages(self) -> list[int]:
        pages = self.sidebar.selected_pages()
        if not pages:
            pages = [self.viewer.current_page]
        return pages

    def _insert_blank_pages(self) -> None:
        if not self.doc_model.is_open:
            return
        current_size = self.doc_model.page_size(self.viewer.current_page)
        dlg = BlankPageDialog(
            self, self.doc_model.page_count, self.viewer.current_page, current_size
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        try:
            for offset in range(values["count"]):
                ops.insert_blank_page(
                    self.doc_model,
                    values["position"] + offset,
                    values["width"],
                    values["height"],
                )
            self._after_edit("已插入空白页", rebuild=True)
            self.viewer.goto_page(values["position"])
        except Exception as exc:
            QMessageBox.critical(self, "插入页面失败", str(exc))

    def _insert_pdf_dialog(self) -> None:
        dlg = InsertPagesDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        source = dlg.path.text().strip()
        if not source or not os.path.exists(source):
            return
        try:
            src = pymupdf.open(source)
            password = None
            if src.needs_pass:
                src.close()
                pwd_dlg = PasswordDialog(self, "源 PDF 受保护", "请输入要插入的 PDF 的打开密码。")
                if pwd_dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                password = pwd_dlg.value()
                src = pymupdf.open(source)
                if not src.authenticate(password):
                    src.close()
                    QMessageBox.warning(self, "密码错误", "无法打开源 PDF。")
                    return
            count = len(src)
            src.close()
            selected = parse_page_ranges(dlg.ranges.text(), count) if dlg.ranges.text().strip() else list(range(count))
            if not selected:
                self.toast.show_message("没有可插入的页面")
                return
            ops.insert_pdf_pages(
                self.doc_model, source, dlg.position.value() - 1, selected, password=password
            )
            self._after_edit("已插入 PDF 页面", rebuild=True)
            self.viewer.goto_page(dlg.position.value() - 1)
        except Exception as exc:
            QMessageBox.critical(self, "插入 PDF 失败", str(exc))

    def _delete_pages(self) -> None:
        pages = self._target_pages()
        if len(pages) >= self.doc_model.page_count:
            QMessageBox.information(self, "删除页面", "文档至少需要保留一页。")
            return
        if QMessageBox.question(
            self, "删除页面", f"确定删除选中的 {len(pages)} 页吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            ops.delete_pages(self.doc_model, pages)
            self._after_edit("页面已删除", rebuild=True)
            self.viewer.goto_page(min(pages[0], self.doc_model.page_count - 1))
        except Exception as exc:
            QMessageBox.critical(self, "删除页面失败", str(exc))

    def _duplicate_page(self) -> None:
        try:
            index = ops.duplicate_page(self.doc_model, self.viewer.current_page)
            self._after_edit("已复制页面", rebuild=True)
            self.viewer.goto_page(index)
        except Exception as exc:
            QMessageBox.critical(self, "复制页面失败", str(exc))

    def _move_page_dialog(self) -> None:
        dlg = MovePageDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        source, target = dlg.values()
        try:
            ops.move_page(self.doc_model, source, target)
            self._after_edit("页面顺序已调整", rebuild=True)
            self.viewer.goto_page(target)
        except Exception as exc:
            QMessageBox.critical(self, "移动页面失败", str(exc))

    def _rotate_selected(self, angle: int) -> None:
        try:
            ops.rotate_pages(self.doc_model, self._target_pages(), angle)
            self._after_edit("页面已旋转", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "旋转页面失败", str(exc))

    def _crop_dialog(self) -> None:
        dlg = CropDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        try:
            ops.crop_pages(self.doc_model, values["pages"], values["margins"])
            self._after_edit("页面已裁剪", rebuild=True)
        except Exception as exc:
            QMessageBox.critical(self, "裁剪失败", str(exc))

    def _page_size_dialog(self) -> None:
        dlg = PageSizeDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        try:
            ops.resize_pages(
                self.doc_model, values["width"], values["height"], values["pages"],
                keep_ratio=values["keep_ratio"],
            )
            self._after_edit("页面大小已调整", rebuild=True)
        except Exception as exc:
            QMessageBox.critical(self, "调整页面大小失败", str(exc))

    def _extract_pages(self) -> None:
        pages = self._target_pages()
        default = ",".join(str(p + 1) for p in pages)
        text, ok = QInputDialog.getText(
            self, "提取页面", "输入要提取的页码（例如 1-3, 5）：", text=default
        )
        if not ok or not text.strip():
            return
        selected = parse_page_ranges(text, self.doc_model.page_count)
        if not selected:
            self.toast.show_message("页码范围无效")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存提取的页面",
            os.path.join(self._last_dir, "提取页面.pdf"),
            "PDF 文件 (*.pdf)",
        )
        if not target:
            return
        try:
            ops.extract_pages(self.doc_model, selected, target)
            self.toast.show_message(f"已提取 {len(selected)} 页到 {os.path.basename(target)}")
        except Exception as exc:
            QMessageBox.critical(self, "提取页面失败", str(exc))

    def _split_document(self) -> None:
        dlg = SplitDialog(self, self.doc_model.page_count, self._last_dir)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        output_dir = values["output_dir"]
        if not output_dir:
            self.toast.show_message("请选择输出文件夹")
            return
        copy = self._doc_copy()
        total = self.doc_model.page_count

        def task(progress, cancelled):
            try:
                outputs = ops.split_document(
                    copy, output_dir, every=values["every"],
                    ranges=values["ranges"] or None,
                )
                return outputs
            finally:
                copy.close()

        def done(outputs):
            self.toast.show_message(f"已拆分为 {len(outputs)} 个文件")
            if outputs and QMessageBox.question(
                self, "拆分完成", f"已生成 {len(outputs)} 个文件，是否打开输出文件夹？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(Path(output_dir).as_uri())

        self._run_task("拆分文档", task, done, f"共 {total} 页")

    def _replace_page_dialog(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "选择替换页面来源", self._last_dir, "PDF 文件 (*.pdf)")
        if not source:
            return
        try:
            src = pymupdf.open(source)
            count = len(src)
            src.close()
        except Exception as exc:
            QMessageBox.critical(self, "打开源 PDF 失败", str(exc))
            return
        page, ok = QInputDialog.getInt(
            self, "替换页面", f"使用源 PDF 的第几页替换当前页？（1-{count}）", 1, 1, count
        )
        if not ok:
            return
        try:
            ops.replace_page_with_pdf(self.doc_model, self.viewer.current_page, source, page - 1)
            self._after_edit("页面已替换", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "替换页面失败", str(exc))

    def merge_documents_dialog(self) -> None:
        initial = [self.doc_model.path] if self.doc_model.is_open and self.doc_model.path else []
        dlg = MergeDialog(self, initial)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paths = dlg.paths()
        if len(paths) < 2:
            self.toast.show_message("请至少添加两个 PDF 文件")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存合并文档", os.path.join(self._last_dir, "合并文档.pdf"), "PDF 文件 (*.pdf)"
        )
        if not target:
            return

        def task(progress, cancelled):
            return ops.merge_documents(paths, target)

        def done(result):
            self.toast.show_message(f"已合并 {len(paths)} 个文件")
            if QMessageBox.question(
                self, "合并完成", "合并完成，是否打开合并后的文档？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(result)

        self._run_task("合并文档", task, done, f"正在合并 {len(paths)} 个文件")

    # -------------------------------------------------------- bookmarks/notes
    def _add_bookmark(self) -> None:
        if not self.doc_model.is_open:
            return
        dlg = BookmarkDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        try:
            ops.add_bookmark(self.doc_model, values["title"], values["page"])
            self.sidebar.refresh_bookmarks()
            self._update_document_ui()
            self.toast.show_message("书签已添加")
        except Exception as exc:
            QMessageBox.critical(self, "添加书签失败", str(exc))

    def _delete_bookmark(self) -> None:
        item = self.sidebar.bookmark_tree.currentItem()
        if item is None:
            self.toast.show_message("请先选择要删除的书签")
            return
        title = item.text(0)
        page = int(item.data(0, Qt.ItemDataRole.UserRole) or 0)
        toc = self.doc_model.outline()
        match = next((i for i, row in enumerate(toc) if str(row[1]) == title and int(row[2]) - 1 == page), None)
        if match is None:
            return
        try:
            ops.delete_bookmark(self.doc_model, match)
            self.sidebar.refresh_bookmarks()
            self._update_document_ui()
            self.toast.show_message("书签已删除")
        except Exception as exc:
            QMessageBox.critical(self, "删除书签失败", str(exc))

    def _goto_annotation(self, page: int, xref: int) -> None:
        self.viewer.goto_page(page)
        self.viewer.select_annotation(page, xref)

    def _delete_selected_annotation(self) -> None:
        selected = self.viewer.selected_object()
        if selected.get("kind") == "annot":
            try:
                ops.delete_annotation(self.doc_model, selected["page"], selected["xref"])
                self.viewer.clear_object_selection()
                self._after_edit("批注已删除")
                return
            except Exception as exc:
                QMessageBox.critical(self, "删除批注失败", str(exc))
                return
        item = self.sidebar.annot_list.currentItem()
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                try:
                    ops.delete_annotation(self.doc_model, int(data[0]), int(data[1]))
                    self._after_edit("批注已删除")
                    return
                except Exception as exc:
                    QMessageBox.critical(self, "删除批注失败", str(exc))
                    return
        self.toast.show_message("请先选择要删除的批注")

    def _export_annotations(self) -> None:
        annotations = self.doc_model.all_annotations()
        if not annotations:
            self.toast.show_message("当前文档没有批注")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "导出批注", os.path.join(self._last_dir, "批注汇总.csv"), "CSV 文件 (*.csv)"
        )
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["页码", "类型", "作者", "内容", "颜色", "修改时间"])
                for annot in annotations:
                    writer.writerow([
                        annot.page + 1, annot.type, annot.author, annot.content,
                        annot.color or "", annot.modified,
                    ])
            self.toast.show_message(f"已导出 {len(annotations)} 条批注")
        except Exception as exc:
            QMessageBox.critical(self, "导出批注失败", str(exc))

    def _add_attachment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "添加附件", self._last_dir, "所有文件 (*.*)")
        if not path:
            return
        try:
            ops.add_attachment(self.doc_model, path)
            self.sidebar.refresh_attachments()
            self._update_document_ui()
            self.toast.show_message("附件已添加")
        except Exception as exc:
            QMessageBox.critical(self, "添加附件失败", str(exc))

    def _save_attachment(self, name: str) -> None:
        if not name:
            self.toast.show_message("请选择附件")
            return
        target, _ = QFileDialog.getSaveFileName(self, "保存附件", os.path.join(self._last_dir, name))
        if not target:
            return
        try:
            ops.extract_attachment(self.doc_model, name, target)
            self.toast.show_message("附件已保存")
        except Exception as exc:
            QMessageBox.critical(self, "保存附件失败", str(exc))

    def _delete_attachment(self, name: str) -> None:
        if not name:
            return
        if QMessageBox.question(
            self, "删除附件", f"确定从 PDF 中删除附件“{name}”吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            ops.delete_attachment(self.doc_model, name)
            self.sidebar.refresh_attachments()
            self._update_document_ui()
            self.toast.show_message("附件已删除")
        except Exception as exc:
            QMessageBox.critical(self, "删除附件失败", str(exc))

    # ----------------------------------------------------------------- search
    def _show_search(self) -> None:
        self.sidebar.show_panel("search")
        if self.viewer.selected_text:
            self.sidebar.search_edit.setText(self.viewer.selected_text[:60])
        self.sidebar.search_edit.setFocus()
        self.sidebar.search_edit.selectAll()

    def _perform_search(self, query: str) -> None:
        query = query.strip()
        if not query or not self.doc_model.is_open:
            return
        try:
            hits = self.doc_model.search(query, 800)
        except Exception as exc:
            QMessageBox.critical(self, "搜索失败", str(exc))
            return
        self._search_hits = hits
        self.viewer.set_search_hits([(h.page, h.rect) for h in hits], 0 if hits else -1)
        page_texts: dict[int, str] = {}
        for hit in hits:
            if hit.page not in page_texts:
                page_texts[hit.page] = self.doc_model.text(hit.page)
        snippets = [self._search_snippet(h, query, page_texts.get(h.page, "")) for h in hits]
        self.sidebar.set_search_results(hits, snippets)
        self.sidebar.show_panel("search")
        if hits:
            self.viewer.focus_hit(0)
            self.statusbar.set_message(f"找到 {len(hits)} 处结果")
        else:
            self.statusbar.set_message("未找到匹配内容")
            self.toast.show_message("未找到匹配内容")

    @staticmethod
    def _search_snippet(hit, query: str, text: str = "") -> str:
        if not text:
            return f"第 {hit.page + 1} 页"
        lowered = text.lower()
        pos = lowered.find(query.lower())
        if pos < 0:
            return text[:50]
        start = max(0, pos - 24)
        end = min(len(text), pos + len(query) + 36)
        snippet = text[start:end].replace("\n", " ")
        return ("…" if start else "") + snippet + ("…" if end < len(text) else "")

    def _select_search_hit(self, index: int) -> None:
        if 0 <= index < len(self._search_hits):
            self.viewer.focus_hit(index)
            self.statusbar.set_message(f"第 {self._search_hits[index].page + 1} 页 · 结果 {index + 1}/{len(self._search_hits)}")

    # -------------------------------------------------------------- replace
    def _replace_dialog(self, all_pages: bool = False) -> None:
        dlg = ReplaceDialog(self, self.doc_model.page_count, self.viewer.current_page)
        if all_pages:
            dlg.scope.setCurrentIndex(1)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["find"]:
            self.toast.show_message("请输入要查找的文字")
            return
        try:
            count = ops.replace_all_text(
                self.doc_model, values["find"], values["replace"],
                pages=values["pages"], color=_hex_to_rgb(values["color"]),
            )
            if count:
                self._after_edit(f"已替换 {count} 处", rebuild_thumbs=True)
            else:
                self.toast.show_message("未找到匹配文字")
        except Exception as exc:
            QMessageBox.critical(self, "替换失败", str(exc))

    # ----------------------------------------------------------------- print
    def print_document(self) -> None:
        if not self.doc_model.is_open:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(self.doc_model.file_name)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("打印 PDF")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            painter = QPainter(printer)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            resolution = min(300, max(96, printer.resolution()))
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            first = printer.fromPage() - 1 if printer.fromPage() > 0 else 0
            last = printer.toPage() - 1 if printer.toPage() > 0 else self.doc_model.page_count - 1
            first = max(0, min(first, self.doc_model.page_count - 1))
            last = max(first, min(last, self.doc_model.page_count - 1))
            for idx, pno in enumerate(range(first, last + 1)):
                if idx:
                    printer.newPage()
                pix = self.doc_model.render(pno, resolution / 72.0, annots=True)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                target = QRectF(page_rect)
                iw, ih = image.width(), image.height()
                scale = min(target.width() / iw, target.height() / ih)
                w, h = iw * scale, ih * scale
                target = QRectF(
                    page_rect.x() + (page_rect.width() - w) / 2,
                    page_rect.y() + (page_rect.height() - h) / 2,
                    w, h,
                )
                painter.drawImage(target, image)
            painter.end()
            self.toast.show_message("打印任务已发送")
        except Exception as exc:
            try:
                painter.end()
            except Exception:
                pass
            QMessageBox.critical(self, "打印失败", str(exc))

    # --------------------------------------------------------------- security
    def _encrypt_dialog(self) -> None:
        dlg = EncryptDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        default = self.doc_model.path or os.path.join(self._last_dir, "文档")
        base = default[:-4] if default.lower().endswith(".pdf") else default
        target, _ = QFileDialog.getSaveFileName(
            self, "加密保存为", base + "_加密.pdf", "PDF 文件 (*.pdf)"
        )
        if not target:
            return
        if os.path.abspath(target) == os.path.abspath(self.doc_model.path or ""):
            QMessageBox.warning(self, "加密文档", "请选择不同的文件名，避免覆盖正在编辑的文档。")
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            permissions = self._permission_value(values["permissions"])
            ops.encrypt_to(
                self.doc_model, target, values["user"], values["owner"],
                permissions, algorithm=values["algorithm"],
            )
            QApplication.restoreOverrideCursor()
            self.toast.show_message("加密文档已保存")
            if QMessageBox.question(
                self, "加密完成", "文档已加密保存，是否立即打开加密文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(target)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "加密失败", str(exc))

    def _permissions_dialog(self) -> None:
        dlg = PermissionDialog(self, self.doc_model.permissions)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["owner"]:
            self.toast.show_message("请输入权限密码")
            return
        if not self.doc_model.path:
            if not self.save_document_as():
                return
        default = self.doc_model.path[:-4] + "_权限.pdf" if self.doc_model.path else "权限设置.pdf"
        target, _ = QFileDialog.getSaveFileName(self, "保存权限设置", default, "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            permissions = self._permission_value(values["permissions"])
            ops.update_permissions_copy(
                self.doc_model.path, target, values["owner"], permissions
            )
            QApplication.restoreOverrideCursor()
            self.toast.show_message("权限设置已保存")
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "权限设置失败", str(exc))

    def _decrypt_dialog(self) -> None:
        if not self.doc_model.is_encrypted:
            self.toast.show_message("当前文档未加密")
            return
        dlg = PasswordDialog(
            self, "解除密码保护", "请输入权限密码（所有者密码）。如果没有权限密码，将无法解除限制。"
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        default = (self.doc_model.path or "文档.pdf")
        default = default[:-4] + "_已解密.pdf" if default.lower().endswith(".pdf") else default + "_已解密.pdf"
        target, _ = QFileDialog.getSaveFileName(self, "解除密码保存为", default, "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            ops.decrypt_copy(self.doc_model.path, target, dlg.value())
            QApplication.restoreOverrideCursor()
            self.toast.show_message("已生成无密码副本")
            if QMessageBox.question(
                self, "解除完成", "已生成无密码副本，是否打开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(target)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "解除密码失败", str(exc))

    def _find_redact(self) -> None:
        text, ok = QInputDialog.getText(self, "搜索密文", "要永久移除的文字：")
        if not ok or not text:
            return
        hits = self.doc_model.search(text, 5000)
        if not hits:
            self.toast.show_message("未找到匹配文字")
            return
        if QMessageBox.warning(
            self, "搜索密文",
            f"找到 {len(hits)} 处匹配。将永久移除这些文字并涂黑，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            count = ops.redact_search(self.doc_model, text, fill=(0, 0, 0))
            self._after_edit(f"已密文处理 {count} 处内容", rebuild_thumbs=True)
        except Exception as exc:
            QMessageBox.critical(self, "密文处理失败", str(exc))

    @staticmethod
    def _permission_value(values: dict[str, bool]) -> int:
        return ops.permissions_value(
            print_=bool(values.get("print", True)),
            print_hq=bool(values.get("print_hq", True)),
            modify=bool(values.get("modify", True)),
            copy=bool(values.get("copy", True)),
            annotate=bool(values.get("annotate", True)),
            forms=bool(values.get("forms", True)),
            extract=bool(values.get("extract", True)),
            assemble=bool(values.get("assemble", True)),
            accessibility=bool(values.get("accessibility", True)),
        )

    def _insert_timestamp(self) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self._pending_text = stamp
        self.set_tool("text", None)

    # ------------------------------------------------------------------ forms
    def _fill_forms(self) -> None:
        widgets = self.doc_model.widgets()
        if not widgets:
            self.toast.show_message("当前文档没有可填写的表单字段")
            return
        dlg = FormFillDialog(self, widgets)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        signature_fields = [w for w in widgets if values.get(w.xref) == "__SIGN__"]
        plain_values = {k: ("" if v == "__SIGN__" else v) for k, v in values.items()}
        try:
            if plain_values:
                ops.fill_form_values(self.doc_model, plain_values)
            if signature_fields:
                data = self.store.load_signature()
                if not data:
                    sig = SignatureDialog(self)
                    if sig.exec() == QDialog.DialogCode.Accepted:
                        data = sig.png()
                        self.store.save_signature(data)
                if data:
                    for widget in signature_fields:
                        ops.sign_page(self.doc_model, widget.page, widget.rect, image_bytes=data)
            self._after_edit("表单已保存")
        except Exception as exc:
            QMessageBox.critical(self, "填写表单失败", str(exc))

    def _manage_forms(self) -> None:
        widgets = self.doc_model.widgets()
        if not widgets:
            TextResultDialog(self, "表单信息", "当前文档没有表单字段。", 480).exec()
            return
        lines = ["字段名称    类型    页码    当前值"]
        for widget in widgets:
            lines.append(f"{widget.name}    {widget.field_type}    第 {widget.page + 1} 页    {widget.value}")
        TextResultDialog(self, "表单字段", "\n".join(lines), 620).exec()

    def _export_form_data(self) -> None:
        widgets = self.doc_model.widgets()
        if not widgets:
            self.toast.show_message("当前文档没有表单字段")
            return
        target, selected_filter = QFileDialog.getSaveFileName(
            self, "导出表单数据", os.path.join(self._last_dir, "表单数据.csv"),
            "CSV 文件 (*.csv);;JSON 文件 (*.json)",
        )
        if not target:
            return
        try:
            if target.lower().endswith(".json"):
                data = [
                    {"name": w.name, "type": w.field_type, "page": w.page + 1, "value": w.value}
                    for w in widgets
                ]
                with open(target, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
            else:
                with open(target, "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["字段名称", "类型", "页码", "当前值"])
                    for w in widgets:
                        writer.writerow([w.name, w.field_type, w.page + 1, w.value])
            self.toast.show_message("表单数据已导出")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _reset_forms(self) -> None:
        widgets = self.doc_model.widgets()
        if not widgets:
            self.toast.show_message("当前文档没有表单字段")
            return
        if QMessageBox.question(
            self, "重置表单", "确定清空所有表单字段吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        values = {}
        for w in widgets:
            values[w.xref] = False if w.field_type in ("CheckBox", "RadioButton") else ""
        try:
            ops.fill_form_values(self.doc_model, values)
            self._after_edit("表单已重置")
        except Exception as exc:
            QMessageBox.critical(self, "重置表单失败", str(exc))

    # -------------------------------------------------------------- signatures
    def _signature_dialog(self) -> None:
        saved = self.store.load_signature()
        dlg = SignatureDialog(self, saved)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.png()
        if not data:
            return
        self.store.save_signature(data)
        self.viewer.set_signature(data)
        self.set_tool("signature", None)
        self.toast.show_message("请在页面上点击放置签名")

    def _upload_signature(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择签名图片", self._last_dir, SUPPORTED_IMAGES)
        if not path:
            return
        try:
            image = Image.open(path).convert("RGBA")
            pixels = []
            for r, g, b, a in image.getdata():
                if r > 242 and g > 242 and b > 242:
                    pixels.append((255, 255, 255, 0))
                else:
                    pixels.append((r, g, b, a))
            image.putdata(pixels)
            bbox = image.getbbox()
            if bbox:
                image = image.crop(bbox)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            data = buffer.getvalue()
            self.store.save_signature(data)
            self.viewer.set_signature(data)
            self.set_tool("signature", None)
            self.toast.show_message("签名已载入，请在页面上点击放置")
        except Exception as exc:
            QMessageBox.critical(self, "载入签名失败", str(exc))

    def _stamp_dialog(self) -> None:
        dlg = StampDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        self.viewer.set_stamp(values["text"], values["subtitle"])
        self._stamp_color = values["color"]
        self.set_tool("stamp", None)
        self.toast.show_message("请在页面上点击放置图章")

    def _initials_signature(self) -> None:
        text, ok = QInputDialog.getText(self, "姓名缩写", "输入要作为签名的姓名或缩写：")
        if not ok or not text.strip():
            return
        try:
            from PySide6.QtGui import QImage, QPainter, QColor, QFont

            image = QImage(640, 220, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor("#16233F"))
            painter.setFont(QFont("KaiTi", 80))
            painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, text.strip())
            painter.end()
            data = qimage_png(image)
            self.store.save_signature(data)
            self.viewer.set_signature(data)
            self.set_tool("signature", None)
            self.toast.show_message("签名已载入，请在页面上点击放置")
        except Exception as exc:
            QMessageBox.critical(self, "生成签名失败", str(exc))

    # -------------------------------------------------------------------- OCR
    def _ocr_dialog(self) -> None:
        dlg = OcrDialog(
            self, self.doc_model.page_count, self.viewer.current_page,
            int(self.store.settings.get("ocr_dpi", 200)),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        output_mode = values["output"]
        target = None
        if output_mode == 0:
            target, _ = QFileDialog.getSaveFileName(
                self, "保存可搜索 PDF",
                os.path.join(self._last_dir, (Path(self.doc_model.file_name).stem or "文档") + "_OCR.pdf"),
                "PDF 文件 (*.pdf)",
            )
            if not target:
                return
        elif output_mode == 1:
            target, _ = QFileDialog.getSaveFileName(
                self, "保存识别文本", os.path.join(self._last_dir, "OCR文本.txt"), "文本文件 (*.txt)"
            )
            if not target:
                return
        copy = self._doc_copy()
        pages = values["pages"]
        dpi = values["dpi"]

        def task(progress, cancelled):
            try:
                engine = ocr_core.OcrEngine.instance()
                progress(2, "正在加载本地 OCR 模型…")
                lines = engine.ocr_document(copy, pages=pages, dpi=dpi, progress=progress)
                if output_mode == 0:
                    engine.make_searchable_copy(copy, lines, target)
                    return ("file", target, len(lines))
                if output_mode == 1:
                    engine.export_text(lines, target)
                    return ("file", target, len(lines))
                return ("layer", lines, len(lines))
            finally:
                copy.close()

        def done(result):
            kind, payload, count = result
            if kind == "file":
                self.toast.show_message(f"OCR 完成，识别 {count} 行文字")
                if QMessageBox.question(
                    self, "OCR 完成", "识别结果已保存，是否打开文件？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes:
                    if str(payload).lower().endswith(".pdf"):
                        self.open_path(payload)
                    else:
                        QDesktopServices.openUrl(Path(payload).as_uri())
            else:
                try:
                    ocr_core.OcrEngine.add_text_layer(self.doc_model, payload)
                    self._after_edit(f"已添加隐藏文字层，识别 {count} 行", rebuild_thumbs=True)
                except Exception as exc:
                    QMessageBox.critical(self, "写入文字层失败", str(exc))

        self._run_task("OCR 文字识别", task, done, "首次识别需要加载本地模型")

    # --------------------------------------------------------------- optimize
    def _compress_dialog(self) -> None:
        default = self.doc_model.path or os.path.join(self._last_dir, "文档.pdf")
        base = default[:-4] if default.lower().endswith(".pdf") else default
        target, _ = QFileDialog.getSaveFileName(
            self, "压缩 PDF", base + "_压缩.pdf", "PDF 文件 (*.pdf)"
        )
        if not target:
            return
        original_size = 0
        if self.doc_model.path and os.path.exists(self.doc_model.path):
            original_size = os.path.getsize(self.doc_model.path)
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                progress(15, "正在重采样图片…")
                return ops.compress_document(copy, target, dpi=140, quality=64)
            finally:
                copy.close()

        def done(path):
            new_size = os.path.getsize(path) if os.path.exists(path) else 0
            if original_size and new_size:
                saved = max(0, original_size - new_size)
                pct = saved / original_size * 100
                self.toast.show_message(
                    f"压缩完成：{_format_size(original_size)} → {_format_size(new_size)}（减少 {pct:.0f}%）"
                )
            else:
                self.toast.show_message("压缩完成")
            if QMessageBox.question(
                self, "压缩完成", "压缩文件已生成，是否打开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(path)

        self._run_task("压缩文档", task, done, "重采样图片并清理冗余对象")

    def _repair_document(self) -> None:
        if QMessageBox.question(
            self, "修复文档", "将重新整理 PDF 结构并清理损坏对象，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            if not self.doc_model.path:
                if not self.save_document_as():
                    return
            self._save_to(self.doc_model.path)
            self.toast.show_message("文档结构已重新整理")
        except Exception as exc:
            QMessageBox.critical(self, "修复失败", str(exc))

    # ---------------------------------------------------------------- extract
    def _export_images(self) -> None:
        dlg = ConvertOptionsDialog(self, "image", self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        folder = QFileDialog.getExistingDirectory(self, "选择图片输出文件夹", self._last_dir)
        if not folder:
            return
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                return convert_core.pdf_to_images(
                    copy, folder, fmt=values["fmt"], dpi=values["dpi"],
                    pages=values["pages"], progress=progress,
                )
            finally:
                copy.close()

        def done(paths):
            self.toast.show_message(f"已导出 {len(paths)} 张图片")
            if QMessageBox.question(
                self, "导出完成", "图片已导出，是否打开输出文件夹？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(Path(folder).as_uri())

        self._run_task("导出图片", task, done, "按页面渲染图片")

    def _export_text(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "导出文本", os.path.join(self._last_dir, "文档文本.txt"), "文本文件 (*.txt)"
        )
        if not target:
            return
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                return convert_core.pdf_to_text(copy, target, progress=progress)
            finally:
                copy.close()

        self._run_task("导出文本", task, lambda _: self.toast.show_message("文本已导出"), "正在提取文字")

    def _extract_images(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图片保存文件夹", self._last_dir)
        if not folder:
            return
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                count = 0
                pages = copy.page_count
                for pno in range(pages):
                    if cancelled():
                        break
                    progress(int(pno / max(1, pages) * 100), f"提取第 {pno + 1} 页图片")
                    page = copy.require_doc()[pno]
                    for image in page.get_images(full=True):
                        xref = int(image[0])
                        try:
                            info = copy.require_doc().extract_image(xref)
                            ext = info.get("ext", "png")
                            name = f"p{pno + 1:03d}_img{xref}.{ext}"
                            with open(os.path.join(folder, name), "wb") as fh:
                                fh.write(info["image"])
                            count += 1
                        except Exception:
                            continue
                return count
            finally:
                copy.close()

        def done(count):
            self.toast.show_message(f"已提取 {count} 张图片")
            QDesktopServices.openUrl(Path(folder).as_uri())

        self._run_task("提取图片", task, done, "从页面资源中提取原始图片")

    # -------------------------------------------------------------- batch
    def _batch_convert(self) -> None:
        dlg = BatchConvertDialog(self, self._last_dir)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paths = dlg.paths()
        values = dlg.values()
        if not paths:
            self.toast.show_message("请添加要转换的 PDF")
            return
        output = values["output"]
        if not output:
            self.toast.show_message("请选择输出文件夹")
            return
        os.makedirs(output, exist_ok=True)
        target_kind = values["target"]
        dpi = values["dpi"]

        def task(progress, cancelled):
            count = 0
            for i, path in enumerate(paths):
                if cancelled():
                    break
                progress(int(i / len(paths) * 100), f"处理 {os.path.basename(path)}")
                facade = self._open_facade(path)
                if facade is None:
                    continue
                try:
                    stem = Path(path).stem
                    if target_kind == 0:
                        convert_core.pdf_to_docx(facade, os.path.join(output, stem + ".docx"))
                    elif target_kind == 1:
                        folder = os.path.join(output, stem + "_图片")
                        convert_core.pdf_to_images(facade, folder, fmt="png", dpi=dpi)
                    elif target_kind == 2:
                        convert_core.pdf_to_text(facade, os.path.join(output, stem + ".txt"))
                    elif target_kind == 3:
                        convert_core.pdf_to_xlsx(facade, os.path.join(output, stem + ".xlsx"))
                    else:
                        ops.compress_document(facade, os.path.join(output, stem + "_压缩.pdf"))
                    count += 1
                except Exception:
                    continue
                finally:
                    facade.close()
            return count

        def done(count):
            self.toast.show_message(f"批量转换完成：{count}/{len(paths)} 个文件")
            QDesktopServices.openUrl(Path(output).as_uri())

        self._run_task("批量转换", task, done, f"共 {len(paths)} 个 PDF")

    # ------------------------------------------------------------- conversion
    def _handle_convert_action(self, action: str) -> None:
        if action in ("convert.word", "convert.excel", "convert.ppt", "convert.image", "convert.text", "convert.html"):
            self._convert_pdf_to(action.split(".", 1)[1])
        elif action == "convert.word_pdf":
            self._office_to_pdf(".docx")
        elif action == "convert.excel_pdf":
            self._office_to_pdf(".xlsx")
        elif action == "convert.ppt_pdf":
            self._office_to_pdf(".pptx")
        elif action == "convert.images_pdf":
            self._images_to_pdf()
        elif action == "convert.batch":
            self._batch_convert()
        elif action == "convert.compress":
            self._compress_dialog()
        elif action == "convert.merge":
            self.merge_documents_dialog()
        elif action == "convert.split":
            self._split_document()
        elif action == "convert.extract_all":
            self._export_all()
        elif action == "convert.options":
            self._conversion_options_info()
        elif action == "convert.preview":
            self._conversion_preview()

    def _convert_pdf_to(self, target_kind: str) -> None:
        dlg = ConvertOptionsDialog(self, target_kind, self.doc_model.page_count, self.viewer.current_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values(self.doc_model.page_count)
        stem = Path(self.doc_model.file_name).stem or "文档"
        folder = None
        target = None
        if target_kind == "image":
            folder = QFileDialog.getExistingDirectory(self, "选择图片输出文件夹", self._last_dir)
            if not folder:
                return
        else:
            suffixes = {
                "word": (".docx", "Word 文档 (*.docx)"),
                "excel": (".xlsx", "Excel 工作簿 (*.xlsx)"),
                "ppt": (".pptx", "PowerPoint 演示文稿 (*.pptx)"),
                "text": (".txt", "文本文件 (*.txt)"),
                "html": (".html", "HTML 文件 (*.html)"),
            }
            suffix, file_filter = suffixes[target_kind]
            target, _ = QFileDialog.getSaveFileName(
                self, "保存转换结果", os.path.join(self._last_dir, stem + suffix), file_filter
            )
            if not target:
                return
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                if target_kind == "image":
                    return convert_core.pdf_to_images(
                        copy, folder, fmt=values["fmt"], dpi=values["dpi"],
                        pages=values["pages"], progress=progress,
                    )
                if target_kind == "word":
                    return convert_core.pdf_to_docx(
                        copy, target, pages=values["pages"],
                        add_page_breaks=values["keep_breaks"], progress=progress,
                    )
                if target_kind == "excel":
                    return convert_core.pdf_to_xlsx(copy, target, pages=values["pages"], progress=progress)
                if target_kind == "ppt":
                    return convert_core.pdf_to_pptx(
                        copy, target, dpi=values["dpi"], pages=values["pages"], progress=progress
                    )
                if target_kind == "text":
                    return convert_core.pdf_to_text(copy, target, pages=values["pages"], progress=progress)
                if target_kind == "html":
                    return convert_core.pdf_to_html(copy, target, pages=values["pages"], progress=progress)
                raise ValueError("未知转换类型")
            finally:
                copy.close()

        def done(result):
            if target_kind == "image":
                self.toast.show_message(f"已导出 {len(result)} 张图片")
                QDesktopServices.openUrl(Path(folder).as_uri())
            else:
                self.toast.show_message("转换完成")
                if QMessageBox.question(
                    self, "转换完成", "转换已完成，是否立即打开文件？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(Path(result).as_uri())

        labels = {
            "word": "PDF 转 Word", "excel": "PDF 转 Excel", "ppt": "PDF 转 PPT",
            "image": "PDF 转图片", "text": "PDF 转文本", "html": "PDF 转 HTML",
        }
        self._run_task(labels.get(target_kind, "文档转换"), task, done, "正在转换，请稍候…")

    def _office_to_pdf(self, extension: str) -> None:
        filters = {
            ".docx": ("Word 文档 (*.docx)", "打开 Word 文档"),
            ".xlsx": ("Excel 工作簿 (*.xlsx)", "打开 Excel 工作簿"),
            ".pptx": ("PowerPoint 演示文稿 (*.pptx)", "打开 PowerPoint 演示文稿"),
        }
        file_filter, caption = filters[extension]
        source, _ = QFileDialog.getOpenFileName(self, caption, self._last_dir, file_filter)
        if not source:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存为 PDF",
            os.path.join(self._last_dir, Path(source).stem + ".pdf"),
            "PDF 文件 (*.pdf)",
        )
        if not target:
            return

        def task(progress, cancelled):
            return convert_core.convert_office_to_pdf(source, target, progress=progress)

        def done(result):
            self.toast.show_message("已转换为 PDF")
            if QMessageBox.question(
                self, "转换完成", "PDF 已生成，是否打开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(result)

        self._run_task("转换为 PDF", task, done, "解析文档并排版")

    def _images_to_pdf(self) -> None:
        images, _ = QFileDialog.getOpenFileNames(self, "选择图片", self._last_dir, SUPPORTED_IMAGES)
        if not images:
            return
        dlg = ImageToPdfDialog(self, images)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        values = dlg.values()
        if not values["images"]:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存 PDF", os.path.join(self._last_dir, "图片合集.pdf"), "PDF 文件 (*.pdf)"
        )
        if not target:
            return

        def task(progress, cancelled):
            return convert_core.images_to_pdf(
                values["images"], target, page_mode=values["mode"], progress=progress
            )

        def done(result):
            self.toast.show_message("图片已生成 PDF")
            if QMessageBox.question(
                self, "生成完成", "PDF 已生成，是否打开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                self.open_path(result)

        self._run_task("图片转 PDF", task, done, f"共 {len(values['images'])} 张图片")

    def _export_all(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择全部导出文件夹", self._last_dir)
        if not folder:
            return
        stem = Path(self.doc_model.file_name).stem or "文档"
        copy = self._doc_copy()

        def task(progress, cancelled):
            try:
                out = []
                progress(5, "导出 Word…")
                out.append(convert_core.pdf_to_docx(copy, os.path.join(folder, stem + ".docx")))
                progress(30, "导出图片…")
                convert_core.pdf_to_images(copy, os.path.join(folder, stem + "_图片"), dpi=150)
                progress(60, "导出 Excel…")
                out.append(convert_core.pdf_to_xlsx(copy, os.path.join(folder, stem + ".xlsx")))
                progress(80, "导出文本…")
                out.append(convert_core.pdf_to_text(copy, os.path.join(folder, stem + ".txt")))
                progress(95, "导出 HTML…")
                out.append(convert_core.pdf_to_html(copy, os.path.join(folder, stem + ".html")))
                return out
            finally:
                copy.close()

        def done(results):
            self.toast.show_message(f"已导出 {len(results) + 1} 种格式")
            QDesktopServices.openUrl(Path(folder).as_uri())

        self._run_task("全部导出", task, done, "同时输出 Word、Excel、图片、文本与 HTML")

    def _conversion_options_info(self) -> None:
        text = (
            "转换设置\n\n"
            "• PDF 转 Word：保留段落、文字颜色与基本样式，图片会嵌入文档。\n"
            "• PDF 转 Excel：优先识别页面中的表格；没有表格时按行写入。\n"
            "• PDF 转 PPT：每页渲染为一张幻灯片，保持原始比例。\n"
            "• PDF 转图片：支持 PNG / JPG / WEBP 与 72–600 DPI。\n"
            "• Office 转 PDF：本地排版引擎处理，复杂动画与特殊字体可能简化。\n\n"
            "提示：扫描版 PDF 建议先执行 OCR，再进行 Word / Excel 转换。"
        )
        TextResultDialog(self, "转换设置", text, 560).exec()

    def _conversion_preview(self) -> None:
        try:
            pix = self.doc_model.render_dpi(self.viewer.current_page, dpi=120)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            dialog = QDialog(self)
            dialog.setWindowTitle("转换预览")
            dialog.resize(min(900, image.width() + 40), min(760, image.height() + 90))
            layout = QVBoxLayout(dialog)
            label = QLabel(dialog)
            label.setPixmap(QPixmap.fromImage(image).scaled(
                840, 680, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            close = QPushButton("关闭", dialog)
            close.clicked.connect(dialog.accept)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(close)
            layout.addLayout(row)
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, "预览失败", str(exc))

    # -------------------------------------------------------------------- AI
    def _handle_ai_action(self, action: str) -> None:
        if action == "ai.about" or action == "ai.local":
            text = (
                "星澜本地智能\n\n"
                "• 智能摘要：抽取文档中最具代表性的句子，按原文顺序呈现。\n"
                "• 关键词：基于词频与词组长度评分，不依赖云端模型。\n"
                "• 文档问答：在文档中检索与问题最相关的段落，并给出原文依据。\n"
                "• 全文翻译：离线版本不内置第三方翻译接口，避免文件外传。\n\n"
                "所有分析都在本机内存中完成，不会上传文档内容。"
            )
            TextResultDialog(self, "本地智能说明", text, 580).exec()
            return
        if action == "ai.proofread":
            text = self.doc_model.all_text(300000)
            issues = []
            if re.search(r"[，。！？；：]{2,}", text):
                issues.append("发现重复的标点符号。")
            if "  " in text:
                issues.append("发现连续两个空格。")
            if "的的" in text or "了了" in text:
                issues.append("发现重复字词（如“的的”“了了”）。")
            if re.search(r"[\u4e00-\u9fff][,;:!?]", text):
                issues.append("中文句子中使用了半角标点。")
            if not issues:
                issues.append("未发现明显的标点或重复字词问题。")
            TextResultDialog(self, "文字检查", "\n".join("• " + i for i in issues), 520).exec()
            return
        if action == "ai.wordcount":
            text = self.doc_model.all_text(2000000)
            chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
            english = len(re.findall(r"[A-Za-z]+", text))
            digits = len(re.findall(r"\d+", text))
            summary = (
                f"字数统计\n\n页数：{self.doc_model.page_count}\n"
                f"汉字：{chinese:,}\n英文单词：{english:,}\n数字串：{digits:,}\n"
                f"总字符：{len(text):,}"
            )
            TextResultDialog(self, "字数统计", summary, 440).exec()
            return
        if self.doc_model is None or not self.doc_model.is_open:
            return
        text = self.doc_model.all_text(450000)
        if not text.strip():
            self.toast.show_message("文档没有可分析的文本，扫描件请先 OCR")
            return
        selected = self.viewer.selected_text
        if action == "ai.summary":
            dlg = AIDialog(self, text, selected)
            dlg._summary()
            dlg.exec()
        elif action == "ai.outline":
            dlg = AIDialog(self, text, selected)
            dlg._outline()
            dlg.exec()
        elif action == "ai.keywords":
            dlg = AIDialog(self, text, selected)
            dlg._keywords()
            dlg.exec()
        elif action in ("ai.qa", "ai.selection_qa"):
            source = selected if action == "ai.selection_qa" and selected.strip() else text
            AIDialog(self, source, selected).exec()
        elif action == "ai.explain":
            source = selected.strip() or text[:12000]
            dlg = AIDialog(self, source, selected)
            dlg._summary()
            dlg.exec()
        elif action == "ai.rewrite":
            source = selected.strip()
            if not source:
                self.toast.show_message("请先选中要润色的文字")
                return
            cleaned = re.sub(r"[ \t]+", " ", source)
            cleaned = re.sub(r"([，。！？；：])\1+", r"\1", cleaned)
            cleaned = cleaned.replace("的的", "的").replace("了了", "了")
            TextResultDialog(
                self, "文字润色建议",
                "原文：\n" + source + "\n\n整理后：\n" + cleaned +
                "\n\n（本地规则整理，不会自动修改文档）",
                580,
            ).exec()
        elif action == "ai.translate":
            dlg = AIDialog(self, text, selected)
            dlg._translate()
            dlg.exec()

    # --------------------------------------------------------------- workers
    def _run_task(
        self,
        title: str,
        function: Callable,
        on_done: Callable[[Any], None] | None = None,
        subtitle: str = "正在处理，请稍候…",
    ) -> None:
        dialog = TaskProgressDialog(self, title, subtitle)
        worker = FunctionWorker(function, self)
        self._active_worker = worker
        worker.progress.connect(dialog.set_progress)
        worker.done.connect(lambda result: self._task_done(dialog, worker, result, on_done))
        worker.failed.connect(lambda message: self._task_failed(dialog, worker, message))
        dialog.rejected.connect(worker.cancel)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.start()
        dialog.exec()

    def _task_done(self, dialog: TaskProgressDialog, worker: FunctionWorker, result, on_done) -> None:
        dialog.accept()
        if self._active_worker is worker:
            self._active_worker = None
        if on_done:
            try:
                on_done(result)
            except Exception as exc:
                QMessageBox.critical(self, "操作失败", str(exc))

    def _task_failed(self, dialog: TaskProgressDialog, worker: FunctionWorker, message: str) -> None:
        dialog.reject()
        if self._active_worker is worker:
            self._active_worker = None
        QMessageBox.critical(self, "操作失败", message)

    def _cleanup_worker(self, worker: FunctionWorker) -> None:
        if self._active_worker is worker:
            self._active_worker = None
        worker.deleteLater()

    # --------------------------------------------------------------- helpers
    def _doc_copy(self) -> PdfDocument:
        copy = PdfDocument()
        try:
            data = self.doc_model.require_doc().tobytes(
                garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_NONE
            )
        except Exception:
            data = self.doc_model.require_doc().tobytes(garbage=0, deflate=False)
        copy.doc = pymupdf.open(stream=data, filetype="pdf")
        if copy.doc.needs_pass and self.doc_model.password:
            copy.doc.authenticate(self.doc_model.password)
        copy.path = None
        copy.password = self.doc_model.password
        copy.page = self.viewer.current_page
        return copy

    @staticmethod
    def _open_facade(path: str) -> PdfDocument | None:
        try:
            facade = PdfDocument()
            facade.open(path)
            return facade
        except Exception:
            return None
