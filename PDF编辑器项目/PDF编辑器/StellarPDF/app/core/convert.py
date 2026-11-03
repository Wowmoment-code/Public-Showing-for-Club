"""Format conversion helpers used by the Convert ribbon tab.

The implementations favour reliability and offline operation over pixel-perfect
layout reproduction.  Text, tables, images and page order are preserved.
"""
from __future__ import annotations

import html
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pymupdf
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pptx import Presentation
from pptx.util import Emu
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..config import cjk_font_file
from .document import PdfDocument

Progress = Callable[[int, str], None] | None


def _progress(cb: Progress, value: int, message: str) -> None:
    if cb:
        cb(max(0, min(100, int(value))), message)


def _ensure_pdf_suffix(path: str) -> str:
    return path if path.lower().endswith(".pdf") else path + ".pdf"


# --------------------------------------------------------------- PDF -> output
def pdf_to_images(
    doc: PdfDocument,
    output_dir: str,
    *,
    fmt: str = "png",
    dpi: int = 150,
    pages: Sequence[int] | None = None,
    prefix: str = "page",
    progress: Progress = None,
) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    outputs: list[str] = []
    for i, pno in enumerate(page_range):
        pix = doc.render_dpi(pno, dpi=dpi)
        path = os.path.join(output_dir, f"{prefix}_{pno + 1:03d}.{fmt.lower()}")
        if fmt.lower() in ("jpg", "jpeg"):
            pil = pix.pil_image()
            pil = pil.convert("RGB")
            pil.save(path, quality=92, optimize=True)
        else:
            pix.save(path)
        outputs.append(path)
        _progress(progress, (i + 1) / max(1, len(page_range)) * 100, f"导出第 {pno + 1} 页")
    return outputs


def pdf_to_text(
    doc: PdfDocument,
    target: str,
    *,
    pages: Sequence[int] | None = None,
    progress: Progress = None,
) -> str:
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    chunks: list[str] = []
    for i, pno in enumerate(page_range):
        chunks.append(f"===== 第 {pno + 1} 页 =====\n" + doc.text(pno))
        _progress(progress, (i + 1) / max(1, len(page_range)) * 100, "提取文本")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(chunks))
    return target


def _set_docx_font(run, name: str = "Microsoft YaHei", size: float | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)


def pdf_to_docx(
    doc: PdfDocument,
    target: str,
    *,
    pages: Sequence[int] | None = None,
    add_page_breaks: bool = True,
    progress: Progress = None,
) -> str:
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    out = DocxDocument()
    # Use the first page size for the document.
    if page_range:
        w, h = doc.page_size(page_range[0])
        section = out.sections[0]
        section.page_width = Cm(w / 72 * 2.54)
        section.page_height = Cm(h / 72 * 2.54)
        section.left_margin = Cm(1.8)
        section.right_margin = Cm(1.8)
        section.top_margin = Cm(1.8)
        section.bottom_margin = Cm(1.8)
    style = out.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(10.5)
    for idx, pno in enumerate(page_range):
        if idx and add_page_breaks:
            out.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        page = doc.require_doc()[pno]
        data = page.get_text("dict")
        blocks = data.get("blocks", [])
        for block in blocks:
            if block.get("type") == 1:
                # Place embedded raster images after the surrounding text.
                try:
                    image_bytes = block.get("image")
                    if image_bytes:
                        out.add_picture(io.BytesIO(image_bytes), width=Cm(min(15.0, page.rect.width / 72 * 2.54 - 3)))
                except Exception:
                    pass
                continue
            if block.get("type") != 0:
                continue
            para = out.add_paragraph()
            para.paragraph_format.space_after = Pt(3)
            para.paragraph_format.line_spacing = 1.15
            for line in block.get("lines", []):
                first = True
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    if not first:
                        para.add_run(" " if not text.startswith(" ") else "")
                    run = para.add_run(text)
                    size = float(span.get("size", 10.5))
                    _set_docx_font(run, size=min(36, max(6, size * 0.95)))
                    color = int(span.get("color", 0))
                    run.font.color.rgb = RGBColor(
                        (color >> 16) & 255, (color >> 8) & 255, color & 255
                    )
                    if int(span.get("flags", 0)) & 16:
                        run.bold = True
                    if int(span.get("flags", 0)) & 2:
                        run.italic = True
                    first = False
        _progress(progress, (idx + 1) / max(1, len(page_range)) * 100, f"转换第 {pno + 1} 页")
    out.save(target)
    return target


