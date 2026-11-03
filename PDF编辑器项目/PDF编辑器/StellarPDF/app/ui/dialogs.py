"""Modal dialogs used across the ribbon."""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION, SUPPORTED_IMAGES, cjk_font_file
from ..core.document import AnnotInfo, TextSpan, WidgetInfo
from ..icons import app_icon, icon
from ..theme import C
from .imageutil import qimage_png


# --------------------------------------------------------------------- helpers
def _page_scope_values(widget: "PageScopeWidget", count: int) -> list[int]:
    return widget.pages(count)


def _button_row(dialog: QDialog, ok_text: str = "确定", cancel_text: str = "取消") -> QDialogButtonBox:
    box = QDialogButtonBox(dialog)
    ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setObjectName("Primary")
    cancel = box.addButton(cancel_text, QDialogButtonBox.ButtonRole.RejectRole)
    ok.setMinimumWidth(88)
    cancel.setMinimumWidth(76)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class BaseDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, subtitle: str = "", width: int = 480) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.setMinimumWidth(width)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 18, 22, 16)
        self._root.setSpacing(12)
        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(3)
        title_label = QLabel(title, header)
        title_label.setStyleSheet("font-size:14pt; font-weight:600; color:#202635;")
        header_layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle, header)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.8pt;")
            header_layout.addWidget(sub)
        self._root.addWidget(header)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self._root.addWidget(self.body, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(0, 4, 0, 0)
        self._root.addLayout(self.footer)

    def finish(self, ok_text: str = "确定") -> QDialogButtonBox:
        box = _button_row(self, ok_text)
        self.footer.addStretch(1)
        self.footer.addWidget(box)
        return box


class ColorButton(QPushButton):
    def __init__(self, color: str = "#2F6BFF", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(64, 28)
        self.clicked.connect(self._pick)
        self._update()

    def _update(self) -> None:
        self.setText(self._color.upper())
        self.setStyleSheet(
            f"QPushButton {{ background:{self._color}; color:"
            f"{'#111' if QColor(self._color).lightness() > 150 else 'white'};"
            "border:1px solid #C9D0DC; border-radius:5px; font-size:8pt; }"
        )

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "选择颜色")
        if color.isValid():
            self._color = color.name()
            self._update()

    def value(self) -> str:
        return self._color


class PageScopeWidget(QWidget):
    def __init__(self, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.count = count
        self.current = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.radio_all = QCheckBox("全部页面", self)
        self.radio_current = QCheckBox("当前页", self)
        self.radio_custom = QCheckBox("指定范围", self)
        self.radio_all.setChecked(True)
        for radio in (self.radio_all, self.radio_current, self.radio_custom):
            radio.setAutoExclusive(True)
            layout.addWidget(radio)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("例如：1-3, 5, 8-10")
        self.edit.setEnabled(False)
        self.radio_custom.toggled.connect(self.edit.setEnabled)
        row = QHBoxLayout()
        row.setContentsMargins(22, 0, 0, 0)
        row.addWidget(self.edit)
        layout.addLayout(row)
        self.radio_current.setText(f"当前页（第 {self.current + 1} 页）")

    def set_current(self, index: int) -> None:
        self.current = max(0, index)
        self.radio_current.setText(f"当前页（第 {self.current + 1} 页）")

    def pages(self, count: int | None = None) -> list[int]:
        count = count or self.count
        if self.radio_all.isChecked():
            return list(range(count))
        if self.radio_current.isChecked():
            return [min(self.current, max(0, count - 1))]
        return parse_page_ranges(self.edit.text(), count)


def parse_page_ranges(text: str, count: int) -> list[int]:
    pages: set[int] = set()
    for part in re.split(r"[,，;；\s]+", text.strip()):
        if not part:
            continue
        if "-" in part or "–" in part:
            bits = re.split(r"[-–]", part, maxsplit=1)
            try:
                start = int(bits[0])
                end = int(bits[1])
            except Exception:
                continue
            if start > end:
                start, end = end, start
            for value in range(start, end + 1):
                if 1 <= value <= count:
                    pages.add(value - 1)
        else:
            try:
                value = int(part)
            except Exception:
                continue
            if 1 <= value <= count:
                pages.add(value - 1)
    return sorted(pages)


# ---------------------------------------------------------------------- password
class PasswordDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str = "输入密码",
        message: str = "此 PDF 受密码保护，请输入打开密码。",
        *,
        confirm: bool = False,
    ) -> None:
        super().__init__(parent, title, message, 430)
        self.edit = QLineEdit(self)
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("密码")
        self.body_layout.addWidget(self.edit)
        self.confirm_edit: QLineEdit | None = None
        if confirm:
            self.confirm_edit = QLineEdit(self)
            self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_edit.setPlaceholderText("再次输入密码")
            self.body_layout.addWidget(self.confirm_edit)
        self.finish("解锁")
        self.edit.setFocus()

    def accept(self) -> None:
        if self.confirm_edit is not None and self.edit.text() != self.confirm_edit.text():
            QMessageBox.warning(self, "密码不一致", "两次输入的密码不一致。")
            return
        if not self.edit.text():
            QMessageBox.warning(self, "请输入密码", "密码不能为空。")
            return
        super().accept()

    def value(self) -> str:
        return self.edit.text()


# -------------------------------------------------------------------- text editing
class TextEditDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, span: TextSpan) -> None:
        super().__init__(
            parent,
            "编辑文字",
            "原文字将被替换，周围内容与排版保持不变。支持中文、英文和换行。",
            520,
        )
        self.span = span
        self.editor = QTextEdit(self)
        self.editor.setPlainText(span.text)
        self.editor.setMinimumHeight(130)
        self.body_layout.addWidget(self.editor)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(4, 200)
        self.size.setDecimals(1)
        self.size.setValue(max(4.0, float(span.size or 11)))
        self.size.setSuffix(" pt")
        form.addRow("字号", self.size)
        self.color = ColorButton(
            "#%02X%02X%02X" % tuple(int(c * 255) for c in span.color), self
        )
        form.addRow("颜色", self.color)
        self.bold = QCheckBox("粗体", self)
        self.bold.setChecked(span.bold)
        self.align = QComboBox(self)
        self.align.addItems(["左对齐", "居中", "右对齐", "两端对齐"])
        row = QHBoxLayout()
        row.addWidget(self.bold)
        row.addWidget(QLabel("对齐", self))
        row.addWidget(self.align)
        row.addStretch(1)
        form.addRow("", row)
        self.body_layout.addLayout(form)
        self.finish("应用修改")
        self.editor.setFocus()
        self.editor.selectAll()

    def values(self) -> dict[str, Any]:
        return {
            "text": self.editor.toPlainText(),
            "size": self.size.value(),
            "color": self.color.value(),
            "bold": self.bold.isChecked(),
            "align": self.align.currentIndex(),
        }


class TextInsertDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, *, box: bool = False, default_text: str = "") -> None:
        super().__init__(
            parent,
            "添加文本框" if box else "插入文字",
            "文字将直接写入 PDF；双击已有文字可继续编辑。",
            500,
        )
        self.editor = QTextEdit(self)
        self.editor.setPlainText(default_text)
        self.editor.setPlaceholderText("输入要添加到 PDF 的文字…")
        self.editor.setMinimumHeight(130)
        self.body_layout.addWidget(self.editor)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(4, 200)
        self.size.setValue(14)
        self.size.setSuffix(" pt")
        form.addRow("字号", self.size)
        self.color = ColorButton("#1F2430", self)
        form.addRow("颜色", self.color)
        self.bold = QCheckBox("粗体", self)
        self.align = QComboBox(self)
        self.align.addItems(["左对齐", "居中", "右对齐"])
        row = QHBoxLayout()
        row.addWidget(self.bold)
        row.addWidget(self.align)
        row.addStretch(1)
        form.addRow("样式", row)
        self.body_layout.addLayout(form)
        self.finish("插入")
        self.editor.setFocus()

    def values(self) -> dict[str, Any]:
        return {
            "text": self.editor.toPlainText(),
            "size": self.size.value(),
            "color": self.color.value(),
            "bold": self.bold.isChecked(),
            "align": self.align.currentIndex(),
        }


