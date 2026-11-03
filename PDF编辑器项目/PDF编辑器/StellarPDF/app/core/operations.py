"""Editing operations on a :class:`PdfDocument`.

Every public operation checkpoints the document first, so the UI only has to
call the operation and refresh.  Coordinates are PDF points and always refer to
the un-rotated page coordinate system used by PyMuPDF.
"""
from __future__ import annotations

import io
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from ..config import cjk_font_file, pdf_font_family_and_file
from .document import PdfDocument, TextBlock, TextSpan


Color = tuple[float, float, float]


# --------------------------------------------------------------------- helpers
def _page(doc: PdfDocument, index: int) -> pymupdf.Page:
    d = doc.require_doc()
    if not (0 <= index < len(d)):
        raise ValueError("页码超出范围")
    return d[index]


def _font(bold: bool = False) -> tuple[str, str | None]:
    path = cjk_font_file()
    return ("STLXB" if bold else "STLX", path)


def _clean_color(color: Sequence[float] | str | None) -> Color:
    if color is None:
        return (0.1, 0.1, 0.1)
    if isinstance(color, str):
        value = color.lstrip("#")
        if len(value) == 6:
            return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        return (0.1, 0.1, 0.1)
    if len(color) == 3:
        return tuple(float(max(0, min(1, c))) for c in color)
    return (0.1, 0.1, 0.1)


def _fit_font_size(text: str, rect: pymupdf.Rect, default: float = 11) -> float:
    if not text.strip() or rect.width <= 0:
        return default
    # Rough estimate; CJK glyphs are close to 1 em wide, Latin around 0.55 em.
    width_units = sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in text)
    if width_units <= 0:
        return default
    return max(5, min(72, rect.width / width_units))


def _insert_cjk_text(
    page: pymupdf.Page,
    point: tuple[float, float] | pymupdf.Point,
    text: str,
    size: float,
    color: Color,
    *,
    bold: bool = False,
    opacity: float = 1.0,
    rotate: int = 0,
    render_mode: int = 0,
    overlay: bool = True,
) -> None:
    name, path = _font(bold)
    kwargs = dict(
        fontsize=float(size),
        fontname=name,
        color=color,
        fill_opacity=float(max(0.0, min(1.0, opacity))),
        rotate=int(rotate),
        render_mode=int(render_mode),
        overlay=overlay,
    )
    if path:
        kwargs["fontfile"] = path
    page.insert_text(pymupdf.Point(point), text, **kwargs)


def _insert_cjk_box(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    size: float,
    color: Color,
    *,
    align: int = 0,
    bold: bool = False,
    opacity: float = 1.0,
    rotate: int = 0,
    render_mode: int = 0,
    overlay: bool = True,
    fontname: str | None = None,
    fontfile: str | None = None,
    lineheight: float | None = None,
) -> float:
    if fontfile is None:
        name, path = _font(bold)
    else:
        name, path = (fontname or "ORIG"), fontfile
    kwargs = dict(
        fontsize=float(size),
        fontname=name,
        color=color,
        align=int(align),
        fill_opacity=float(max(0.0, min(1.0, opacity))),
        rotate=int(rotate),
        render_mode=int(render_mode),
        overlay=overlay,
    )
    if path:
        kwargs["fontfile"] = path
    if lineheight:
        kwargs["lineheight"] = float(lineheight)
    return float(page.insert_textbox(rect, text, **kwargs))


def _delete_annots(doc: PdfDocument, page: pymupdf.Page, xrefs: Iterable[int]) -> None:
    wanted = set(xrefs)
    for annot in list(page.annots() or []):
        if annot.xref in wanted:
            page.delete_annot(annot)


# ------------------------------------------------------------------------ text
def replace_text(
    doc: PdfDocument,
    span: TextSpan,
    new_text: str,
    *,
    size: float | None = None,
    color: Color | None = None,
    bold: bool | None = None,
    align: int = 0,
) -> None:
    """Replace an extracted text span, removing the old glyphs with redaction."""
    doc.checkpoint()
    page = _page(doc, span.page)
    rect = pymupdf.Rect(span.bbox)
    redact = pymupdf.Rect(rect.x0 - 0.6, rect.y0 - 0.4, rect.x1 + 0.6, rect.y1 + 0.4)
    page.add_redact_annot(redact, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    if not new_text:
        doc.mark_dirty()
        return
    use_size = float(size or span.size or 11)
    use_color = _clean_color(color if color is not None else span.color)
    use_bold = span.bold if bold is None else bold
    origin = span.origin or (rect.x0, rect.y1 - max(1.0, use_size * 0.18))
    single_line = "\n" not in new_text
    expected_width = sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in new_text) * use_size
    if single_line and expected_width <= max(rect.width * 1.6, 20):
        _insert_cjk_text(page, origin, new_text, use_size, use_color, bold=use_bold)
    else:
        target = pymupdf.Rect(rect.x0, rect.y0, max(rect.x1, rect.x0 + expected_width + 2), rect.y1)
        target.y1 = max(target.y1, rect.y0 + use_size * (new_text.count("\n") + 1.6))
        _insert_cjk_box(
            page, target, new_text, use_size, use_color, bold=use_bold, align=align
        )
    doc.mark_dirty()