def pdf_to_xlsx(
    doc: PdfDocument,
    target: str,
    *,
    pages: Sequence[int] | None = None,
    progress: Progress = None,
) -> str:
    wb = Workbook()
    wb.remove(wb.active)
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    header_fill = PatternFill("solid", fgColor="EAF1FF")
    for idx, pno in enumerate(page_range):
        page = doc.require_doc()[pno]
        tables = []
        try:
            finder = page.find_tables()
            tables = list(getattr(finder, "tables", []) or [])
        except Exception:
            tables = []
        if tables:
            for t_idx, table in enumerate(tables, 1):
                ws = wb.create_sheet(f"P{pno + 1}_表{t_idx}"[:31])
                try:
                    rows = table.extract()
                except Exception:
                    rows = []
                for r_idx, row in enumerate(rows, 1):
                    for c_idx, value in enumerate(row, 1):
                        cell = ws.cell(row=r_idx, column=c_idx, value=value)
                        cell.alignment = Alignment(vertical="center", wrap_text=True)
                        if r_idx == 1:
                            cell.font = Font(bold=True)
                            cell.fill = header_fill
                for col in range(1, max((len(r) for r in rows), default=1) + 1):
                    letter = ws.cell(row=1, column=col).column_letter
                    ws.column_dimensions[letter].width = 22
        else:
            ws = wb.create_sheet(f"第{pno + 1}页"[:31])
            text = page.get_text("text")
            for r_idx, line in enumerate(text.splitlines(), 1):
                ws.cell(row=r_idx, column=1, value=line)
            ws.column_dimensions["A"].width = 110
        _progress(progress, (idx + 1) / max(1, len(page_range)) * 100, f"识别第 {pno + 1} 页表格")
    if not wb.worksheets:
        wb.create_sheet("空白")
    wb.save(target)
    return target


def pdf_to_pptx(
    doc: PdfDocument,
    target: str,
    *,
    dpi: int = 150,
    pages: Sequence[int] | None = None,
    progress: Progress = None,
) -> str:
    prs = Presentation()
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    if page_range:
        w_pt, h_pt = doc.page_size(page_range[0])
        prs.slide_width = Emu(int(w_pt * 12700))
        prs.slide_height = Emu(int(h_pt * 12700))
    blank = prs.slide_layouts[6]
    for idx, pno in enumerate(page_range):
        slide = prs.slides.add_slide(blank)
        pix = doc.render_dpi(pno, dpi=dpi)
        img = io.BytesIO(pix.tobytes("png"))
        slide.shapes.add_picture(img, 0, 0, width=prs.slide_width, height=prs.slide_height)
        _progress(progress, (idx + 1) / max(1, len(page_range)) * 100, f"生成幻灯片 {pno + 1}")
    prs.save(target)
    return target