# -------------------------------------------------------------------- watermark
class WatermarkPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.text = "内部资料"
        self.color = QColor("#8C93A3")
        self.opacity = 0.2
        self.angle = 45
        self.tiled = False
        self.setMinimumHeight(150)
        self.setStyleSheet("background:#E9EDF4; border-radius:6px;")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page = QRectF(self.width() / 2 - 70, 12, 140, 126)
        painter.setPen(QPen(QColor("#D7DEE9"), 1))
        painter.setBrush(QColor("white"))
        painter.drawRect(page)
        color = QColor(self.color)
        color.setAlphaF(max(0.03, self.opacity))
        painter.setPen(color)
        font = QFont("Microsoft YaHei UI", 10)
        painter.setFont(font)
        painter.translate(page.center())
        painter.rotate(-self.angle)
        if self.tiled:
            for y in (-45, 8, 58):
                painter.drawText(QRectF(-90, y, 180, 24), Qt.AlignmentFlag.AlignCenter, self.text)
        else:
            painter.drawText(QRectF(-90, -12, 180, 24), Qt.AlignmentFlag.AlignCenter, self.text)


class WatermarkDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int, *, image: bool = False) -> None:
        super().__init__(
            parent,
            "添加图片水印" if image else "添加文字水印",
            "水印会写入所有选中页面，可设置透明度和角度。",
            560,
        )
        self.image_mode = image
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.image_edit: QLineEdit | None = None
        if image:
            row = QHBoxLayout()
            self.image_edit = QLineEdit(self)
            self.image_edit.setPlaceholderText("选择 PNG / JPG 图片")
            browse = QPushButton("浏览…", self)
            browse.clicked.connect(self._browse_image)
            row.addWidget(self.image_edit, 1)
            row.addWidget(browse)
            form.addRow("水印图片", row)
        else:
            self.text = QLineEdit("内部资料", self)
            form.addRow("水印文字", self.text)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(8, 200)
        self.size.setValue(54)
        self.size.setSuffix(" pt")
        if not image:
            form.addRow("字号", self.size)
        self.color = ColorButton("#8C93A3", self)
        if not image:
            form.addRow("颜色", self.color)
        self.opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setRange(3, 80)
        self.opacity.setValue(18)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        self.opacity_label = QLabel("18%", self)
        self.opacity_label.setFixedWidth(38)
        self.opacity.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_row.addWidget(self.opacity_label)
        form.addRow("透明度", opacity_row)
        self.angle = QSpinBox(self)
        self.angle.setRange(-90, 90)
        self.angle.setValue(45)
        self.angle.setSuffix("°")
        form.addRow("旋转角度", self.angle)
        self.tiled = QCheckBox("平铺水印", self)
        form.addRow("", self.tiled)
        self.body_layout.addLayout(form)
        self.body_layout.addWidget(QLabel("预览", self))
        self.preview = WatermarkPreview(self)
        self.body_layout.addWidget(self.preview)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.body_layout.addWidget(self.scope)
        for widget in (self.text if not image else None, self.size, self.color, self.angle, self.tiled):
            if widget is None:
                continue
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._sync_preview)
            else:
                try:
                    widget.valueChanged.connect(self._sync_preview)
                except Exception:
                    widget.toggled.connect(self._sync_preview)
        self.opacity.valueChanged.connect(self._sync_preview)
        self.preview.text = self.text.text() if not image else "图片水印"
        self.finish("添加水印")

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", SUPPORTED_IMAGES)
        if path and self.image_edit:
            self.image_edit.setText(path)

    def _sync_preview(self, *args) -> None:
        if not self.image_mode:
            self.preview.text = self.text.text() or "水印"
            self.preview.color = QColor(self.color.value())
            self.preview.angle = self.angle.value()
        self.preview.opacity = self.opacity.value() / 100
        self.preview.tiled = self.tiled.isChecked()
        self.preview.update()

    def values(self, count: int) -> dict[str, Any]:
        return {
            "text": self.text.text() if not self.image_mode else "",
            "path": self.image_edit.text() if self.image_edit else "",
            "size": self.size.value(),
            "color": self.color.value(),
            "opacity": self.opacity.value() / 100,
            "angle": self.angle.value(),
            "tiled": self.tiled.isChecked(),
            "pages": self.scope.pages(count),
        }


class BackgroundDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "设置页面背景", "为选中页面添加纯色或图片背景，位于内容下层。", 500)
        self.mode = QComboBox(self)
        self.mode.addItems(["纯色背景", "图片背景"])
        self.color = ColorButton("#F6F3E8", self)
        row = QHBoxLayout()
        row.addWidget(self.mode)
        row.addWidget(self.color)
        row.addStretch(1)
        self.body_layout.addLayout(row)
        self.image_edit = QLineEdit(self)
        self.image_edit.setPlaceholderText("图片路径")
        browse = QPushButton("浏览…", self)
        browse.clicked.connect(self._browse)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_edit, 1)
        image_row.addWidget(browse)
        self.body_layout.addLayout(image_row)
        self.opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(100)
        self.body_layout.addWidget(QLabel("图片不透明度", self))
        self.body_layout.addWidget(self.opacity)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(self.scope)
        self.finish("应用背景")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "", SUPPORTED_IMAGES)
        if path:
            self.image_edit.setText(path)
            self.mode.setCurrentIndex(1)

    def values(self, count: int) -> dict[str, Any]:
        return {
            "color": self.color.value() if self.mode.currentIndex() == 0 else None,
            "image": self.image_edit.text() if self.mode.currentIndex() == 1 else None,
            "opacity": self.opacity.value() / 100,
            "pages": self.scope.pages(count),
        }


class HeaderFooterDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int, *, footer: bool = False) -> None:
        super().__init__(
            parent,
            "添加页脚" if footer else "添加页眉",
            "可使用 {page} 表示当前页码，{total} 表示总页数。",
            500,
        )
        self.is_footer = footer
        self.text = QLineEdit("第 {page} 页 / 共 {total} 页", self)
        self.body_layout.addWidget(self.text)
        form = QFormLayout()
        self.position = QComboBox(self)
        options = ["左侧", "居中", "右侧"]
        self.position.addItems(options)
        self.position.setCurrentIndex(1)
        form.addRow("对齐", self.position)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(6, 36)
        self.size.setValue(9)
        self.size.setSuffix(" pt")
        form.addRow("字号", self.size)
        self.color = ColorButton("#5E6678", self)
        form.addRow("颜色", self.color)
        self.margin = QDoubleSpinBox(self)
        self.margin.setRange(6, 120)
        self.margin.setValue(24)
        self.margin.setSuffix(" pt")
        form.addRow("边距", self.margin)
        self.body_layout.addLayout(form)
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.body_layout.addWidget(self.scope)
        self.finish("应用")

    def values(self, count: int) -> dict[str, Any]:
        position = ["top-left", "top-center", "top-right"] if not self.is_footer else [
            "bottom-left", "bottom-center", "bottom-right"
        ]
        return {
            "text": self.text.text(),
            "position": position[self.position.currentIndex()],
            "size": self.size.value(),
            "color": self.color.value(),
            "margin": self.margin.value(),
            "pages": self.scope.pages(count),
        }


class PageNumberDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "添加页码", "页码会写入页面内容，可选择位置与起始编号。", 500)
        form = QFormLayout()
        self.fmt = QComboBox(self)
        self.fmt.addItems(["第 {page} 页 / 共 {total} 页", "{page}", "{page} / {total}", "第 {page} 页"])
        self.fmt.setEditable(True)
        form.addRow("格式", self.fmt)
        self.position = QComboBox(self)
        self.position.addItems([
            "底部居中", "底部左侧", "底部右侧", "顶部居中", "顶部左侧", "顶部右侧",
        ])
        form.addRow("位置", self.position)
        self.start = QSpinBox(self)
        self.start.setRange(1, 9999)
        form.addRow("起始页码", self.start)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(6, 36)
        self.size.setValue(9)
        self.size.setSuffix(" pt")
        form.addRow("字号", self.size)
        self.color = ColorButton("#5E6678", self)
        form.addRow("颜色", self.color)
        self.body_layout.addLayout(form)
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.body_layout.addWidget(self.scope)
        self.finish("添加页码")

    def values(self, count: int) -> dict[str, Any]:
        mapping = {
            0: "bottom-center", 1: "bottom-left", 2: "bottom-right",
            3: "top-center", 4: "top-left", 5: "top-right",
        }
        return {
            "fmt": self.fmt.currentText(),
            "position": mapping[self.position.currentIndex()],
            "start": self.start.value(),
            "size": self.size.value(),
            "color": self.color.value(),
            "pages": self.scope.pages(count),
        }


