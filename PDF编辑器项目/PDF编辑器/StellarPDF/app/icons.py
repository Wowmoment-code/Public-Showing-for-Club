"""SVG icon loading with recolouring and DPI aware pixmaps."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .config import asset_path
from .theme import C

_ICON_DIR = asset_path("icons", "lucide")
_cache: dict[tuple[str, str, int], QIcon] = {}
_pix_cache: dict[tuple[str, str, int, int], QPixmap] = {}

# Friendly aliases used by the ribbon.
ALIASES = {
    "open": "folder-open",
    "save": "save",
    "save-as": "save-all",
    "print": "printer",
    "undo": "undo-2",
    "redo": "redo-2",
    "select": "mouse-pointer-2",
    "hand": "hand",
    "text": "type",
    "text-box": "text-cursor-input",
    "image": "image",
    "images": "images",
    "shape": "shapes",
    "rect": "square",
    "ellipse": "circle",
    "arrow": "move-up-right",
    "line": "minus",
    "link": "link",
    "watermark": "droplets",
    "background": "paint-bucket",
    "header": "panel-top",
    "footer": "panel-bottom",
    "page-number": "hash",
    "properties": "settings-2",
    "insert-page": "file-plus-2",
    "delete-page": "trash-2",
    "extract": "file-output",
    "split": "scissors",
    "merge": "combine",
    "rotate-left": "rotate-ccw",
    "rotate-right": "rotate-cw",
    "crop": "crop",
    "page-size": "file-stack",
    "replace": "replace",
    "duplicate": "copy-plus",
    "move": "move",
    "export": "download",
    "highlight": "highlighter",
    "underline": "underline",
    "strike": "strikethrough",
    "squiggly": "waves",
    "note": "message-square-text",
    "sticky": "sticky-note",
    "ink": "pen-line",
    "stamp": "stamp",
    "signature": "signature",
    "area-highlight": "scan",
    "manage-annot": "list-checks",
    "compress": "archive",
    "ocr": "scan-text",
    "compare": "git-compare-arrows",
    "search": "search",
    "bookmark": "bookmark",
    "attachment": "paperclip",
    "measure": "ruler",
    "screenshot": "camera",
    "form": "list-checks",
    "fill": "pencil-line",
    "checkbox": "square-check-big",
    "radio": "circle-dot",
    "dropdown": "chevrons-up-down",
    "date": "calendar-days",
    "encrypt": "lock-keyhole",
    "permissions": "shield-check",
    "redact": "square-dashed",
    "certificate": "badge-check",
    "metadata": "info",
    "security": "shield",
    "pdf-word": "file-text",
    "pdf-excel": "file-spreadsheet",
    "pdf-ppt": "presentation",
    "pdf-image": "file-image",
    "pdf-txt": "file-type-2",
    "pdf-html": "file-code-2",
    "to-pdf": "file-input",
    "ai": "sparkles",
    "summary": "align-left",
    "qa": "messages-square",
    "keywords": "tags",
    "translate": "languages",
    "proofread": "spell-check-2",
    "zoom-in": "zoom-in",
    "zoom-out": "zoom-out",
    "fit-width": "move-horizontal",
    "fit-page": "maximize-2",
    "fullscreen": "expand",
    "single": "square",
    "continuous": "rows-3",
    "double": "columns-2",
    "book": "book-open",
    "night": "moon",
    "more": "ellipsis",
    "close": "x",
    "minimize": "minus",
    "maximize": "square",
    "restore": "minimize-2",
    "chevron-down": "chevron-down",
    "chevron-right": "chevron-right",
    "folder": "folder",
    "file-pdf": "file-text",
    "info": "info",
    "help": "circle-help",
    "new": "file-plus",
    "home": "house",
    "recent": "history",
    "thumbnails": "layout-grid",
    "annots": "message-square-text",
    "attachments": "paperclip",
    "forms": "text-cursor-input",
    "outline": "list-tree",
    "star": "star",
    "user": "user-round",
    "check": "check",
    "plus": "plus",
    "back": "arrow-left",
    "forward": "arrow-right",
    "page": "file",
    "eye": "eye",
    "download": "download",
    "upload": "upload",
    "eraser": "eraser",
    "rotate": "rotate-cw",
}


def _svg_text(name: str) -> str | None:
    name = ALIASES.get(name, name)
    path: Path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        path = _ICON_DIR / "file-text.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def colored_svg(name: str, color: str) -> bytes:
    svg = _svg_text(name) or ""
    svg = svg.replace("currentColor", color)
    svg = svg.replace('stroke="black"', f'stroke="{color}"')
    svg = svg.replace('fill="black"', f'fill="{color}"')
    if "stroke=" not in svg:
        svg = svg.replace("<svg ", f'<svg stroke="{color}" ', 1)
    return svg.encode("utf-8")


def icon(name: str, color: str = C.TEXT_SUB, size: int = 18) -> QIcon:
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    renderer = QSvgRenderer(QByteArray(colored_svg(name, color)))
    dpr = 2
    pix = QPixmap(size * dpr, size * dpr)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pix.setDevicePixelRatio(dpr)
    qicon = QIcon(pix)
    _cache[key] = qicon
    return qicon


def pixmap(name: str, color: str = C.TEXT_SUB, size: int = 18, dpr: int = 2) -> QPixmap:
    key = (name, color, size, dpr)
    if key in _pix_cache:
        return _pix_cache[key]
    renderer = QSvgRenderer(QByteArray(colored_svg(name, color)))
    pix = QPixmap(size * dpr, size * dpr)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pix.setDevicePixelRatio(dpr)
    _pix_cache[key] = pix
    return pix


def app_icon() -> QIcon:
    path = asset_path("logo.svg")
    renderer = QSvgRenderer(str(path))
    icon_obj = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon_obj.addPixmap(QPixmap.fromImage(image))
    return icon_obj


def svg_data(name: str, color: str) -> bytes:
    return colored_svg(name, color)