def replace_text_block(
    doc: PdfDocument,
    block: TextBlock,
    new_text: str,
    *,
    size: float | None = None,
    color: Color | None = None,
    bold: bool | None = None,
    align: int | None = None,
) -> None:
    """Replace a whole paragraph while keeping its original typography.

    The page is checkpointed first, the paragraph box is removed with a
    text-only redaction, and the new text is laid out using the same font
    family/file, size, color, alignment and line spacing as the source.
    """
    doc.checkpoint()
    page = _page(doc, block.page)
    rect = pymupdf.Rect(block.bbox)
    redact = pymupdf.Rect(rect.x0 - 1.2, rect.y0 - 1.0, rect.x1 + 1.2, rect.y1 + 1.0)
    page.add_redact_annot(redact, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    if not new_text.strip():
        doc.mark_dirty()
        return
    use_size = float(size or block.size or 11)
    use_color = _clean_color(color if color is not None else block.color)
    use_bold = block.bold if bold is None else bold
    use_align = block.align if align is None else int(align)
    use_lineheight = (
        max(1.0, min(2.2, block.line_height / use_size))
        if block.line_height > 0
        else 1.3
    )
    _, font_file = pdf_font_family_and_file(
        block.font, bold=use_bold, italic=block.italic
    )
    font_name = "ORIGB" if use_bold else ("ORIGI" if block.italic else "ORIG")
    max_width = max(40.0, page.rect.width - rect.x0 - 12)
    # Keep a body paragraph's original width, but let a short heading/label
    # expand instead of wrapping into a one-character-wide column.
    short_line = block.line_count <= 1 and rect.width < page.rect.width * 0.55
    if short_line:
        widest = max(
            (sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in line)
             for line in new_text.split("\n")),
            default=1.0,
        )
        width = min(max_width, max(80.0, rect.width + 2.0, widest * use_size + 4.0))
    else:
        width = min(max_width, max(40.0, rect.width + 2.0))
    height = max(rect.height + 4.0, (new_text.count("\n") + 1) * use_size * use_lineheight + 8)
    # insert_textbox returns a negative value when the text does not fit.
    # Grow the box downwards (or upwards near the bottom edge) until it does.
    for _ in range(8):
        y0 = rect.y0
        y1 = y0 + height
        if y1 > page.rect.height - 12:
            y1 = page.rect.height - 12
            y0 = max(12, y1 - height)
        target = pymupdf.Rect(rect.x0, y0, min(page.rect.width - 12, rect.x0 + width), y1)
        rc = _insert_cjk_box(
            page,
            target,
            new_text,
            use_size,
            use_color,
            align=use_align,
            bold=use_bold,
            fontname=font_name,
            fontfile=font_file,
            lineheight=use_lineheight,
        )
        if rc >= 0:
            break
        height *= 1.3
    doc.mark_dirty()