# ---------------------------------------------------------------------- stamps
class StampDialog(BaseDialog):
    PRESETS = [
        ("已批准", "APPROVED", "#D93B3B"),
        ("已驳回", "REJECTED", "#D93B3B"),
        ("草稿", "DRAFT", "#2F6BFF"),
        ("机密", "CONFIDENTIAL", "#D93B3B"),
        ("仅供内部使用", "INTERNAL USE", "#7A5AF8"),
        ("已归档", "ARCHIVED", "#18A66F"),
    ]

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, "添加图章", "选择预设图章，或输入自定义文字。", 520)
        grid = QGridLayout()
        grid.setSpacing(7)
        self.selected = 0
        self.buttons: list[QPushButton] = []
        for i, (text, subtitle, color) in enumerate(self.PRESETS):
            button = QPushButton(f"{text}\n{subtitle}", self)
            button.setFixedHeight(50)
            button.setStyleSheet(
                f"QPushButton {{ border:2px solid {color}; color:{color}; border-radius:6px;"
                "font-weight:600; background:white; }"
                "QPushButton:checked { background:#FFF1F1; }"
            )
            button.setCheckable(True)
            button.setChecked(i == 0)
            button.clicked.connect(lambda checked=False, index=i: self._select(index))
            self.buttons.append(button)
            grid.addWidget(button, i // 3, i % 3)
        self.body_layout.addLayout(grid)
        form = QFormLayout()
        self.text = QLineEdit("已批准", self)
        self.subtitle = QLineEdit("APPROVED", self)
        form.addRow("图章文字", self.text)
        form.addRow("副标题", self.subtitle)
        self.color = ColorButton("#D93B3B", self)
        form.addRow("颜色", self.color)
        self.body_layout.addLayout(form)
        self.finish("放置图章")

    def _select(self, index: int) -> None:
        self.selected = index
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
        text, subtitle, color = self.PRESETS[index]
        self.text.setText(text)
        self.subtitle.setText(subtitle)
        self.color._color = color
        self.color._update()

    def values(self) -> dict[str, str]:
        return {
            "text": self.text.text(),
            "subtitle": self.subtitle.text(),
            "color": self.color.value(),
        }


# -------------------------------------------------------------------- signature
class SignaturePad(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 180)
        self.setStyleSheet("background:white; border:1px dashed #C9D2E0; border-radius:8px;")
        self.paths: list[QPainterPath] = []
        self._current: QPainterPath | None = None
        self.pen_width = 3

    def clear(self) -> None:
        self.paths.clear()
        self._current = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._current = QPainterPath(event.position())
            self.paths.append(self._current)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._current is not None:
            self._current.lineTo(event.position())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._current = None

    def isEmpty(self) -> bool:
        return not self.paths

    def render_png(self) -> bytes:
        scale = 3
        image = QImage(self.width() * scale, self.height() * scale, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        pen = QPen(QColor("#16233F"), self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for path in self.paths:
            painter.drawPath(path)
        painter.end()
        # Crop transparent margins.
        buffer = QPixmap.fromImage(image)
        image = buffer.toImage()
        rect = image.rect()
        left, top, right, bottom = rect.width(), rect.height(), 0, 0
        found = False
        for y in range(0, rect.height(), 2):
            for x in range(0, rect.width(), 2):
                if image.pixelColor(x, y).alpha() > 8:
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x), max(bottom, y)
                    found = True
        if found:
            image = image.copy(QRect(max(0, left - 12), max(0, top - 12), right - left + 24, bottom - top + 24))
        return qimage_png(image)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#16233F"), self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for path in self.paths:
            painter.drawPath(path)
        if not self.paths:
            painter.setPen(QColor("#B4BCCB"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "请在此处用鼠标手写签名")


class SignatureDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, saved: bytes | None = None) -> None:
        super().__init__(parent, "添加签名", "签名图片会以透明图层放置到 PDF 页面。", 620)
        self.tabs = QTabWidget(self)
        # Draw tab
        draw_page = QWidget(self)
        draw_layout = QVBoxLayout(draw_page)
        draw_layout.setContentsMargins(10, 12, 10, 10)
        self.pad = SignaturePad(draw_page)
        draw_layout.addWidget(self.pad)
        row = QHBoxLayout()
        clear = QPushButton("清除", draw_page)
        clear.clicked.connect(self.pad.clear)
        row.addWidget(clear)
        row.addStretch(1)
        tip = QLabel("建议使用鼠标或触控笔书写", draw_page)
        tip.setStyleSheet(f"color:{C.TEXT_MUTED};")
        row.addWidget(tip)
        draw_layout.addLayout(row)
        self.tabs.addTab(draw_page, "手写签名")
        # Type tab
        type_page = QWidget(self)
        type_layout = QVBoxLayout(type_page)
        type_layout.setContentsMargins(14, 18, 14, 14)
        self.type_edit = QLineEdit(type_page)
        self.type_edit.setPlaceholderText("输入姓名")
        self.type_edit.setStyleSheet("font-size:20pt; padding:10px;")
        type_layout.addWidget(self.type_edit)
        type_form = QFormLayout()
        self.type_font = QComboBox(type_page)
        self.type_font.addItems(["楷体", "微软雅黑", "宋体", "黑体", "Segoe Script"])
        type_form.addRow("字体", self.type_font)
        self.type_color = ColorButton("#16233F", type_page)
        type_form.addRow("颜色", self.type_color)
        type_layout.addLayout(type_form)
        type_layout.addStretch(1)
        self.tabs.addTab(type_page, "输入签名")
        # Upload tab
        upload_page = QWidget(self)
        upload_layout = QVBoxLayout(upload_page)
        upload_layout.setContentsMargins(14, 18, 14, 14)
        row = QHBoxLayout()
        self.upload_edit = QLineEdit(upload_page)
        self.upload_edit.setPlaceholderText("选择透明背景的 PNG 图片")
        browse = QPushButton("浏览…", upload_page)
        browse.clicked.connect(self._browse)
        row.addWidget(self.upload_edit, 1)
        row.addWidget(browse)
        upload_layout.addLayout(row)
        self.upload_preview = QLabel("尚未选择图片", upload_page)
        self.upload_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upload_preview.setMinimumHeight(130)
        self.upload_preview.setStyleSheet("background:#F7F9FC; border:1px dashed #CCD4E1; border-radius:8px;")
        upload_layout.addWidget(self.upload_preview)
        self.tabs.addTab(upload_page, "上传图片")
        self.body_layout.addWidget(self.tabs)
        self.finish("使用签名")
        if saved:
            self._saved = saved
        else:
            self._saved = None

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择签名图片", "", SUPPORTED_IMAGES)
        if path:
            self.upload_edit.setText(path)
            pix = QPixmap(path)
            if not pix.isNull():
                self.upload_preview.setPixmap(pix.scaled(420, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _typed_png(self) -> bytes:
        text = self.type_edit.text().strip()
        if not text:
            return b""
        font_name = ["KaiTi", "Microsoft YaHei", "SimSun", "SimHei", "Segoe Script"][self.type_font.currentIndex()]
        image = QImage(760, 240, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(font_name, 72)
        painter.setFont(font)
        painter.setPen(QColor(self.type_color.value()))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return qimage_png(image)

    def _uploaded_png(self) -> bytes:
        path = self.upload_edit.text()
        if not path or not os.path.exists(path):
            return b""
        try:
            image = Image.open(path).convert("RGBA")
            pixels = image.getdata()
            new_pixels = []
            for r, g, b, a in pixels:
                if r > 242 and g > 242 and b > 242:
                    new_pixels.append((255, 255, 255, 0))
                elif r < 35 and g < 35 and b < 35:
                    new_pixels.append((22, 35, 63, 255))
                else:
                    new_pixels.append((r, g, b, a))
            image.putdata(new_pixels)
            bbox = image.getbbox()
            if bbox:
                image = image.crop(bbox)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            return buffer.getvalue()
        except Exception:
            return b""

    def accept(self) -> None:
        index = self.tabs.currentIndex()
        if index == 0:
            if self.pad.isEmpty():
                QMessageBox.information(self, "签名", "请先在签名板上手写签名。")
                return
            self._saved = self.pad.render_png()
        elif index == 1:
            data = self._typed_png()
            if not data:
                QMessageBox.information(self, "签名", "请输入签名文字。")
                return
            self._saved = data
        else:
            data = self._uploaded_png()
            if not data:
                QMessageBox.information(self, "签名", "请选择有效的签名图片。")
                return
            self._saved = data
        super().accept()

    def png(self) -> bytes:
        return self._saved or b""


# --------------------------------------------------------------------- security
class EncryptDialog(BaseDialog):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(
            parent,
            "加密文档",
            "设置打开密码与权限密码。权限密码用于限制打印、复制和编辑。",
            560,
        )
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.user = QLineEdit(self)
        self.user.setEchoMode(QLineEdit.EchoMode.Password)
        self.user.setPlaceholderText("留空则无需密码即可打开")
        form.addRow("打开密码", self.user)
        self.owner = QLineEdit(self)
        self.owner.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner.setPlaceholderText("用于修改权限，请妥善保管")
        form.addRow("权限密码", self.owner)
        self.algorithm = QComboBox(self)
        self.algorithm.addItems(["AES-256（推荐）", "AES-128"])
        form.addRow("加密算法", self.algorithm)
        self.body_layout.addLayout(form)
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{C.BORDER};")
        self.body_layout.addWidget(line)
        self.body_layout.addWidget(QLabel("权限设置", self))
        grid = QGridLayout()
        grid.setSpacing(7)
        self.perms: dict[str, QCheckBox] = {}
        options = [
            ("print", "允许打印", True),
            ("print_hq", "允许高质量打印", True),
            ("modify", "允许修改内容", True),
            ("copy", "允许复制文字", True),
            ("annotate", "允许添加批注", True),
            ("forms", "允许填写表单", True),
            ("extract", "允许提取页面", True),
            ("assemble", "允许拼合页面", True),
            ("accessibility", "允许辅助功能", True),
        ]
        for i, (key, label, checked) in enumerate(options):
            box = QCheckBox(label, self)
            box.setChecked(checked)
            self.perms[key] = box
            grid.addWidget(box, i // 3, i % 3)
        self.body_layout.addLayout(grid)
        self.finish("加密并保存")

    def accept(self) -> None:
        if not self.user.text() and not self.owner.text():
            QMessageBox.warning(self, "加密文档", "请至少设置一个打开密码或权限密码。")
            return
        if not self.owner.text():
            QMessageBox.warning(self, "加密文档", "请设置权限密码，以免权限设置失效。")
            return
        super().accept()

    def values(self) -> dict[str, Any]:
        return {
            "user": self.user.text(),
            "owner": self.owner.text(),
            "algorithm": "aes256" if self.algorithm.currentIndex() == 0 else "aes128",
            "permissions": {k: v.isChecked() for k, v in self.perms.items()},
        }


class PermissionDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, current: int) -> None:
        super().__init__(
            parent,
            "权限设置",
            "修改权限需要权限密码。权限仅在支持 PDF 权限的阅读器中生效。",
            540,
        )
        self.owner = QLineEdit(self)
        self.owner.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner.setPlaceholderText("权限密码（所有者密码）")
        self.body_layout.addWidget(self.owner)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.perms: dict[str, QCheckBox] = {}
        options = [
            ("print", "允许打印", True),
            ("print_hq", "高质量打印", True),
            ("modify", "允许修改", True),
            ("copy", "允许复制", True),
            ("annotate", "允许批注", True),
            ("forms", "允许填写表单", True),
            ("extract", "允许提取", True),
            ("assemble", "允许拼合", True),
            ("accessibility", "辅助功能", True),
        ]
        for i, (key, label, checked) in enumerate(options):
            box = QCheckBox(label, self)
            box.setChecked(checked)
            self.perms[key] = box
            grid.addWidget(box, i // 3, i % 3)
        self.body_layout.addLayout(grid)
        self.finish("应用权限")

    def values(self) -> dict[str, Any]:
        return {
            "owner": self.owner.text(),
            "permissions": {k: v.isChecked() for k, v in self.perms.items()},
        }


# ------------------------------------------------------------------ page dialogs
class PageSizeDialog(BaseDialog):
    SIZES = {
        "A4（210 × 297 mm）": (595, 842),
        "A3（297 × 420 mm）": (842, 1191),
        "A5（148 × 210 mm）": (420, 595),
        "Letter（8.5 × 11 in）": (612, 792),
        "Legal（8.5 × 14 in）": (612, 1008),
    }

    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "页面大小", "将页面调整为指定尺寸，内容按比例缩放并居中。", 500)
        form = QFormLayout()
        self.preset = QComboBox(self)
        self.preset.addItems(list(self.SIZES.keys()) + ["自定义"])
        self.preset.currentTextChanged.connect(self._preset_changed)
        form.addRow("预设", self.preset)
        self.width = QDoubleSpinBox(self)
        self.width.setRange(50, 5000)
        self.width.setValue(595)
        self.width.setSuffix(" pt")
        form.addRow("宽度", self.width)
        self.height = QDoubleSpinBox(self)
        self.height.setRange(50, 5000)
        self.height.setValue(842)
        self.height.setSuffix(" pt")
        form.addRow("高度", self.height)
        self.orientation = QComboBox(self)
        self.orientation.addItems(["纵向", "横向"])
        form.addRow("方向", self.orientation)
        self.keep_ratio = QCheckBox("保持内容比例", self)
        self.keep_ratio.setChecked(True)
        form.addRow("", self.keep_ratio)
        self.body_layout.addLayout(form)
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.body_layout.addWidget(self.scope)
        self.finish("应用页面大小")

    def _preset_changed(self, text: str) -> None:
        if text in self.SIZES:
            w, h = self.SIZES[text]
            self.width.setValue(w)
            self.height.setValue(h)

    def values(self, count: int) -> dict[str, Any]:
        w, h = self.width.value(), self.height.value()
        if self.orientation.currentIndex() == 1 and h > w:
            w, h = h, w
        return {
            "width": w,
            "height": h,
            "pages": self.scope.pages(count),
            "keep_ratio": self.keep_ratio.isChecked(),
        }


class CropDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "裁剪页面", "输入要裁掉的边距，单位为点（1 pt ≈ 0.353 mm）。", 460)
        self.values_widgets: dict[str, QDoubleSpinBox] = {}
        grid = QGridLayout()
        for i, (key, label) in enumerate([("left", "左"), ("top", "上"), ("right", "右"), ("bottom", "下")]):
            grid.addWidget(QLabel(label, self), i // 2, (i % 2) * 2)
            spin = QDoubleSpinBox(self)
            spin.setRange(0, 1000)
            spin.setSuffix(" pt")
            spin.setValue(18)
            self.values_widgets[key] = spin
            grid.addWidget(spin, i // 2, (i % 2) * 2 + 1)
        self.body_layout.addLayout(grid)
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("应用范围", self))
        self.body_layout.addWidget(self.scope)
        self.finish("裁剪")

    def values(self, count: int) -> dict[str, Any]:
        return {
            "margins": tuple(self.values_widgets[k].value() for k in ("left", "top", "right", "bottom")),
            "pages": self.scope.pages(count),
        }


class SplitDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, default_dir: str) -> None:
        super().__init__(parent, "拆分文档", "按页数或指定范围生成多个 PDF 文件。", 540)
        self.mode = QComboBox(self)
        self.mode.addItems(["每 N 页拆分", "按指定范围拆分", "每页单独拆分"])
        self.body_layout.addWidget(self.mode)
        self.every = QSpinBox(self)
        self.every.setRange(1, max(1, count))
        self.every.setValue(1)
        row = QHBoxLayout()
        row.addWidget(QLabel("每", self))
        row.addWidget(self.every)
        row.addWidget(QLabel("页生成一个文件", self))
        row.addStretch(1)
        self.body_layout.addLayout(row)
        self.ranges = QLineEdit(self)
        self.ranges.setPlaceholderText("例如：1-3, 4-6, 7-10")
        self.body_layout.addWidget(QLabel("范围（每段一个文件）", self))
        self.body_layout.addWidget(self.ranges)
        self.dir_edit = QLineEdit(default_dir, self)
        browse = QPushButton("选择文件夹…", self)
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        self.body_layout.addWidget(QLabel("输出文件夹", self))
        self.body_layout.addLayout(dir_row)
        self.finish("开始拆分")

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.dir_edit.text())
        if directory:
            self.dir_edit.setText(directory)

    def values(self, count: int) -> dict[str, Any]:
        ranges = []
        if self.mode.currentIndex() == 1:
            for part in re.split(r"[,，;；]+", self.ranges.text()):
                if not part.strip():
                    continue
                pages = parse_page_ranges(part, count)
                if pages:
                    ranges.append((pages[0], pages[-1]))
        every = 1 if self.mode.currentIndex() == 2 else self.every.value()
        return {"every": every, "ranges": ranges, "output_dir": self.dir_edit.text()}


class MergeDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, initial: Sequence[str] = ()) -> None:
        super().__init__(parent, "合并文档", "添加多个 PDF，调整顺序后合并为一个文件。", 650)
        self.list = QListWidget(self)
        self.list.setMinimumHeight(220)
        for path in initial:
            self._add(path)
        self.body_layout.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("添加 PDF…", self)
        add.clicked.connect(self._browse)
        remove = QPushButton("移除", self)
        remove.clicked.connect(self._remove)
        up = QPushButton("上移", self)
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("下移", self)
        down.clicked.connect(lambda: self._move(1))
        for button in (add, remove, up, down):
            row.addWidget(button)
        row.addStretch(1)
        self.body_layout.addLayout(row)
        self.finish("合并并保存")

    def _add(self, path: str) -> None:
        item = QListWidgetItem(f"{os.path.basename(path)}    {path}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.list.addItem(item)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", "", "PDF 文件 (*.pdf)")
        for path in paths:
            self._add(path)

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        target = max(0, min(self.list.count() - 1, row + delta))
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def paths(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]


class InsertPagesDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "插入 PDF 页面", "选择要插入的 PDF 与页码范围，可指定插入位置。", 540)
        row = QHBoxLayout()
        self.path = QLineEdit(self)
        self.path.setPlaceholderText("选择 PDF 文件")
        browse = QPushButton("浏览…", self)
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.body_layout.addWidget(QLabel("源 PDF", self))
        self.body_layout.addLayout(row)
        form = QFormLayout()
        self.ranges = QLineEdit(self)
        self.ranges.setPlaceholderText("留空表示全部页面，例如：1-3, 5")
        form.addRow("源页码", self.ranges)
        self.position = QSpinBox(self)
        self.position.setRange(1, count + 1)
        self.position.setValue(current + 1)
        self.position.setPrefix("插入到第 ")
        self.position.setSuffix(" 页之前")
        form.addRow("插入位置", self.position)
        self.body_layout.addLayout(form)
        self.finish("插入页面")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF 文件 (*.pdf)")
        if path:
            self.path.setText(path)

    def accept(self) -> None:
        if not os.path.exists(self.path.text()):
            QMessageBox.warning(self, "插入页面", "请选择有效的 PDF 文件。")
            return
        super().accept()


class MovePageDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "移动页面", "将当前页面移动到指定位置。", 420)
        form = QFormLayout()
        self.source = QSpinBox(self)
        self.source.setRange(1, count)
        self.source.setValue(current + 1)
        form.addRow("源页面", self.source)
        self.target = QSpinBox(self)
        self.target.setRange(1, count)
        self.target.setValue(min(count, current + 2))
        form.addRow("移动到第", self.target)
        self.body_layout.addLayout(form)
        self.finish("移动")

    def values(self) -> tuple[int, int]:
        return self.source.value() - 1, self.target.value() - 1


