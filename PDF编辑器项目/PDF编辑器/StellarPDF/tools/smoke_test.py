"""Headless smoke test for the PDF engine and converters."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test_output"
DEMO = ROOT / "sample" / "欢迎使用星澜PDF.pdf"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    from app.core.document import PdfDocument
    from app.core import operations as ops
    from app.core import convert

    doc = PdfDocument()
    doc.open(DEMO)
    assert doc.page_count == 6, doc.page_count
    spans = doc.spans(2)
    assert spans, "no spans on page 3"
    target_span = next((s for s in spans if "在日常办公中" in s.text), None)
    assert target_span is not None, [s.text[:20] for s in spans][:20]
    print("span:", target_span.text[:30], target_span.size)
    ops.replace_text(doc, target_span, "在日常办公中，星澜 PDF 让修改变得简单。")
    assert "让修改变得简单" in doc.text(2)
    print("replace ok")
    assert doc.undo()
    assert "在日常办公中" in doc.text(2)
    assert doc.redo()
    print("undo/redo ok")

    ops.add_text_markup(doc, 2, [pymupdf.Rect(60, 180, 300, 196)], "highlight", (1, 0.8, 0.2))
    ops.add_sticky_note(doc, 2, __import__("pymupdf").Point(400, 300), "请复核这一段")
    ops.add_shape(doc, 2, "rect", __import__("pymupdf").Rect(320, 340, 480, 420), stroke=(0.2, 0.4, 1))
    print("annotations", len(doc.annotations(2)))
    assert len(doc.annotations(2)) >= 3

    image_path = OUT / "image.png"
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (360, 200), "white")
    draw = ImageDraw.Draw(im)
    draw.rectangle((10, 10, 350, 190), outline="#2F6BFF", width=4)
    draw.text((40, 80), "STELLAR PDF", fill="#2F6BFF")
    im.save(image_path)
    ops.insert_image(doc, 1, __import__("pymupdf").Rect(60, 600, 260, 700), str(image_path))
    print("image ok")

    ops.add_watermark_text(doc, "内部资料", opacity=0.14)
    ops.add_page_numbers(doc)
    ops.add_header_footer(doc, "星澜 PDF 测试文档", position="top-left")
    print("decorations ok")

    ops.add_stamp(doc, 2, __import__("pymupdf").Rect(380, 520, 530, 590), "已批准", subtitle="APPROVED")
    print("stamp ok")

    doc.save(OUT / "edited.pdf")
    print("save ok", (OUT / "edited.pdf").stat().st_size)
    assert doc.page_count == 6

    # Page operations -------------------------------------------------------
    ops.insert_blank_page(doc, 1)
    assert doc.page_count == 7
    ops.rotate_pages(doc, [1], 90)
    ops.duplicate_page(doc, 1)
    assert doc.page_count == 8
    ops.delete_pages(doc, [1])
    assert doc.page_count == 7
    ops.move_page(doc, 6, 0)
    print("page ops ok", doc.page_count)
    ops.resize_pages(doc, 420, 595, pages=[0])
    assert abs(doc.page_size(0)[0] - 420) < 1
    print("resize ok", doc.page_size(0))
    order = list(reversed(range(doc.page_count)))
    doc.require_doc().select(order)
    assert doc.page_count == len(order)
    print("select/reorder ok")

    # Split / extract / merge ----------------------------------------------
    outputs = ops.split_document(doc, str(OUT / "split"), every=2)
    assert outputs and all(Path(p).exists() for p in outputs)
    extracted = OUT / "extract.pdf"
    ops.extract_pages(doc, [0, 2, 4], str(extracted))
    assert extracted.exists()
    merged = OUT / "merged.pdf"
    ops.merge_documents([str(extracted), str(extracted)], str(merged))
    assert merged.exists()
    print("split/extract/merge ok")

    # Compression -----------------------------------------------------------
    compressed = OUT / "compressed.pdf"
    ops.compress_document(doc, str(compressed))
    assert compressed.exists()
    print("compress ok", compressed.stat().st_size)

    # Conversions -----------------------------------------------------------
    docx_path = OUT / "converted.docx"
    convert.pdf_to_docx(doc, str(docx_path))
    assert docx_path.exists() and docx_path.stat().st_size > 5000
    xlsx_path = OUT / "converted.xlsx"
    convert.pdf_to_xlsx(doc, str(xlsx_path))
    assert xlsx_path.exists()
    pptx_path = OUT / "converted.pptx"
    convert.pdf_to_pptx(doc, str(pptx_path))
    assert pptx_path.exists()
    txt_path = OUT / "converted.txt"
    convert.pdf_to_text(doc, str(txt_path))
    assert "星澜" in txt_path.read_text(encoding="utf-8")
    html_path = OUT / "converted.html"
    convert.pdf_to_html(doc, str(html_path))
    assert html_path.exists()
    image_dir = OUT / "images"
    images = convert.pdf_to_images(doc, str(image_dir), pages=[0, 1], dpi=72)
    assert len(images) == 2
    print("conversions ok")

    # Forms -----------------------------------------------------------------
    ops.add_form_field(
        doc, 2, "text", __import__("pymupdf").Rect(80, 700, 300, 724),
        name="reviewer", value="张三",
    )
    widgets = doc.widgets(2)
    assert any(w.name == "reviewer" for w in widgets)
    print("form ok", len(widgets))

    # Security --------------------------------------------------------------
    encrypted = OUT / "encrypted.pdf"
    ops.encrypt_to(
        doc, str(encrypted), "user123", "owner123",
        ops.permissions_value(copy=False, modify=False, print_=True),
    )
    assert encrypted.exists()
    enc = PdfDocument()
    try:
        enc.open(str(encrypted))
        raise AssertionError("password should be required")
    except Exception as exc:
        assert "密码" in str(exc) or exc.__class__.__name__ == "PasswordRequired"
    enc.open(str(encrypted), "user123")
    assert enc.page_count == doc.page_count
    print("encryption ok", encrypted.stat().st_size)

    # Office -> PDF ---------------------------------------------------------
    office_pdf = OUT / "word.pdf"
    convert.docx_to_pdf(str(docx_path), str(office_pdf))
    assert office_pdf.exists() and office_pdf.stat().st_size > 5000
    print("docx->pdf ok")

    doc.close()
    enc.close()
    print("ALL CORE TESTS PASSED")


if __name__ == "__main__":
    main()
