"""Reusable UI primitives for the WPS-inspired ribbon interface."""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap

from ..config import ui_font_family
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon, pixmap
from ..theme import C


class ToolButton(QToolButton):
    def __init__(
        self,
        icon_name: str,
        text: str = "",
        *,
        color: str = C.TEXT_SUB,
        size: int = 18,
        checkable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._color = color
        self._icon_size = size
        self.setIcon(icon(icon_name, color, size))
        self.setIconSize(QSize(size, size))
        if text:
            self.setText(text)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_icon(self, name: str, color: str | None = None, size: int | None = None) -> None:
        self._icon_name = name
        if color:
            self._color = color
        if size:
            self._icon_size = size
        self.setIcon(icon(self._icon_name, self._color, self._icon_size))
        self.setIconSize(QSize(self._icon_size, self._icon_size))


class RibbonButton(ToolButton):
    """A large (icon over text) or compact (icon beside text) ribbon command."""

    command = Signal(str)

    def __init__(
        self,
        action: str,
        icon_name: str,
        text: str,
        *,
        large: bool = True,
        color: str = C.TEXT_SUB,
        tooltip: str = "",
        checkable: bool = False,
        menu: QMenu | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            icon_name,
            text,
            color=color,
            size=27 if large else 16,
            checkable=checkable,
            parent=parent,
        )
        self.action = action
        self.large = large
        self.setObjectName("RibbonLarge" if large else "RibbonSmall")
        measure = QFontMetrics(QFont(ui_font_family(), 9))
        if large:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            width = max(78, min(134, measure.horizontalAdvance(text) + 22))
            self.setFixedSize(width, 66)
            self.setIconSize(QSize(27, 27))
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setFixedHeight(26)
            self.setMinimumWidth(max(82, min(180, measure.horizontalAdvance(text) + 50)))
            self.setIconSize(QSize(16, 16))
        if tooltip:
            self.setToolTip(tooltip)
        elif text:
            self.setToolTip(text)
        if menu:
            self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        if self.menu() and self.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup:
            return
        self.command.emit(self.action)


class RibbonGroup(QWidget):
    def __init__(
        self,
        title: str,
        *,
        large: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.large = large
        self.setObjectName("RibbonGroup")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(6, 3, 6, 2)
        self._outer.setSpacing(1)
        self.body = QWidget(self)
        if large:
            self._body_layout: QHBoxLayout | QVBoxLayout = QHBoxLayout(self.body)
        else:
            self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(1)
        self._outer.addWidget(self.body, 1)
        self.label = QLabel(title, self)
        self.label.setObjectName("GroupLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self._outer.addWidget(self.label, 0)

    def add_button(self, button: RibbonButton) -> RibbonButton:
        self._body_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        return button

    def add_row(self, buttons: Iterable[RibbonButton]) -> QWidget:
        row = QWidget(self.body)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        for button in buttons:
            layout.addWidget(button)
        layout.addStretch(0)
        if isinstance(self._body_layout, QVBoxLayout):
            self._body_layout.addWidget(row)
        else:
            self._body_layout.addWidget(row)
        return row

    def add_widget(self, widget: QWidget) -> QWidget:
        self._body_layout.addWidget(widget)
        return widget


class VerticalSeparator(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonSeparator")
        self.setFixedWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(20)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full = text
        super().setText(text)
        self._elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(20, self.width() - 4)))


class Toast(QWidget):
    """Small non-blocking notification hovering above the status bar."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._label = QLabel(self)
        self._label.setStyleSheet(
            "background: rgba(35,40,51,235); color: white; border-radius: 8px;"
            "padding: 9px 18px; font-size: 9.5pt;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, msec: int = 2600) -> None:
        self._label.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 52
            self.move(max(8, x), max(8, y))
        self.show()
        self.raise_()
        self._timer.start(msec)


class ShadowCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class Avatar(QWidget):
    def __init__(self, initials: str = "星", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.initials = initials
        self.setFixedSize(28, 28)
        self.setToolTip("本地账户 · 文件不会上传")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QColor(C.PRIMARY)
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())
        painter.setPen(QColor("white"))
        font = QFont("Microsoft YaHei UI", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initials)


class BusyOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self) -> None:
        self._timer.start(16)
        self.show()
        self.raise_()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 18))
        center = self.rect().center()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawEllipse(center, 34, 34)
        pen = painter.pen()
        pen.setColor(QColor(C.PRIMARY))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRect(center.x() - 14, center.y() - 14, 28, 28), self._angle * 16, 120 * 16)