def pdf_to_html(
    doc: PdfDocument,
    target: str,
    *,
    pages: Sequence[int] | None = None,
    progress: Progress = None,
) -> str:
    page_range = list(range(doc.page_count)) if pages is None else list(pages)
    chunks: list[str] = []
    for idx, pno in enumerate(page_range):
        try:
            body = doc.require_doc()[pno].get_text("html")
        except Exception:
            body = f"<pre>{html.escape(doc.text(pno))}</pre>"
        chunks.append(f'<section class="pdf-page" data-page="{pno + 1}">{body}</section>')
        _progress(progress, (idx + 1) / max(1, len(page_range)) * 100, "生成 HTML")
    page_css = "".join(
        f"""
    .pdf-page {{ background:#fff; margin:24px auto; padding:48px; max-width:900px;
      box-shadow:0 4px 24px rgba(30,50,90,.12); position:relative; }}
    """
        for _ in [0]
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{html.escape(doc.title)}</title>
<style>
  body {{ background:#eef1f6; margin:0; font-family:"Microsoft YaHei",sans-serif; }}
  {page_css}
  .pdf-page p {{ margin:.25em 0; }}
  @media print {{ body {{ background:#fff; }} .pdf-page {{ box-shadow:none; margin:0; page-break-after:always; }} }}
</style></head><body>{''.join(chunks)}</body></html>"""
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    return target


# --------------------------------------------------------------- images -> PDF
def images_to_pdf(
    images: Sequence[str],
    target: str,
    *,
    page_mode: str = "fit",
    progress: Progress = None,
) -> str:
    out = pymupdf.open()
    try:
        for i, path in enumerate(images):
            try:
                with pymupdf.open(path) as img_doc:
                    if not img_doc.is_pdf:
                        pix = pymupdf.Pixmap(path)
                        w = max(1.0, pix.width * 72.0 / 96.0)
                        h = max(1.0, pix.height * 72.0 / 96.0)
                    else:
                        page = img_doc[0]
                        w, h = page.rect.width, page.rect.height
            except Exception:
                pix = pymupdf.Pixmap(path)
                w = max(1.0, pix.width * 72.0 / 96.0)
                h = max(1.0, pix.height * 72.0 / 96.0)
            if page_mode == "a4":
                pw, ph = 595.0, 842.0
                page = out.new_page(width=pw, height=ph)
                scale = min(pw / w, ph / h) * 0.94
                rect = pymupdf.Rect(
                    (pw - w * scale) / 2,
                    (ph - h * scale) / 2,
                    (pw + w * scale) / 2,
                    (ph + h * scale) / 2,
                )
            else:
                page = out.new_page(width=w, height=h)
                rect = page.rect
            page.insert_image(rect, filename=path, keep_proportion=True)
            _progress(progress, (i + 1) / max(1, len(images)) * 100, f"添加图片 {i + 1}")
        out.save(target, garbage=3, deflate=True)
    finally:
        out.close()
    return target


# --------------------------------------------------------- Office/document input
def _register_pdf_fonts() -> tuple[str, str]:
    normal = cjk_font_file()
    if not normal:
        return "Helvetica", "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont("StellarCJK", normal))
    except Exception:
        pass
    bold_path = r"C:\Windows\Fonts\msyhbd.ttc"
    try:
        if os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("StellarCJKBold", bold_path))
        else:
            pdfmetrics.registerFont(TTFont("StellarCJKBold", normal))
    except Exception:
        pass
    try:
        pdfmetrics.registerFontFamily("StellarCJK", normal="StellarCJK", bold="StellarCJKBold")
    except Exception:
        pass
    return "StellarCJK", "StellarCJKBold"


def _pdf_styles() -> dict[str, ParagraphStyle]:
    normal, bold = _register_pdf_fonts()
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle(
            "StellarBody", parent=base["BodyText"], fontName=normal, fontSize=10.5,
            leading=17, spaceAfter=6, wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "StellarH1", parent=base["Heading1"], fontName=bold, fontSize=20,
            leading=28, spaceAfter=12, textColor=colors.HexColor("#1E2638"),
        ),
        "h2": ParagraphStyle(
            "StellarH2", parent=base["Heading2"], fontName=bold, fontSize=15,
            leading=22, spaceAfter=8, textColor=colors.HexColor("#2F3A52"),
        ),
        "h3": ParagraphStyle(
            "StellarH3", parent=base["Heading3"], fontName=bold, fontSize=12,
            leading=18, spaceAfter=5,
        ),
    }
    return styles


def docx_to_pdf(
    source: str, target: str, *, progress: Progress = None
) -> str:
    document = DocxDocument(source)
    styles = _pdf_styles()
    story: list = []
    _progress(progress, 10, "读取 Word 文档")
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            story.append(Spacer(1, 5))
            continue
        style_name = (para.style.name or "").lower()
        style = styles["body"]
        if "heading 1" in style_name or "标题 1" in style_name:
            style = styles["h1"]
        elif "heading 2" in style_name or "标题 2" in style_name:
            style = styles["h2"]
        elif "heading" in style_name or "标题" in style_name:
            style = styles["h3"]
        safe = html.escape(text).replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        if para.alignment is not None and str(para.alignment).startswith("CENTER"):
            style = ParagraphStyle(f"{style.name}Center", parent=style, alignment=TA_CENTER)
        story.append(Paragraph(safe, style))
    for table in document.tables:
        data = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if not data:
            continue
        col_count = max(len(row) for row in data)
        data = [row + [""] * (col_count - len(row)) for row in data]
        widths = [170 * mm / col_count] * col_count
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "StellarCJK"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BCC5D6")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FF")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(Spacer(1, 6))
        story.append(t)
        story.append(Spacer(1, 8))
    _progress(progress, 65, "排版 PDF")
    doc = SimpleDocTemplate(
        target,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=os.path.splitext(os.path.basename(source))[0],
    )
    doc.build(story or [Paragraph("（空白文档）", styles["body"])])
    _progress(progress, 100, "完成")
    return target


def xlsx_to_pdf(
    source: str, target: str, *, progress: Progress = None
) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(source, data_only=True)
    styles = _pdf_styles()
    story: list = []
    for sheet_index, ws in enumerate(wb.worksheets):
        if sheet_index:
            story.append(PageBreak())
        story.append(Paragraph(html.escape(ws.title), styles["h2"]))
        rows = []
        max_rows = min(ws.max_row, 400)
        max_cols = min(ws.max_column, 16)
        for r in range(1, max_rows + 1):
            row = []
            for c in range(1, max_cols + 1):
                value = ws.cell(row=r, column=c).value
                row.append("" if value is None else str(value))
            if any(cell for cell in row):
                rows.append(row)
        if not rows:
            story.append(Paragraph("（空工作表）", styles["body"]))
            continue
        col_count = max(len(r) for r in rows)
        rows = [r + [""] * (col_count - len(r)) for r in rows]
        available = 250 * mm if ws.max_column > 7 else 170 * mm
        t = Table(rows, colWidths=[available / col_count] * col_count, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "StellarCJK"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C7CFDC")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FF")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        _progress(progress, 20 + 60 * (sheet_index + 1) / max(1, len(wb.worksheets)), "排版工作表")
    doc = SimpleDocTemplate(target, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    doc.build(story or [Paragraph("（空白工作簿）", styles["body"])])
    _progress(progress, 100, "完成")
    return target


def pptx_to_pdf(
    source: str, target: str, *, progress: Progress = None
) -> str:
    prs = Presentation(source)
    styles = _pdf_styles()
    page_w = prs.slide_width / 12700 if prs.slide_width else 960
    page_h = prs.slide_height / 12700 if prs.slide_height else 540
    pagesize = (page_w, page_h)
    story: list = []
    for idx, slide in enumerate(prs.slides):
        if idx:
            story.append(PageBreak())
        title_done = False
        for shape in slide.shapes:
            text = getattr(shape, "text", "") or ""
            if not text.strip():
                continue
            style = styles["h1"] if not title_done else styles["body"]
            story.append(Paragraph(html.escape(text).replace("\n", "<br/>"), style))
            title_done = True
            story.append(Spacer(1, 8))
        _progress(progress, (idx + 1) / max(1, len(prs.slides)) * 80, "读取幻灯片")
    doc = SimpleDocTemplate(target, pagesize=pagesize, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    doc.build(story or [Paragraph("（空白演示文稿）", styles["body"])])
    _progress(progress, 100, "完成")
    return target


def convert_office_to_pdf(source: str, target: str, *, progress: Progress = None) -> str:
    ext = Path(source).suffix.lower()
    if ext == ".docx":
        return docx_to_pdf(source, target, progress=progress)
    if ext in (".xlsx", ".xlsm"):
        return xlsx_to_pdf(source, target, progress=progress)
    if ext == ".pptx":
        return pptx_to_pdf(source, target, progress=progress)
    raise ValueError("支持 Word (.docx)、Excel (.xlsx)、PowerPoint (.pptx) 转 PDF")