# ------------------------------------------------------------------------ forms
class FormFillDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, widgets: Sequence[WidgetInfo]) -> None:
        super().__init__(parent, "填写表单", f"检测到 {len(widgets)} 个表单字段，填写后点击保存。", 560)
        self.widgets = list(widgets)
        self.inputs: dict[int, QWidget] = {}
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(360)
        content = QWidget(scroll)
        form = QFormLayout(content)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        for widget in self.widgets:
            label = QLabel(f"{widget.name}", content)
            label.setToolTip(f"第 {widget.page + 1} 页 · {widget.field_type}")
            if widget.field_type == "CheckBox":
                editor = QCheckBox("已勾选", content)
                editor.setChecked(bool(widget.value))
            elif widget.field_type == "ComboBox":
                editor = QComboBox(content)
                editor.addItems(widget.options or [str(widget.value or "")])
                if widget.value:
                    editor.setCurrentText(str(widget.value))
            elif widget.field_type == "Signature":
                editor = QPushButton("使用已保存签名", content)
                editor.setProperty("signature", True)
            else:
                editor = QLineEdit(content)
                editor.setText("" if widget.value is None else str(widget.value))
            editor.setToolTip(f"第 {widget.page + 1} 页")
            self.inputs[widget.xref] = editor
            form.addRow(label, editor)
        form.addRow(QLabel(""))
        scroll.setWidget(content)
        self.body_layout.addWidget(scroll)
        self.finish("保存表单")

    def values(self) -> dict[int, Any]:
        result: dict[int, Any] = {}
        for widget in self.widgets:
            editor = self.inputs.get(widget.xref)
            if editor is None:
                continue
            if isinstance(editor, QCheckBox):
                result[widget.xref] = editor.isChecked()
            elif isinstance(editor, QComboBox):
                result[widget.xref] = editor.currentText()
            elif isinstance(editor, QPushButton):
                result[widget.xref] = "__SIGN__"
            elif isinstance(editor, QLineEdit):
                result[widget.xref] = editor.text()
        return result


class FormFieldDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, kind: str) -> None:
        names = {
            "text": "文本域", "checkbox": "复选框", "radio": "单选按钮",
            "dropdown": "下拉列表", "signature": "签名域",
        }
        super().__init__(parent, f"添加{names.get(kind, '表单控件')}", "控件会写入 PDF，可供其他阅读器填写。", 460)
        self.kind = kind
        form = QFormLayout()
        self.name = QLineEdit(self)
        self.name.setText(f"field_{kind}")
        form.addRow("字段名称", self.name)
        self.value = QLineEdit(self)
        form.addRow("默认值", self.value)
        self.options = QLineEdit(self)
        self.options.setPlaceholderText("选项之间用逗号分隔")
        if kind == "dropdown":
            self.options.setText("选项一, 选项二, 选项三")
            form.addRow("选项", self.options)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(6, 40)
        self.size.setValue(10)
        self.size.setSuffix(" pt")
        form.addRow("字号", self.size)
        self.body_layout.addLayout(form)
        self.finish("添加控件")

    def values(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name.text().strip() or f"field_{self.kind}",
            "value": self.value.text(),
            "options": [o.strip() for o in re.split(r"[,，]", self.options.text()) if o.strip()],
            "size": self.size.value(),
        }


# ---------------------------------------------------------------------- metadata
class MetadataDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, metadata: dict[str, str]) -> None:
        super().__init__(parent, "文档属性", "修改 PDF 的标题、作者、主题和关键词等信息。", 540)
        form = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        labels = [
            ("title", "标题"), ("author", "作者"), ("subject", "主题"),
            ("keywords", "关键词"), ("creator", "创建程序"), ("producer", "生成器"),
        ]
        for key, label in labels:
            edit = QLineEdit(metadata.get(key, ""), self)
            self.fields[key] = edit
            form.addRow(label, edit)
        self.body_layout.addLayout(form)
        info = QLabel("创建时间 / 修改时间由 PDF 引擎维护。", self)
        info.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.5pt;")
        self.body_layout.addWidget(info)
        self.finish("保存属性")

    def values(self) -> dict[str, str]:
        return {k: v.text() for k, v in self.fields.items()}


class PropertiesDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        metadata: dict[str, str],
        *,
        page_count: int,
        file_size: str,
        fonts: Sequence[str],
        encrypted: bool,
        permissions: int,
    ) -> None:
        super().__init__(parent, "文档属性", "查看 PDF 的常规信息、字体与安全状态。", 580)
        tabs = QTabWidget(self)
        general = QWidget(self)
        form = QFormLayout(general)
        rows = [
            ("文件名", os.path.basename(metadata.get("_path", "")) or "—"),
            ("页数", str(page_count)),
            ("文件大小", file_size),
            ("标题", metadata.get("title", "") or "—"),
            ("作者", metadata.get("author", "") or "—"),
            ("主题", metadata.get("subject", "") or "—"),
            ("关键词", metadata.get("keywords", "") or "—"),
            ("创建程序", metadata.get("creator", "") or "—"),
            ("生成器", metadata.get("producer", "") or "—"),
            ("创建时间", metadata.get("creationDate", "") or "—"),
            ("修改时间", metadata.get("modDate", "") or "—"),
        ]
        for label, value in rows:
            edit = QLineEdit(str(value), general)
            edit.setReadOnly(True)
            form.addRow(label, edit)
        tabs.addTab(general, "常规")
        font_widget = QWidget(self)
        font_layout = QVBoxLayout(font_widget)
        font_list = QListWidget(font_widget)
        font_list.addItems(list(fonts) or ["（未检测到嵌入字体）"])
        font_layout.addWidget(font_list)
        tabs.addTab(font_widget, "字体")
        security = QWidget(self)
        sec_layout = QFormLayout(security)
        sec_layout.addRow("加密状态", QLineEdit("已加密" if encrypted else "未加密", security))
        labels = {
            0x0004: "打印", 0x0800: "高质量打印", 0x0008: "修改", 0x0010: "复制",
            0x0020: "批注", 0x0100: "填写表单", 0x0200: "提取", 0x0400: "拼合",
        }
        enabled = [label for bit, label in labels.items() if permissions & bit]
        edit = QLineEdit("、".join(enabled) or "无限制", security)
        edit.setReadOnly(True)
        sec_layout.addRow("允许的操作", edit)
        tabs.addTab(security, "安全")
        self.body_layout.addWidget(tabs)
        self.footer.addStretch(1)
        close = QPushButton("关闭", self)
        close.clicked.connect(self.accept)
        self.footer.addWidget(close)


# -------------------------------------------------------------------------- OCR
class OcrDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int, default_dpi: int = 200) -> None:
        super().__init__(
            parent,
            "OCR 文字识别",
            "本地识别扫描件中的中文与英文，可生成可搜索 PDF 或导出文字。",
            540,
        )
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("识别范围", self))
        self.body_layout.addWidget(self.scope)
        form = QFormLayout()
        self.dpi = QSpinBox(self)
        self.dpi.setRange(120, 400)
        self.dpi.setSingleStep(20)
        self.dpi.setValue(default_dpi)
        self.dpi.setSuffix(" DPI")
        form.addRow("渲染精度", self.dpi)
        self.output = QComboBox(self)
        self.output.addItems(["可搜索 PDF（另存为）", "仅导出为文本", "在 PDF 中添加隐藏文字层"])
        form.addRow("输出方式", self.output)
        self.body_layout.addLayout(form)
        note = QLabel("首次识别需要加载本地模型，可能需要数秒。所有计算均在本机完成。", self)
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.5pt;")
        self.body_layout.addWidget(note)
        self.finish("开始识别")

    def values(self, count: int) -> dict[str, Any]:
        return {
            "pages": self.scope.pages(count),
            "dpi": self.dpi.value(),
            "output": self.output.currentIndex(),
        }


# -------------------------------------------------------------------- conversion
class ConvertOptionsDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, target: str, count: int, current: int) -> None:
        labels = {
            "word": "PDF 转 Word", "excel": "PDF 转 Excel", "ppt": "PDF 转 PPT",
            "image": "PDF 转图片", "text": "PDF 转文本", "html": "PDF 转 HTML",
        }
        super().__init__(parent, labels.get(target, "转换"), "选择转换范围与输出选项。", 500)
        self.target = target
        self.scope = PageScopeWidget(count, self)
        self.scope.set_current(current)
        self.body_layout.addWidget(QLabel("转换范围", self))
        self.body_layout.addWidget(self.scope)
        self.dpi = QSpinBox(self)
        self.dpi.setRange(72, 600)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" DPI")
        self.fmt = QComboBox(self)
        self.fmt.addItems(["PNG", "JPG", "WEBP"])
        self.keep_breaks = QCheckBox("保留分页", self)
        self.keep_breaks.setChecked(True)
        form = QFormLayout()
        if target == "image":
            form.addRow("图片格式", self.fmt)
            form.addRow("分辨率", self.dpi)
        elif target == "ppt":
            form.addRow("页面渲染精度", self.dpi)
        elif target == "word":
            form.addRow("", self.keep_breaks)
        self.body_layout.addLayout(form)
        self.finish("开始转换")

    def values(self, count: int) -> dict[str, Any]:
        return {
            "pages": self.scope.pages(count),
            "dpi": self.dpi.value(),
            "fmt": self.fmt.currentText().lower(),
            "keep_breaks": self.keep_breaks.isChecked(),
        }


class ImageToPdfDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, images: Sequence[str]) -> None:
        super().__init__(parent, "图片转 PDF", f"将 {len(images)} 张图片按顺序生成 PDF。", 560)
        self.list = QListWidget(self)
        self.list.setMinimumHeight(220)
        for path in images:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
        self.body_layout.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("添加图片…", self)
        add.clicked.connect(self._browse)
        remove = QPushButton("移除", self)
        remove.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        up = QPushButton("上移", self)
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("下移", self)
        down.clicked.connect(lambda: self._move(1))
        for button in (add, remove, up, down):
            row.addWidget(button)
        row.addStretch(1)
        self.body_layout.addLayout(row)
        form = QFormLayout()
        self.mode = QComboBox(self)
        self.mode.addItems(["保持图片尺寸", "适配 A4 页面"])
        form.addRow("页面设置", self.mode)
        self.body_layout.addLayout(form)
        self.finish("生成 PDF")

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", SUPPORTED_IMAGES)
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        target = max(0, min(self.list.count() - 1, row + delta))
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def values(self) -> dict[str, Any]:
        return {
            "images": [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())],
            "mode": "a4" if self.mode.currentIndex() == 1 else "fit",
        }


# --------------------------------------------------------------------------- AI
class AIDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, text: str, selected: str = "") -> None:
        super().__init__(
            parent,
            "星澜智能助手",
            "本地分析当前文档：摘要、问答、关键词均不会上传文件。",
            760,
        )
        self.document_text = text
        self.selected_text = selected
        top = QHBoxLayout()
        self.btn_summary = QPushButton("生成摘要", self)
        self.btn_outline = QPushButton("结构大纲", self)
        self.btn_keywords = QPushButton("关键词", self)
        self.btn_translate = QPushButton("翻译说明", self)
        for button in (self.btn_summary, self.btn_outline, self.btn_keywords, self.btn_translate):
            button.setObjectName("Primary" if button is self.btn_summary else "")
            top.addWidget(button)
        top.addStretch(1)
        self.body_layout.addLayout(top)
        self.output = QTextBrowser(self)
        self.output.setMinimumHeight(330)
        self.output.setStyleSheet(
            "QTextBrowser { background:#FBFCFE; border:1px solid #E3E7EE; border-radius:8px;"
            "padding:14px; font-size:10pt; line-height:1.5; }"
        )
        self.output.setHtml(
            "<div style='color:#6E778B'>点击上方按钮生成结果，或在下方输入问题。</div>"
        )
        self.body_layout.addWidget(self.output)
        bottom = QHBoxLayout()
        self.question = QLineEdit(self)
        self.question.setPlaceholderText("针对全文提问，例如：这份文档的核心结论是什么？")
        self.question.returnPressed.connect(self._ask)
        ask = QPushButton("提问", self)
        ask.setObjectName("Primary")
        ask.clicked.connect(self._ask)
        bottom.addWidget(self.question, 1)
        bottom.addWidget(ask)
        self.body_layout.addLayout(bottom)
        self.btn_summary.clicked.connect(self._summary)
        self.btn_outline.clicked.connect(self._outline)
        self.btn_keywords.clicked.connect(self._keywords)
        self.btn_translate.clicked.connect(self._translate)
        self.footer.addStretch(1)
        close = QPushButton("关闭", self)
        close.clicked.connect(self.accept)
        self.footer.addWidget(close)

    def _set_text(self, text: str) -> None:
        html_text = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>").replace("•", "&#8226;")
        )
        self.output.setHtml(f"<div style='line-height:1.65'>{html_text}</div>")

    def _summary(self) -> None:
        from ..core.ai import summarize

        self._set_text(summarize(self.document_text, 7))

    def _outline(self) -> None:
        from ..core.ai import build_outline

        self._set_text(build_outline(self.document_text))

    def _keywords(self) -> None:
        from ..core.ai import keywords

        words = keywords(self.document_text, 18)
        if not words:
            self._set_text("没有提取到关键词。")
            return
        text = "关键词\n\n" + "\n".join(f"• {word}（出现 {count} 次）" for word, count in words)
        self._set_text(text)

    def _translate(self) -> None:
        from ..core.ai import translation_notice

        self._set_text(translation_notice())

    def _ask(self) -> None:
        question = self.question.text().strip()
        if not question:
            return
        from ..core.ai import answer_question

        answer = answer_question(self.document_text, question, 4)
        self._set_text(answer.text)
        self.question.clear()


# -------------------------------------------------------------------- progress
class TaskProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, subtitle: str = "正在处理，请稍候…") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFixedWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        label = QLabel(title, self)
        label.setStyleSheet("font-size:13pt; font-weight:600;")
        layout.addWidget(label)
        self.subtitle = QLabel(subtitle, self)
        self.subtitle.setStyleSheet(f"color:{C.TEXT_MUTED};")
        layout.addWidget(self.subtitle)
        from PySide6.QtWidgets import QProgressBar

        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        layout.addWidget(self.bar)
        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def set_progress(self, value: int, message: str = "") -> None:
        self.bar.setValue(max(0, min(100, value)))
        if message:
            self.subtitle.setText(message)


# ---------------------------------------------------------------------- compare
class CompareDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, current_path: str) -> None:
        super().__init__(parent, "比较文档", "选择另一份 PDF，与当前文档进行文本差异比较。", 600)
        row = QHBoxLayout()
        self.path = QLineEdit(self)
        self.path.setPlaceholderText("选择要比较的 PDF")
        browse = QPushButton("浏览…", self)
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.body_layout.addLayout(row)
        self.result = QTextBrowser(self)
        self.result.setMinimumHeight(300)
        self.body_layout.addWidget(self.result)
        self.finish("开始比较")
        self.current_path = current_path

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF 文件 (*.pdf)")
        if path:
            self.path.setText(path)


