"""Verify the bundled offline OCR engine."""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "test_output"
OUT.mkdir(exist_ok=True)

from app.core.document import PdfDocument  # noqa: E402
from app.core.ocr import OcrEngine  # noqa: E402


def main() -> None:
    image = Image.new("RGB", (1200, 640), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 56)
    draw.text((80, 120), "星澜 PDF 文字识别测试", font=font, fill="#111111")
    draw.text((80, 240), "离线 OCR 支持中文与 English 2026", font=font, fill="#222222")
    draw.text((80, 360), "合同编号：SL-2026-001", font=font, fill="#333333")
    image.save(OUT / "ocr_sample.png")

    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=320)
    page.insert_image(page.rect, filename=str(OUT / "ocr_sample.png"))
    scanned = OUT / "scanned.pdf"
    pdf.save(scanned)
    pdf.close()

    doc = PdfDocument()
    doc.open(scanned)
    engine = OcrEngine.instance()
    lines = engine.ocr_document(doc, dpi=220, progress=lambda p, m: print(p, m))
    for line in lines:
        print(f"{line.confidence:.2f}\t{line.text}")
    assert any("星澜" in line.text for line in lines), "Chinese OCR failed"
    assert any("2026" in line.text for line in lines), "digit OCR failed"
    target = OUT / "ocr_searchable.pdf"
    engine.make_searchable_copy(doc, lines, str(target))
    check = pymupdf.open(target)
    text = check[0].get_text()
    print("extracted:", repr(text[:120]))
    assert "星澜" in text
    check.close()
    doc.close()
    print("OCR TEST PASSED")


if __name__ == "__main__":
    main()
