"""Offline OCR powered by RapidOCR (ONNX Runtime)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import pymupdf

from ..config import cjk_font_file
from .document import PdfDocument


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: tuple[float, float, float, float]  # PDF points, unrotated page space
    page: int = 0


class OcrEngine:
    _instance: "OcrEngine | None" = None
    _engine = None

    @classmethod
    def instance(cls) -> "OcrEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        if self._engine is not None:
            return self._engine
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        return self._engine

    @staticmethod
    def _pix_to_bgr(pix: pymupdf.Pixmap) -> np.ndarray:
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            arr = arr[:, :, :3]
        if pix.n == 1:
            arr = np.repeat(arr, 3, axis=2)
        # MuPDF gives RGB; RapidOCR/OpenCV expects BGR.
        return np.ascontiguousarray(arr[:, :, ::-1])

    def recognize_pixmap(self, pix: pymupdf.Pixmap, page_rotation: int = 0) -> list[tuple[str, float, tuple]]:
        engine = self._load()
        result, _ = engine(self._pix_to_bgr(pix))
        out: list[tuple[str, float, tuple]] = []
        if not result:
            return out
        scale = 72.0 / max(1, pix.xres if hasattr(pix, "xres") else 72)
        # pix.xres can be zero for some documents; derive from dimensions using
        # the caller's dpi instead.  The caller patches coordinates afterwards.
        for item in result:
            try:
                box, text, score = item[0], str(item[1]), float(item[2])
            except Exception:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            out.append((text, score, (min(xs), min(ys), max(xs), max(ys))))
        return out

    def ocr_page(
        self,
        doc: PdfDocument,
        page_index: int,
        *,
        dpi: int = 200,
    ) -> list[OcrLine]:
        page = doc.require_doc()[page_index]
        pix = doc.render_dpi(page_index, dpi=dpi)
        engine = self._load()
        result, _ = engine(self._pix_to_bgr(pix))
        lines: list[OcrLine] = []
        if not result:
            return lines
        scale = 72.0 / dpi
        for item in result:
            try:
                box, text, score = item[0], str(item[1]), float(item[2])
            except Exception:
                continue
            xs = [float(p[0]) * scale for p in box]
            ys = [float(p[1]) * scale for p in box]
            rect = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
            # The pixmap is rendered in rotated display space.  Text extraction,
            # annotations and insert_text all use unrotated page space.
            if page.rotation:
                rect = rect * page.derotation_matrix
            lines.append(
                OcrLine(
                    text=text,
                    confidence=score,
                    box=(rect.x0, rect.y0, rect.x1, rect.y1),
                    page=page_index,
                )
            )
        return lines

    def ocr_document(
        self,
        doc: PdfDocument,
        *,
        pages: Sequence[int] | None = None,
        dpi: int = 200,
        progress: Callable[[int, str], None] | None = None,
    ) -> list[OcrLine]:
        page_range = list(range(doc.page_count)) if pages is None else list(pages)
        all_lines: list[OcrLine] = []
        for i, pno in enumerate(page_range):
            if progress:
                progress(int(i / max(1, len(page_range)) * 100), f"识别第 {pno + 1} 页")
            all_lines.extend(self.ocr_page(doc, pno, dpi=dpi))
        if progress:
            progress(100, "识别完成")
        return all_lines

    @staticmethod
    def add_text_layer(doc: PdfDocument, lines: Sequence[OcrLine]) -> None:
        font_path = cjk_font_file()
        doc.checkpoint()
        by_page: dict[int, list[OcrLine]] = {}
        for line in lines:
            by_page.setdefault(line.page, []).append(line)
        for pno, page_lines in by_page.items():
            page = doc.require_doc()[pno]
            for line in page_lines:
                text = line.text.strip()
                if not text:
                    continue
                x0, y0, x1, y1 = line.box
                height = max(4.0, y1 - y0)
                size = max(4.5, min(48.0, height * 0.86))
                kwargs = dict(
                    fontsize=size,
                    fontname="STLX",
                    color=(0, 0, 0),
                    render_mode=3,
                )
                if font_path:
                    kwargs["fontfile"] = font_path
                try:
                    page.insert_text((x0, y1 - height * 0.12), text, **kwargs)
                except Exception:
                    continue
        doc.mark_dirty()

    @staticmethod
    def export_text(lines: Sequence[OcrLine], target: str) -> str:
        by_page: dict[int, list[OcrLine]] = {}
        for line in lines:
            by_page.setdefault(line.page, []).append(line)
        chunks: list[str] = []
        for pno in sorted(by_page):
            chunks.append(f"===== 第 {pno + 1} 页 =====")
            chunks.extend(line.text for line in by_page[pno])
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("\n".join(chunks))
        return target

    @staticmethod
    def make_searchable_copy(doc: PdfDocument, lines: Sequence[OcrLine], target: str) -> str:
        data = doc.require_doc().tobytes(garbage=0)
        work = pymupdf.open(stream=data, filetype="pdf")
        try:
            # Use a temporary PdfDocument facade so add_text_layer can checkpoint.
            from .document import PdfDocument as _Doc

            temp = _Doc()
            temp.doc = work
            temp.path = None
            temp.password = None
            OcrEngine.add_text_layer(temp, lines)
            work.save(target, garbage=3, deflate=True)
        finally:
            work.close()
        return target
