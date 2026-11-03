"""Extended tests for security, Office conversion, AI, compare, and image tools."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = ROOT / "test_output" / "features"
DEMO = ROOT / "sample" / "欢迎使用星澜PDF.pdf"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    from app.core import ai, compare, convert, operations as ops
    from app.core.document import PdfDocument, PdfError

    # AI -------------------------------------------------------------------
    text = "星澜 PDF 支持直接编辑文字。用户双击文字即可修改内容。\n" \
           "批注工具包括高亮、下划线和便签。所有处理都在本地完成，文件不会上传。\n" \
           "结论：星澜 PDF 适合离线办公和合同审阅。"
    summary = ai.summarize(text, 3)
    assert "摘要" in summary
    words = ai.keywords(text, 8)
    assert words
    answer = ai.answer_question(text, "支持哪些批注工具？")
    assert "高亮" in answer.text
    print("AI ok", words[:3])

    # Compare --------------------------------------------------------------
    doc = PdfDocument()
    doc.open(DEMO)
    other = OUT / "other.pdf"
    shutil.copy(DEMO, other)
    other_doc = pymupdf.open(other)
    other_doc[2].insert_text((60, 700), "A new comparison line.", fontsize=12)
    other_doc.saveIncr()
    other_doc.close()
    result = compare.compare_texts(doc, str(other))
    assert "文档比较结果" in result
    print("compare ok", result.splitlines()[3])

    # Image replace/delete -------------------------------------------------
    image_pdf = OUT / "image.pdf"
    image_doc = pymupdf.open()
    page = image_doc.new_page()
    img_path = OUT / "one.png"
    Image.new("RGB", (400, 240), "#2F6BFF").save(img_path)
    page.insert_image(pymupdf.Rect(100, 100, 400, 280), filename=str(img_path))
    image_doc.save(image_pdf)
    image_doc.close()
    image_model = PdfDocument()
    image_model.open(image_pdf)
    images = image_model.images(0)
    assert images, "image block missing"
    replacement = OUT / "two.png"
    Image.new("RGB", (400, 240), "#18A66F").save(replacement)
    ops.replace_image(image_model, 0, images[0].xref, str(replacement))
    image_model.save(OUT / "replaced.pdf")
    assert (OUT / "replaced.pdf").exists()
    image_model.open(image_pdf)
    images = image_model.images(0)
    ops.delete_image(image_model, 0, images[0].xref)
    assert not image_model.images(0)
    image_model.close()
    print("image replace/delete ok")

    # Image PDF and Office to PDF -----------------------------------------
    images_pdf = OUT / "images.pdf"
    convert.images_to_pdf([str(img_path), str(replacement)], str(images_pdf), page_mode="a4")
    assert images_pdf.exists()
    assert len(pymupdf.open(images_pdf)) == 2
    print("images->pdf ok")

    docx_path = OUT / "word.docx"
    convert.pdf_to_docx(doc, str(docx_path))
    docx_pdf = OUT / "from_word.pdf"
    convert.docx_to_pdf(str(docx_path), str(docx_pdf))
    assert docx_pdf.exists()
    xlsx_path = OUT / "sheet.xlsx"
    convert.pdf_to_xlsx(doc, str(xlsx_path))
    xlsx_pdf = OUT / "from_excel.pdf"
    convert.xlsx_to_pdf(str(xlsx_path), str(xlsx_pdf))
    assert xlsx_pdf.exists()
    pptx_path = OUT / "deck.pptx"
    convert.pdf_to_pptx(doc, str(pptx_path), pages=[0, 1], dpi=72)
    pptx_pdf = OUT / "from_ppt.pdf"
    convert.pptx_to_pdf(str(pptx_path), str(pptx_pdf))
    assert pptx_pdf.exists()
    print("office conversions ok")

    # Security permissions -------------------------------------------------
    encrypted = OUT / "secure.pdf"
    ops.encrypt_to(
        doc, str(encrypted), "user", "owner",
        ops.permissions_value(print_=False, copy=False, modify=False),
    )
    opened = PdfDocument()
    opened.open(str(encrypted), "user")
    assert opened.is_encrypted
    opened.close()
    decrypted = OUT / "decrypted.pdf"
    ops.decrypt_copy(str(encrypted), str(decrypted), "owner")
    check = PdfDocument()
    check.open(str(decrypted))
    assert not check.is_encrypted
    check.close()
    permissions = OUT / "permissions.pdf"
    ops.update_permissions_copy(
        str(encrypted), str(permissions), "owner",
        ops.permissions_value(print_=True, copy=False, modify=False),
    )
    assert permissions.exists()
    print("security ok")

    # Watermark / annotation flatten --------------------------------------
    ops.add_watermark_text(doc, "内部资料", size=52, opacity=0.16, angle=37, tiled=True)
    watermark_pdf = OUT / "watermark.pdf"
    doc.save(str(watermark_pdf))
    rendered = pymupdf.open(watermark_pdf)
    pix = rendered[0].get_pixmap(matrix=pymupdf.Matrix(1, 1))
    pix.save(str(OUT / "watermark_preview.png"))
    rendered.close()
    doc.open(DEMO)
    ops.add_text_markup(doc, 2, [pymupdf.Rect(60, 180, 300, 198)], "highlight", (1, 0.8, 0.2))
    ops.flatten_annotations(doc)
    assert not doc.all_annotations()
    print("watermark/flatten ok")

    # Encryption size / save ------------------------------------------------
    doc.close()
    print("ALL FEATURE TESTS PASSED")


if __name__ == "__main__":
    main()