def insert_text(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    text: str,
    *,
    size: float = 12,
    color: Color = (0.1, 0.1, 0.1),
    bold: bool = False,
    align: int = 0,
    opacity: float = 1.0,
    box: bool = False,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    if box:
        _insert_cjk_box(
            page,
            rect,
            text,
            size,
            _clean_color(color),
            align=align,
            bold=bold,
            opacity=opacity,
        )
    else:
        _insert_cjk_text(
            page,
            (rect.x0, rect.y1 - 2),
            text,
            size,
            _clean_color(color),
            bold=bold,
            opacity=opacity,
        )
    doc.mark_dirty()


def replace_all_text(
    doc: PdfDocument,
    query: str,
    replacement: str,
    *,
    pages: Sequence[int] | None = None,
    color: Color = (0.1, 0.1, 0.1),
) -> int:
    if not query:
        return 0
    doc.checkpoint()
    count = 0
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        hits = list(page.search_for(query))
        if not hits:
            continue
        sizes = []
        for rect in hits:
            page.add_redact_annot(rect, fill=None)
            sizes.append(rect)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        for rect in sizes:
            size = _fit_font_size(replacement, rect, max(7.0, rect.height * 0.82))
            _insert_cjk_text(page, (rect.x0, rect.y1 - 1.5), replacement, size, _clean_color(color))
            count += 1
    if count:
        doc.mark_dirty()
    return count


# ---------------------------------------------------------------------- images
def insert_image(doc: PdfDocument, page_index: int, rect: pymupdf.Rect, path: str) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    page.insert_image(rect, filename=path, keep_proportion=True, overlay=True)
    doc.mark_dirty()


def insert_image_bytes(
    doc: PdfDocument, page_index: int, rect: pymupdf.Rect, data: bytes
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    page.insert_image(rect, stream=data, keep_proportion=True, overlay=True)
    doc.mark_dirty()


def replace_image(doc: PdfDocument, page_index: int, xref: int, path: str) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    page.replace_image(xref, filename=path)
    doc.mark_dirty()


def delete_image(doc: PdfDocument, page_index: int, xref: int) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    rects: list[pymupdf.Rect] = []
    try:
        rects = [pymupdf.Rect(r) for r in page.get_image_rects(xref)]
    except Exception:
        rects = []
    if rects:
        for rect in rects:
            page.add_redact_annot(rect, fill=None)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )
    else:
        page.delete_image(xref)
    doc.mark_dirty()


# ---------------------------------------------------------------------- shapes
def add_shape(
    doc: PdfDocument,
    page_index: int,
    kind: str,
    rect: pymupdf.Rect,
    *,
    stroke: Color = (0.18, 0.42, 1.0),
    fill: Color | None = None,
    width: float = 1.5,
    opacity: float = 1.0,
    points: Sequence[tuple[float, float]] | None = None,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    rect = pymupdf.Rect(rect)
    if rect.width < 1 or rect.height < 1:
        rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + 1, rect.y0 + 1)
    if kind == "rect":
        annot = page.add_rect_annot(rect)
    elif kind == "ellipse":
        annot = page.add_circle_annot(rect)
    elif kind in ("line", "arrow"):
        if points and len(points) >= 2:
            p1, p2 = points[0], points[1]
        else:
            p1, p2 = (rect.x0, rect.y0), (rect.x1, rect.y1)
        annot = page.add_line_annot(pymupdf.Point(p1), pymupdf.Point(p2))
        if kind == "arrow":
            annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
    elif kind == "ink":
        strokes = [[pymupdf.Point(p) for p in points]] if points else [
            [pymupdf.Point(rect.x0, rect.y0), pymupdf.Point(rect.x1, rect.y1)]
        ]
        annot = page.add_ink_annot(strokes)
    else:
        annot = page.add_rect_annot(rect)
    try:
        annot.set_colors(stroke=_clean_color(stroke), fill=_clean_color(fill) if fill else None)
    except Exception:
        pass
    try:
        annot.set_border(width=float(width))
    except Exception:
        pass
    try:
        annot.set_opacity(float(opacity))
    except Exception:
        pass
    try:
        annot.set_info(title="星澜 PDF")
    except Exception:
        pass
    annot.update()
    doc.mark_dirty()


def add_link(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    *,
    uri: str | None = None,
    target_page: int | None = None,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    if uri:
        page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": uri})
    elif target_page is not None:
        page.insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": int(target_page)})
    doc.mark_dirty()


# ----------------------------------------------------------------- annotations
def add_text_markup(
    doc: PdfDocument,
    page_index: int,
    rects: Sequence[pymupdf.Rect],
    kind: str,
    color: tuple[float, float, float],
    *,
    opacity: float = 0.45,
    content: str = "",
) -> int:
    if not rects:
        return 0
    doc.checkpoint()
    page = _page(doc, page_index)
    count = 0
    for rect in rects:
        rect = pymupdf.Rect(rect)
        if rect.width < 0.5 or rect.height < 0.5:
            continue
        if kind == "highlight":
            annot = page.add_highlight_annot(rect)
        elif kind == "underline":
            annot = page.add_underline_annot(rect)
        elif kind == "strike":
            annot = page.add_strikeout_annot(rect)
        elif kind == "squiggly":
            annot = page.add_squiggly_annot(rect)
        else:
            annot = page.add_highlight_annot(rect)
        try:
            annot.set_colors(stroke=color)
            annot.set_opacity(float(opacity))
            annot.set_info(title="星澜 PDF", content=content)
        except Exception:
            pass
        annot.update()
        count += 1
    if count:
        doc.mark_dirty()
    return count


def add_sticky_note(
    doc: PdfDocument, page_index: int, point: pymupdf.Point, text: str
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    annot = page.add_text_annot(point, text, icon="Comment")
    try:
        annot.set_info(title="星澜 PDF", content=text)
        annot.set_colors(stroke=(1.0, 0.75, 0.18))
    except Exception:
        pass
    annot.update()
    doc.mark_dirty()


def add_freetext(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    text: str,
    *,
    size: float = 11,
    color: Color = (0.1, 0.1, 0.1),
    fill: Color | None = (1.0, 0.97, 0.8),
    border: Color | None = (0.95, 0.7, 0.2),
    align: int = 0,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    annot = page.add_freetext_annot(
        rect,
        text,
        fontsize=float(size),
        text_color=_clean_color(color),
        fill_color=_clean_color(fill) if fill else None,
        border_color=_clean_color(border) if border else None,
        border_width=1,
        align=align,
    )
    try:
        annot.set_info(title="星澜 PDF")
    except Exception:
        pass
    annot.update()
    doc.mark_dirty()


def add_stamp(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    text: str,
    *,
    color: str = "#D93B3B",
    subtitle: str = "",
) -> None:
    """Create a crisp transparent stamp image and place it on the page."""
    doc.checkpoint()
    page = _page(doc, page_index)
    data = render_stamp_png(text, color=color, subtitle=subtitle)
    page.insert_image(rect, stream=data, keep_proportion=True, overlay=True)
    doc.mark_dirty()


def render_stamp_png(text: str, color: str = "#D93B3B", subtitle: str = "") -> bytes:
    width, height = 720, 300
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rgb = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    draw.rounded_rectangle((12, 12, width - 12, height - 12), radius=22, outline=rgb + (255,), width=9)
    draw.rounded_rectangle((27, 27, width - 27, height - 27), radius=16, outline=rgb + (180,), width=3)
    font_path = cjk_font_file() or r"C:\Windows\Fonts\simhei.ttf"
    try:
        main_font = ImageFont.truetype(font_path, 112)
        sub_font = ImageFont.truetype(font_path, 38)
    except Exception:
        main_font = ImageFont.load_default()
        sub_font = main_font
    tb = draw.textbbox((0, 0), text, font=main_font)
    draw.text(((width - (tb[2] - tb[0])) / 2, 62), text, font=main_font, fill=rgb + (255,))
    if subtitle:
        sb = draw.textbbox((0, 0), subtitle, font=sub_font)
        draw.text(((width - (sb[2] - sb[0])) / 2, 208), subtitle, font=sub_font, fill=rgb + (230,))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def add_ink(
    doc: PdfDocument,
    page_index: int,
    strokes: Sequence[Sequence[tuple[float, float]]],
    *,
    color: Color = (0.92, 0.2, 0.24),
    width: float = 2.0,
    opacity: float = 1.0,
) -> None:
    if not strokes:
        return
    doc.checkpoint()
    page = _page(doc, page_index)
    annot = page.add_ink_annot([[pymupdf.Point(p) for p in stroke] for stroke in strokes if stroke])
    try:
        annot.set_colors(stroke=_clean_color(color))
        annot.set_border(width=float(width))
        annot.set_opacity(float(opacity))
        annot.set_info(title="星澜 PDF")
    except Exception:
        pass
    annot.update()
    doc.mark_dirty()


def delete_annotation(doc: PdfDocument, page_index: int, xref: int) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    _delete_annots(doc, page, [xref])
    doc.mark_dirty()


def update_annotation(
    doc: PdfDocument,
    page_index: int,
    xref: int,
    *,
    content: str | None = None,
    color: Color | None = None,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    for annot in page.annots() or []:
        if annot.xref == xref:
            info = annot.info or {}
            if content is not None:
                info["content"] = content
                annot.set_info(info)
            if color is not None:
                annot.set_colors(stroke=color)
            annot.update()
            break
    doc.mark_dirty()


def flatten_annotations(doc: PdfDocument) -> None:
    """Bake annotations into the page by rasterising annotated pages.

    PDF annotation appearance streams cannot be merged into page content with a
    single public PyMuPDF call.  A 200 dpi raster keeps the visual result while
    guaranteeing the annotation is no longer separately editable.
    """
    doc.checkpoint()
    for pno in range(doc.page_count):
        page = _page(doc, pno)
        annots = list(page.annots() or [])
        if not annots:
            continue
        pix = page.get_pixmap(matrix=pymupdf.Matrix(200 / 72, 200 / 72), alpha=False, annots=True)
        page.add_redact_annot(page.rect, fill=None)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        page.insert_image(page.rect, pixmap=pix, overlay=True)
        for annot in list(page.annots() or []):
            page.delete_annot(annot)
    doc.mark_dirty()


# ---------------------------------------------------------------- watermark etc.
def render_watermark_overlay(
    page_w: float,
    page_h: float,
    text: str,
    *,
    size: float,
    color: Color,
    opacity: float,
    angle: float,
    tiled: bool,
) -> bytes:
    """Render an arbitrarily rotated watermark as a transparent page overlay.

    PyMuPDF text insertion only supports right-angle rotation, so arbitrary
    angles are rasterised at 2x page resolution for both visual fidelity and
    predictable CJK rendering.
    """
    scale = 2.0
    width, height = max(2, int(page_w * scale)), max(2, int(page_h * scale))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    font_path = cjk_font_file() or r"C:\Windows\Fonts\simhei.ttf"
    try:
        font = ImageFont.truetype(font_path, max(10, int(size * scale)))
    except Exception:
        font = ImageFont.load_default()
    rgb = tuple(int(max(0.0, min(1.0, c)) * 255) for c in color)
    alpha = int(max(0.01, min(1.0, opacity)) * 255)
    bbox = font.getbbox(text)
    tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    pad = int(max(8, size * scale * 0.35))
    tile = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=rgb + (alpha,))
    tile = tile.rotate(float(angle), expand=True, resample=Image.Resampling.BICUBIC)
    if tiled:
        step_x = max(40, tile.width // 2)
        step_y = max(40, tile.height)
        for y in range(-tile.height, height + tile.height, step_y):
            for x in range(-tile.width, width + tile.width, step_x):
                canvas.alpha_composite(tile, (x, y))
    else:
        canvas.alpha_composite(
            tile,
            ((width - tile.width) // 2, (height - tile.height) // 2),
        )
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def add_watermark_text(
    doc: PdfDocument,
    text: str,
    *,
    size: float = 44,
    color: Color = (0.55, 0.58, 0.65),
    opacity: float = 0.18,
    angle: int = 45,
    tiled: bool = False,
    pages: Sequence[int] | None = None,
) -> None:
    doc.checkpoint()
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        data = render_watermark_overlay(
            page.rect.width, page.rect.height, text,
            size=size, color=color, opacity=opacity, angle=angle, tiled=tiled,
        )
        page.insert_image(page.rect, stream=data, overlay=True)
    doc.mark_dirty()


def add_watermark_image(
    doc: PdfDocument,
    path: str,
    *,
    opacity: float = 0.18,
    pages: Sequence[int] | None = None,
) -> None:
    doc.checkpoint()
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        w = page.rect.width * 0.45
        h = w * 0.55
        rect = pymupdf.Rect(
            (page.rect.width - w) / 2, (page.rect.height - h) / 2,
            (page.rect.width + w) / 2, (page.rect.height + h) / 2,
        )
        page.insert_image(rect, filename=path, overlay=True, alpha=int(max(1, opacity * 255)))
    doc.mark_dirty()


def add_background(
    doc: PdfDocument,
    *,
    color: str | None = None,
    image_path: str | None = None,
    opacity: float = 1.0,
    pages: Sequence[int] | None = None,
) -> None:
    doc.checkpoint()
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        if color:
            rgb = _clean_color(color)
            page.draw_rect(page.rect, color=None, fill=rgb, overlay=False)
        elif image_path:
            page.insert_image(
                page.rect, filename=image_path, overlay=False, alpha=int(max(1, opacity * 255))
            )
    doc.mark_dirty()


POSITIONS = {
    "top-left": (0, 1, 0),
    "top-center": (0, 1, 1),
    "top-right": (0, 1, 2),
    "bottom-left": (2, 3, 0),
    "bottom-center": (2, 3, 1),
    "bottom-right": (2, 3, 2),
}


def add_header_footer(
    doc: PdfDocument,
    text: str,
    *,
    position: str = "footer-center",
    size: float = 9,
    color: Color = (0.35, 0.38, 0.44),
    margin: float = 24,
    pages: Sequence[int] | None = None,
    font_bold: bool = False,
) -> None:
    doc.checkpoint()
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        total = doc.page_count
        value = text.replace("{page}", str(pno + 1)).replace("{total}", str(total))
        if position.startswith("top"):
            y0 = margin
            y1 = margin + size * 2.2
        else:
            y0 = page.rect.height - margin - size * 2.2
            y1 = page.rect.height - margin
        align = 0 if position.endswith("left") else (1 if position.endswith("center") else 2)
        x0 = margin
        x1 = page.rect.width - margin
        _insert_cjk_box(
            page, pymupdf.Rect(x0, y0, x1, y1), value, size, color, align=align, bold=font_bold
        )
    doc.mark_dirty()


def add_page_numbers(
    doc: PdfDocument,
    *,
    position: str = "bottom-center",
    fmt: str = "第 {page} 页 / 共 {total} 页",
    size: float = 9,
    color: Color = (0.35, 0.38, 0.44),
    start: int = 1,
    pages: Sequence[int] | None = None,
) -> None:
    doc.checkpoint()
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    total = doc.page_count
    for i, pno in enumerate(page_range):
        page = _page(doc, pno)
        value = fmt.replace("{page}", str(start + i)).replace("{total}", str(total))
        if position.startswith("top"):
            y0 = 22
            y1 = 50
        else:
            y0 = page.rect.height - 46
            y1 = page.rect.height - 18
        align = 0 if position.endswith("left") else (1 if position.endswith("center") else 2)
        _insert_cjk_box(
            page,
            pymupdf.Rect(30, y0, page.rect.width - 30, y1),
            value,
            size,
            color,
            align=align,
        )
    doc.mark_dirty()


# ------------------------------------------------------------------- page ops
def insert_blank_page(
    doc: PdfDocument, index: int, width: float = 595, height: float = 842
) -> None:
    doc.checkpoint()
    doc.require_doc().new_page(pno=max(0, min(index, doc.page_count)), width=width, height=height)
    doc.mark_dirty()


def insert_pdf_pages(
    doc: PdfDocument,
    source: str,
    index: int,
    pages: Sequence[int] | None = None,
    *,
    password: str | None = None,
) -> None:
    src = pymupdf.open(source)
    if src.needs_pass:
        if not password or not src.authenticate(password):
            src.close()
            raise ValueError("源 PDF 需要正确密码")
    try:
        doc.checkpoint()
        index = max(0, min(index, doc.page_count))
        if pages is None or list(pages) == list(range(len(src))):
            doc.require_doc().insert_pdf(src, start_at=index)
        else:
            for offset, pno in enumerate(pages):
                if 0 <= pno < len(src):
                    doc.require_doc().insert_pdf(
                        src, from_page=pno, to_page=pno, start_at=index + offset
                    )
        doc.mark_dirty()
    finally:
        src.close()


def delete_pages(doc: PdfDocument, pages: Sequence[int]) -> None:
    valid = sorted({p for p in pages if 0 <= p < doc.page_count}, reverse=True)
    if not valid:
        return
    if len(valid) >= doc.page_count:
        raise ValueError("文档至少需要保留一页")
    doc.checkpoint()
    doc.require_doc().delete_pages(valid)
    doc.mark_dirty()


def rotate_pages(doc: PdfDocument, pages: Sequence[int], angle: int) -> None:
    doc.checkpoint()
    for pno in pages:
        if 0 <= pno < doc.page_count:
            page = _page(doc, pno)
            page.set_rotation((page.rotation + angle) % 360)
    doc.mark_dirty()


def move_page(doc: PdfDocument, old_index: int, new_index: int) -> None:
    if old_index == new_index:
        return
    doc.checkpoint()
    doc.require_doc().move_page(old_index, new_index)
    doc.mark_dirty()


def duplicate_page(doc: PdfDocument, index: int) -> int:
    if not (0 <= index < doc.page_count):
        raise ValueError("页码超出范围")
    doc.checkpoint()
    new_index = index + 1
    doc.require_doc().fullcopy_page(index, to=new_index)
    doc.mark_dirty()
    return new_index


def resize_pages(
    doc: PdfDocument,
    width: float,
    height: float,
    pages: Sequence[int] | None = None,
    *,
    keep_ratio: bool = True,
) -> None:
    """Rebuild the document with selected pages placed on a new page size.

    Text and vector content are rendered into the new page through
    ``show_pdf_page``; untouched pages are copied with their annotations.
    """
    page_range = set(range(doc.page_count) if pages is None else pages)
    doc.checkpoint()
    source = pymupdf.open(stream=doc.require_doc().tobytes(garbage=0), filetype="pdf")
    new_doc = pymupdf.open()
    try:
        for pno in range(len(source)):
            if pno not in page_range:
                new_doc.insert_pdf(source, from_page=pno, to_page=pno)
                continue
            old = source[pno].rect
            new_page = new_doc.new_page(width=width, height=height)
            if keep_ratio:
                scale = min(width / max(old.width, 1), height / max(old.height, 1))
                w, h = old.width * scale, old.height * scale
                target = pymupdf.Rect(
                    (width - w) / 2, (height - h) / 2,
                    (width + w) / 2, (height + h) / 2,
                )
            else:
                target = pymupdf.Rect(0, 0, width, height)
            new_page.show_pdf_page(target, source, pno, overlay=True)
        try:
            new_doc.set_toc(source.get_toc(simple=True))
        except Exception:
            pass
        try:
            new_doc.set_metadata(source.metadata or {})
        except Exception:
            pass
        old_doc = doc.require_doc()
        doc.doc = new_doc
        new_doc = None
        old_doc.close()
        doc.page = min(doc.page, max(0, doc.page_count - 1))
        doc.mark_dirty()
    finally:
        source.close()
        if new_doc is not None:
            new_doc.close()


def crop_pages(doc: PdfDocument, pages: Sequence[int], margins: tuple[float, float, float, float]) -> None:
    doc.checkpoint()
    left, top, right, bottom = margins
    for pno in pages:
        page = _page(doc, pno)
        rect = page.rect
        crop = pymupdf.Rect(rect.x0 + left, rect.y0 + top, rect.x1 - right, rect.y1 - bottom)
        if crop.width < 10 or crop.height < 10:
            raise ValueError("裁剪区域过小")
        page.set_cropbox(crop)
    doc.mark_dirty()


def replace_page_with_pdf(doc: PdfDocument, index: int, source: str, source_page: int = 0) -> None:
    src = pymupdf.open(source)
    try:
        if source_page < 0 or source_page >= len(src):
            raise ValueError("源 PDF 页码超出范围")
        doc.checkpoint()
        page = _page(doc, index)
        page.add_redact_annot(page.rect, fill=(1, 1, 1))
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        page.show_pdf_page(page.rect, src, source_page, overlay=True)
        doc.mark_dirty()
    finally:
        src.close()


def extract_pages(doc: PdfDocument, pages: Sequence[int], target: str) -> str:
    out = pymupdf.open()
    try:
        for pno in pages:
            out.insert_pdf(doc.require_doc(), from_page=pno, to_page=pno)
        out.save(target, garbage=3, deflate=True)
    finally:
        out.close()
    return target


def split_document(
    doc: PdfDocument,
    output_dir: str,
    *,
    every: int = 1,
    ranges: Sequence[tuple[int, int]] | None = None,
    prefix: str = "split",
) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    groups: list[list[int]] = []
    if ranges:
        for start, end in ranges:
            groups.append(list(range(max(0, start), min(doc.page_count - 1, end) + 1)))
    else:
        step = max(1, int(every))
        groups = [list(range(i, min(i + step, doc.page_count))) for i in range(0, doc.page_count, step)]
    outputs: list[str] = []
    for i, group in enumerate(groups, 1):
        if not group:
            continue
        out = pymupdf.open()
        for pno in group:
            out.insert_pdf(doc.require_doc(), from_page=pno, to_page=pno)
        path = os.path.join(output_dir, f"{prefix}_{i:03d}.pdf")
        out.save(path, garbage=3, deflate=True)
        out.close()
        outputs.append(path)
    return outputs


def merge_documents(sources: Sequence[str], target: str, passwords: dict[str, str] | None = None) -> str:
    out = pymupdf.open()
    try:
        for source in sources:
            src = pymupdf.open(source)
            if src.needs_pass:
                pwd = (passwords or {}).get(source)
                if not pwd or not src.authenticate(pwd):
                    src.close()
                    raise ValueError(f"无法打开受保护的 PDF：{os.path.basename(source)}")
            out.insert_pdf(src)
            src.close()
        out.save(target, garbage=3, deflate=True)
    finally:
        out.close()
    return target


def compress_document(doc: PdfDocument, target: str, *, dpi: int = 140, quality: int = 65) -> str:
    work = pymupdf.open(stream=doc.require_doc().tobytes(garbage=0), filetype="pdf")
    try:
        try:
            work.rewrite_images(dpi_threshold=dpi, dpi_target=dpi, quality=int(quality))
        except Exception:
            pass
        try:
            work.subset_fonts()
        except Exception:
            pass
        work.save(target, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)
    finally:
        work.close()
    return target


def save_copy(doc: PdfDocument, target: str) -> str:
    doc.require_doc().save(target, garbage=3, deflate=True)
    return target


# --------------------------------------------------------------------- security
def permissions_value(
    *,
    print_: bool = True,
    modify: bool = True,
    copy: bool = True,
    annotate: bool = True,
    forms: bool = True,
    extract: bool = True,
    assemble: bool = True,
    print_hq: bool = True,
    accessibility: bool = True,
) -> int:
    value = 0
    mapping = [
        (print_, pymupdf.PDF_PERM_PRINT),
        (modify, pymupdf.PDF_PERM_MODIFY),
        (copy, pymupdf.PDF_PERM_COPY),
        (annotate, pymupdf.PDF_PERM_ANNOTATE),
        (forms, pymupdf.PDF_PERM_FORM),
        (extract, pymupdf.PDF_PERM_COPY),
        (assemble, pymupdf.PDF_PERM_ASSEMBLE),
        (print_hq, pymupdf.PDF_PERM_PRINT_HQ),
        (accessibility, pymupdf.PDF_PERM_ACCESSIBILITY),
    ]
    for enabled, flag in mapping:
        if enabled:
            value |= flag
    return value


def encrypt_to(
    doc: PdfDocument,
    target: str,
    user_password: str,
    owner_password: str,
    permissions: int,
    *,
    algorithm: str = "aes256",
) -> str:
    enc = pymupdf.PDF_ENCRYPT_AES_256 if algorithm == "aes256" else pymupdf.PDF_ENCRYPT_AES_128
    source = pymupdf.open(stream=doc.require_doc().tobytes(garbage=0), filetype="pdf")
    try:
        try:
            source.subset_fonts()
        except Exception:
            pass
        source.save(
            target,
            encryption=enc,
            owner_pw=owner_password,
            user_pw=user_password,
            permissions=permissions,
            garbage=4,
            deflate=True,
        )
    finally:
        source.close()
    return target


def decrypt_to(doc: PdfDocument, target: str) -> str:
    try:
        doc.require_doc().save(target, encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    except Exception as exc:
        raise ValueError("解除密码需要所有者密码，请用所有者密码打开后再试") from exc
    return target


def decrypt_copy(source: str, target: str, owner_password: str) -> str:
    doc = pymupdf.open(source)
    try:
        if doc.needs_pass and not doc.authenticate(owner_password):
            raise ValueError("权限密码错误，无法解除保护")
        doc.save(target, encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    finally:
        doc.close()
    return target


def update_permissions_copy(
    source: str,
    target: str,
    owner_password: str,
    permissions: int,
    *,
    user_password: str | None = None,
) -> str:
    doc = pymupdf.open(source)
    try:
        if doc.needs_pass and not doc.authenticate(owner_password):
            raise ValueError("权限密码错误，无法修改权限")
        kwargs: dict[str, Any] = dict(
            encryption=pymupdf.PDF_ENCRYPT_KEEP,
            owner_pw=owner_password,
            permissions=permissions,
            garbage=3,
            deflate=True,
        )
        if user_password is not None:
            kwargs["user_pw"] = user_password
        doc.save(target, **kwargs)
    finally:
        doc.close()
    return target


def redact_search(
    doc: PdfDocument,
    query: str,
    *,
    fill: Color = (0, 0, 0),
    pages: Sequence[int] | None = None,
) -> int:
    if not query:
        return 0
    doc.checkpoint()
    count = 0
    page_range = range(doc.page_count) if pages is None else pages
    for pno in page_range:
        page = _page(doc, pno)
        hits = list(page.search_for(query))
        if not hits:
            continue
        for rect in hits:
            page.add_redact_annot(rect, fill=fill)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        count += len(hits)
    if count:
        doc.mark_dirty()
    return count


def redact_area(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    *,
    fill: Color | None = (0, 0, 0),
    overlay_text: str = "",
    overlay_color: Color = (1, 1, 1),
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    if overlay_text:
        size = _fit_font_size(overlay_text, rect, 10)
        _insert_cjk_box(page, rect, overlay_text, size, overlay_color, align=1)
    doc.mark_dirty()


# ------------------------------------------------------------------- bookmarks
def set_bookmarks(doc: PdfDocument, entries: Sequence[Sequence]) -> None:
    doc.checkpoint()
    clean: list[list] = []
    for row in entries:
        if len(row) >= 3:
            clean.append([int(row[0]), str(row[1]), int(row[2])])
    doc.require_doc().set_toc(clean)
    doc.mark_dirty()


def add_bookmark(doc: PdfDocument, title: str, page_index: int) -> None:
    toc = doc.outline()
    toc.append([1, title, page_index + 1])
    set_bookmarks(doc, toc)


def delete_bookmark(doc: PdfDocument, index: int) -> None:
    toc = doc.outline()
    if 0 <= index < len(toc):
        toc.pop(index)
        set_bookmarks(doc, toc)


# ----------------------------------------------------------------- attachments
def add_attachment(doc: PdfDocument, path: str, name: str | None = None) -> None:
    doc.checkpoint()
    filename = name or os.path.basename(path)
    doc.require_doc().embfile_add(filename, path, filename=filename)
    doc.mark_dirty()


def delete_attachment(doc: PdfDocument, name: str) -> None:
    doc.checkpoint()
    doc.require_doc().embfile_del(name)
    doc.mark_dirty()


def extract_attachment(doc: PdfDocument, name: str, target: str) -> str:
    data = doc.require_doc().embfile_get(name)
    with open(target, "wb") as fh:
        fh.write(data)
    return target


# ----------------------------------------------------------------------- forms
def add_form_field(
    doc: PdfDocument,
    page_index: int,
    kind: str,
    rect: pymupdf.Rect,
    *,
    name: str,
    value: str = "",
    options: Sequence[str] | None = None,
    font_size: float = 10,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    widget = pymupdf.Widget()
    widget.field_name = name
    widget.rect = pymupdf.Rect(rect)
    widget.text_font = "Helv"
    widget.text_fontsize = float(font_size)
    widget.text_color = (0.08, 0.1, 0.15)
    widget.fill_color = (0.97, 0.98, 1.0)
    widget.border_color = (0.55, 0.63, 0.78)
    widget.border_width = 1
    if kind == "text":
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = value
    elif kind == "checkbox":
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_value = value in ("1", "true", "True", "是", "yes")
    elif kind == "radio":
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON
        widget.field_value = value in ("1", "true", "True", "是", "yes")
    elif kind == "dropdown":
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
        widget.choice_values = list(options or ["选项一", "选项二"])
        widget.field_value = value or widget.choice_values[0]
    elif kind == "signature":
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
    else:
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = value
    page.add_widget(widget)
    doc.mark_dirty()


def fill_form_values(doc: PdfDocument, values: dict[int, str]) -> None:
    if not values:
        return
    doc.checkpoint()
    for pno in range(doc.page_count):
        page = _page(doc, pno)
        for widget in page.widgets() or []:
            if widget.xref not in values:
                continue
            value = values[widget.xref]
            try:
                if widget.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                    widget.field_value = bool(value)
                else:
                    widget.field_value = value
                widget.update()
            except Exception:
                continue
    doc.mark_dirty()


def sign_page(
    doc: PdfDocument,
    page_index: int,
    rect: pymupdf.Rect,
    image_path: str | None = None,
    image_bytes: bytes | None = None,
) -> None:
    doc.checkpoint()
    page = _page(doc, page_index)
    if image_bytes:
        page.insert_image(rect, stream=image_bytes, keep_proportion=True, overlay=True)
    elif image_path:
        page.insert_image(rect, filename=image_path, keep_proportion=True, overlay=True)
    doc.mark_dirty()