# --------------------------------------------------------------------- shortcuts
class ShortcutsDialog(BaseDialog):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, "快捷键与帮助", "常用操作的键盘快捷键。", 520)
        rows = [
            ("打开 PDF", "Ctrl + O"), ("保存", "Ctrl + S"), ("另存为", "Ctrl + Shift + S"),
            ("打印", "Ctrl + P"), ("撤销 / 重做", "Ctrl + Z / Ctrl + Y"),
            ("查找", "Ctrl + F"), ("复制选中文字", "Ctrl + C"), ("全选文本", "Ctrl + A"),
            ("放大 / 缩小", "Ctrl + + / Ctrl + -"), ("适合页面", "Ctrl + 0"),
            ("上一页 / 下一页", "PageUp / PageDown"), ("关闭文档", "Ctrl + W"),
            ("全屏", "F11"), ("退出全屏", "Esc"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(8)
        for i, (name, key) in enumerate(rows):
            grid.addWidget(QLabel(name, self), i, 0)
            key_label = QLabel(key, self)
            key_label.setStyleSheet(
                "background:#F1F4F9; border:1px solid #E0E5EE; border-radius:4px;"
                "padding:3px 8px; color:#4C5465; font-family:Consolas;"
            )
            grid.addWidget(key_label, i, 1)
        self.body_layout.addLayout(grid)
        self.finish("知道了")


class AboutDialog(BaseDialog):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, f"关于 {APP_NAME}", "", 480)
        logo = QLabel(self)
        logo.setPixmap(app_icon().pixmap(72, 72))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(logo)
        title = QLabel(APP_NAME, self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:19pt; font-weight:700; color:#202635;")
        self.body_layout.addWidget(title)
        version = QLabel(f"版本 {APP_VERSION} · 本地离线 PDF 编辑器", self)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self.body_layout.addWidget(version)
        description = QLabel(
            "星澜 PDF 是一款原创的本地 PDF 编辑工具。界面布局参考了主流办公软件的"
            "操作习惯，但品牌、图标与视觉设计均为独立设计，不包含任何第三方商标素材。\n\n"
            "文件处理全部在本机完成，不会上传到服务器。开源组件包括 PyMuPDF、Qt for Python、"
            "python-docx、openpyxl、python-pptx、ReportLab、RapidOCR 与 Lucide 图标。",
            self,
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignLeft)
        description.setStyleSheet("color:#4E5667; line-height:1.55;")
        self.body_layout.addWidget(description)
        self.finish("关闭")


class TextResultDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, text: str, width: int = 680) -> None:
        super().__init__(parent, title, "", width)
        browser = QTextBrowser(self)
        browser.setMinimumHeight(420)
        browser.setPlainText(text)
        self.body_layout.addWidget(browser)
        self.finish("关闭")


# ------------------------------------------------------------------------- more
class LinkDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "添加链接", "为框选区域添加网址链接或跳转到文档内页面。", 480)
        self.mode = QComboBox(self)
        self.mode.addItems(["打开网址", "跳转到页面"])
        self.body_layout.addWidget(self.mode)
        self.url = QLineEdit(self)
        self.url.setPlaceholderText("https://example.com")
        self.body_layout.addWidget(QLabel("网址", self))
        self.body_layout.addWidget(self.url)
        self.page = QSpinBox(self)
        self.page.setRange(1, count)
        self.page.setValue(current + 1)
        self.body_layout.addWidget(QLabel("目标页面", self))
        self.body_layout.addWidget(self.page)
        self.mode.currentIndexChanged.connect(
            lambda index: (self.url.setEnabled(index == 0), self.page.setEnabled(index == 1))
        )
        self.page.setEnabled(False)
        self.finish("添加链接")

    def values(self) -> dict[str, Any]:
        if self.mode.currentIndex() == 0:
            return {"uri": self.url.text().strip(), "page": None}
        return {"uri": None, "page": self.page.value() - 1}


class BookmarkDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(parent, "添加书签", "书签会显示在左侧导航栏，便于快速跳转。", 440)
        form = QFormLayout()
        self.title = QLineEdit(self)
        self.title.setPlaceholderText("书签名称")
        form.addRow("名称", self.title)
        self.page = QSpinBox(self)
        self.page.setRange(1, count)
        self.page.setValue(current + 1)
        form.addRow("页码", self.page)
        self.body_layout.addLayout(form)
        self.finish("添加书签")
        self.title.setFocus()

    def accept(self) -> None:
        if not self.title.text().strip():
            QMessageBox.information(self, "添加书签", "请输入书签名称。")
            return
        super().accept()

    def values(self) -> dict[str, Any]:
        return {"title": self.title.text().strip(), "page": self.page.value() - 1}


class BlankPageDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int, current_size: tuple[float, float]) -> None:
        super().__init__(parent, "插入空白页", "选择纸张尺寸与插入位置。", 480)
        form = QFormLayout()
        self.count = QSpinBox(self)
        self.count.setRange(1, 50)
        self.count.setValue(1)
        form.addRow("页数", self.count)
        self.preset = QComboBox(self)
        self.preset.addItems(["A4", "A3", "A5", "Letter", "与当前页相同", "自定义"])
        self.preset.setCurrentIndex(4)
        form.addRow("纸张", self.preset)
        self.width = QDoubleSpinBox(self)
        self.width.setRange(50, 5000)
        self.width.setValue(current_size[0])
        self.width.setSuffix(" pt")
        form.addRow("宽度", self.width)
        self.height = QDoubleSpinBox(self)
        self.height.setRange(50, 5000)
        self.height.setValue(current_size[1])
        self.height.setSuffix(" pt")
        form.addRow("高度", self.height)
        self.position = QSpinBox(self)
        self.position.setRange(1, count + 1)
        self.position.setValue(current + 2 if current + 2 <= count + 1 else count + 1)
        self.position.setPrefix("插入到第 ")
        self.position.setSuffix(" 页之前")
        form.addRow("位置", self.position)
        self.body_layout.addLayout(form)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.finish("插入")

    def _preset_changed(self, index: int) -> None:
        sizes = {"A4": (595, 842), "A3": (842, 1191), "A5": (420, 595), "Letter": (612, 792)}
        if index < 4:
            w, h = sizes[self.preset.currentText()]
            self.width.setValue(w)
            self.height.setValue(h)

    def values(self) -> dict[str, Any]:
        return {
            "count": self.count.value(),
            "width": self.width.value(),
            "height": self.height.value(),
            "position": self.position.value() - 1,
        }


class ReplaceDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, count: int, current: int) -> None:
        super().__init__(
            parent,
            "查找与替换",
            "替换会永久移除原文字并写入新内容。建议先保存文档。",
            520,
        )
        form = QFormLayout()
        self.find = QLineEdit(self)
        self.find.setPlaceholderText("要查找的文字")
        form.addRow("查找", self.find)
        self.replace = QLineEdit(self)
        self.replace.setPlaceholderText("替换为")
        form.addRow("替换为", self.replace)
        self.scope = QComboBox(self)
        self.scope.addItems(["当前页", "全部页面"])
        form.addRow("范围", self.scope)
        self.color = ColorButton("#1F2430", self)
        form.addRow("文字颜色", self.color)
        self.body_layout.addLayout(form)
        note = QLabel("提示：若替换后文字宽度变化，可能影响排版。可使用撤销恢复。", self)
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8.5pt;")
        self.body_layout.addWidget(note)
        self.finish("全部替换")
        self.find.setFocus()
        self.current_page = current
        self.count = count

    def values(self) -> dict[str, Any]:
        return {
            "find": self.find.text(),
            "replace": self.replace.text(),
            "pages": None if self.scope.currentIndex() == 1 else [self.current_page],
            "color": self.color.value(),
        }


class BatchConvertDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, default_dir: str = "") -> None:
        super().__init__(parent, "批量转换", "选择多个 PDF，统一转换为 Word、图片或文本。", 640)
        self.list = QListWidget(self)
        self.list.setMinimumHeight(210)
        self.body_layout.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("添加 PDF…", self)
        add.clicked.connect(self._browse)
        remove = QPushButton("移除", self)
        remove.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        for button in (add, remove):
            row.addWidget(button)
        row.addStretch(1)
        self.body_layout.addLayout(row)
        form = QFormLayout()
        self.target = QComboBox(self)
        self.target.addItems(["PDF 转 Word", "PDF 转图片", "PDF 转文本", "PDF 转 Excel", "压缩 PDF"])
        form.addRow("转换类型", self.target)
        self.output = QLineEdit(default_dir, self)
        browse = QPushButton("选择输出文件夹…", self)
        browse.clicked.connect(self._browse_output)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output, 1)
        out_row.addWidget(browse)
        form.addRow("输出文件夹", out_row)
        self.dpi = QSpinBox(self)
        self.dpi.setRange(72, 400)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" DPI")
        form.addRow("图片精度", self.dpi)
        self.body_layout.addLayout(form)
        self.finish("开始批量转换")

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", "", "PDF 文件 (*.pdf)")
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)

    def _browse_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.output.text())
        if directory:
            self.output.setText(directory)

    def paths(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def values(self) -> dict[str, Any]:
        return {
            "target": self.target.currentIndex(),
            "output": self.output.text(),
            "dpi": self.dpi.value(),
        }
