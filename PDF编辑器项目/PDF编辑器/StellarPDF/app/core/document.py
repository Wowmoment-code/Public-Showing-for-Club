"""PDF document model: loading, rendering, snapshots and page inspection."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pymupdf

from ..config import UNDO_DIR, ensure_dirs


class PdfError(RuntimeError):
    pass


class PasswordRequired(PdfError):
    pass


class PasswordInvalid(PdfError):
    pass


@dataclass
class TextSpan:
    page: int
    bbox: pymupdf.Rect
    text: str
    font: str
    size: float
    color: tuple[float, float, float]
    flags: int
    origin: tuple[float, float] | None = None

    @property
    def bold(self) -> bool:
        return bool(self.flags & 16) or "bold" in self.font.lower()

    @property
    def italic(self) -> bool:
        return bool(self.flags & 2) or "italic" in self.font.lower()


@dataclass
class TextBlock:
    page: int
    bbox: pymupdf.Rect
    text: str
    size: float
    color: tuple[float, float, float]
    font: str
    flags: int
    line_count: int = 1
    align: int = 0
    line_height: float = 0.0
    origin: tuple[float, float] | None = None

    @property
    def bold(self) -> bool:
        return bool(self.flags & 16) or "bold" in self.font.lower()

    @property
    def italic(self) -> bool:
        return bool(self.flags & 2) or "italic" in self.font.lower()


@dataclass
class ImageBlock:
    page: int
    bbox: pymupdf.Rect
    xref: int
    width: int
    height: int
    colorspace: str = ""


@dataclass
class AnnotInfo:
    page: int
    xref: int
    type: str
    rect: pymupdf.Rect
    content: str
    author: str
    color: tuple[float, float, float] | None
    modified: str = ""
    opacity: float = 1.0


@dataclass
class WidgetInfo:
    page: int
    xref: int
    field_type: str
    name: str
    value: Any
    rect: pymupdf.Rect
    options: list[str] = field(default_factory=list)
    is_signed: bool = False


@dataclass
class SearchHit:
    page: int
    rect: pymupdf.Rect
    text: str


class PdfDocument:
    """A thin, UI-agnostic wrapper around a PyMuPDF document."""

    def __init__(self) -> None:
        self.doc: pymupdf.Document | None = None
        self.path: str | None = None
        self.password: str | None = None
        self._encrypted = False
        self.dirty = False
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []
        self._max_undo = 12
        self.page = 0

    # ------------------------------------------------------------------ open
    @property
    def is_open(self) -> bool:
        return self.doc is not None

    def open(self, path: str | Path, password: str | None = None) -> None:
        path = str(path)
        if not os.path.isfile(path):
            raise PdfError(f"文件不存在：{path}")
        try:
            doc = pymupdf.open(path, filetype="pdf")
        except Exception as exc:  # pragma: no cover - platform messages
            raise PdfError(f"无法打开 PDF：{exc}") from exc
        was_encrypted = bool(doc.needs_pass or doc.is_encrypted)
        if doc.needs_pass:
            if not password:
                doc.close()
                raise PasswordRequired("该 PDF 受密码保护")
            if not doc.authenticate(password):
                doc.close()
                raise PasswordInvalid("密码错误，请重试")
        self._close_current()
        self.doc = doc
        self._encrypted = was_encrypted
        self.path = path
        self.password = password
        self.dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.page = 0

    def new_blank(self, width: float = 595.0, height: float = 842.0) -> None:
        self._close_current()
        self.doc = pymupdf.open()
        self.doc.new_page(width=width, height=height)
        self.path = None
        self.password = None
        self._encrypted = False
        self.dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.page = 0

    def close(self) -> None:
        self._close_current()

    def _close_current(self) -> None:
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None

    def __len__(self) -> int:
        return self.page_count

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc is not None else 0

    def require_doc(self) -> pymupdf.Document:
        if self.doc is None:
            raise PdfError("尚未打开文档")
        return self.doc

    # -------------------------------------------------------------- metadata
    @property
    def title(self) -> str:
        if self.doc is None:
            return "未打开文档"
        meta = self.doc.metadata or {}
        name = os.path.basename(self.path) if self.path else ""
        return meta.get("title") or name or "未命名文档"

    @property
    def file_name(self) -> str:
        if self.path:
            return os.path.basename(self.path)
        return "未命名文档.pdf"

    @property
    def is_encrypted(self) -> bool:
        return bool(self.doc and self._encrypted)

    @property
    def permissions(self) -> int:
        return int(self.doc.permissions) if self.doc else 0

    def metadata(self) -> dict[str, str]:
        doc = self.require_doc()
        meta = doc.metadata or {}
        keys = ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate")
        return {k: meta.get(k, "") or "" for k in keys}

    def set_metadata(self, values: dict[str, str]) -> None:
        doc = self.require_doc()
        meta = doc.metadata or {}
        meta.update({k: v for k, v in values.items() if v is not None})
        doc.set_metadata(meta)
        self.mark_dirty()

    # ----------------------------------------------------------------- render
    def page_size(self, index: int) -> tuple[float, float]:
        page = self.require_doc()[index]
        r = page.rect
        return r.width, r.height

    def render(self, index: int, zoom: float, annots: bool = True) -> pymupdf.Pixmap:
        page = self.require_doc()[index]
        zoom = max(0.05, min(8.0, float(zoom)))
        matrix = pymupdf.Matrix(zoom, zoom)
        return page.get_pixmap(matrix=matrix, alpha=False, annots=annots)

    def render_dpi(self, index: int, dpi: int = 144, annots: bool = True) -> pymupdf.Pixmap:
        return self.render(index, dpi / 72.0, annots=annots)

    # -------------------------------------------------------------- content
    def text(self, index: int) -> str:
        return self.require_doc()[index].get_text("text")

    def raw_text(self, index: int) -> dict:
        return self.require_doc()[index].get_text("dict")

    def spans(self, index: int) -> list[TextSpan]:
        page = self.require_doc()[index]
        result: list[TextSpan] = []
        try:
            data = page.get_text("dict")
        except Exception:
            return result
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if not txt.strip():
                        continue
                    color_int = int(span.get("color", 0))
                    color = (
                        ((color_int >> 16) & 255) / 255.0,
                        ((color_int >> 8) & 255) / 255.0,
                        (color_int & 255) / 255.0,
                    )
                    origin = span.get("origin")
                    result.append(
                        TextSpan(
                            page=index,
                            bbox=pymupdf.Rect(span["bbox"]),
                            text=txt,
                            font=span.get("font", ""),
                            size=float(span.get("size", 11)),
                            color=color,
                            flags=int(span.get("flags", 0)),
                            origin=(float(origin[0]), float(origin[1])) if origin else None,
                        )
                    )
        return result

    def text_blocks(self, index: int) -> list[TextBlock]:
        """Return paragraph-level text blocks for inline editing.

        WPS edits a text block rather than an isolated span; grouping lines of
        the same PyMuPDF block prevents a paragraph from being cut in half when
        the user changes one sentence.
        """
        page = self.require_doc()[index]
        result: list[TextBlock] = []
        try:
            data = page.get_text("dict")
        except Exception:
            return result
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines: list[str] = []
            line_rects: list[pymupdf.Rect] = []
            first_span: dict | None = None
            for line in block.get("lines", []):
                pieces = []
                for span in line.get("spans", []):
                    if first_span is None and span.get("text", "").strip():
                        first_span = span
                    pieces.append(span.get("text", ""))
                line_text = "".join(pieces).strip("\n")
                if line_text.strip():
                    lines.append(line_text.rstrip())
                    if line.get("bbox"):
                        line_rects.append(pymupdf.Rect(line["bbox"]))
            if not lines:
                continue
            if first_span is None:
                continue
            text = "\n".join(lines)
            color_int = int(first_span.get("color", 0))
            color = (
                ((color_int >> 16) & 255) / 255.0,
                ((color_int >> 8) & 255) / 255.0,
                (color_int & 255) / 255.0,
            )
            origin = first_span.get("origin")
            block_rect = pymupdf.Rect(block["bbox"])
            align = 0
            if len(line_rects) >= 2 and block_rect.width > 20:
                left_margins = [max(0.0, r.x0 - block_rect.x0) for r in line_rects]
                right_margins = [max(0.0, block_rect.x1 - r.x1) for r in line_rects]
                avg_left = sum(left_margins) / len(left_margins)
                avg_right = sum(right_margins) / len(right_margins)
                if min(left_margins) < 3 and min(right_margins) > block_rect.width * 0.08:
                    align = 0
                elif avg_left > block_rect.width * 0.08 and avg_right > block_rect.width * 0.08:
                    align = 1
                elif min(right_margins) < 3 and min(left_margins) > block_rect.width * 0.08:
                    align = 2
            line_height = block_rect.height / max(1, len(lines))
            result.append(
                TextBlock(
                    page=index,
                    bbox=block_rect,
                    text=text,
                    size=float(first_span.get("size", 11)),
                    color=color,
                    font=first_span.get("font", ""),
                    flags=int(first_span.get("flags", 0)),
                    line_count=max(1, len(lines)),
                    align=align,
                    line_height=line_height,
                    origin=(float(origin[0]), float(origin[1])) if origin else None,
                )
            )
        return result

    def block_at(self, index: int, point: pymupdf.Point) -> TextBlock | None:
        candidates = [b for b in self.text_blocks(index) if b.bbox.contains(point)]
        if not candidates:
            return None
        # Prefer the tightest paragraph under the cursor.
        return min(candidates, key=lambda b: b.bbox.width * b.bbox.height)

    def words(self, index: int) -> list[tuple[float, float, float, float, str]]:
        page = self.require_doc()[index]
        return [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]

    def images(self, index: int) -> list[ImageBlock]:
        page = self.require_doc()[index]
        out: list[ImageBlock] = []
        for info in page.get_image_info(xrefs=True):
            xref = int(info.get("xref", 0) or 0)
            if xref <= 0:
                continue
            bbox = pymupdf.Rect(info.get("bbox", (0, 0, 0, 0)))
            out.append(
                ImageBlock(
                    page=index,
                    bbox=bbox,
                    xref=xref,
                    width=int(info.get("width", 0)),
                    height=int(info.get("height", 0)),
                    colorspace=str(info.get("colorspace", "")),
                )
            )
        return out

    def annotations(self, index: int) -> list[AnnotInfo]:
        page = self.require_doc()[index]
        out: list[AnnotInfo] = []
        for annot in page.annots() or []:
            try:
                info = annot.info or {}
                color = annot.colors.get("stroke") if annot.colors else None
                out.append(
                    AnnotInfo(
                        page=index,
                        xref=annot.xref,
                        type=self._annot_type_name(annot.type),
                        rect=pymupdf.Rect(annot.rect),
                        content=info.get("content", "") or "",
                        author=info.get("title", "") or "",
                        color=color,
                        modified=info.get("modDate", "") or "",
                        opacity=float(annot.opacity or 1.0),
                    )
                )
            except Exception:
                continue
        return out

    def all_annotations(self) -> list[AnnotInfo]:
        out: list[AnnotInfo] = []
        for i in range(self.page_count):
            out.extend(self.annotations(i))
        return out

    @staticmethod
    def _annot_type_name(value: Any) -> str:
        names = {
            pymupdf.PDF_ANNOT_HIGHLIGHT: "高亮",
            pymupdf.PDF_ANNOT_UNDERLINE: "下划线",
            pymupdf.PDF_ANNOT_STRIKE_OUT: "删除线",
            pymupdf.PDF_ANNOT_SQUIGGLY: "波浪线",
            pymupdf.PDF_ANNOT_TEXT: "文本注释",
            pymupdf.PDF_ANNOT_FREE_TEXT: "文本框",
            pymupdf.PDF_ANNOT_INK: "手绘",
            pymupdf.PDF_ANNOT_SQUARE: "矩形",
            pymupdf.PDF_ANNOT_CIRCLE: "椭圆",
            pymupdf.PDF_ANNOT_LINE: "线条",
            pymupdf.PDF_ANNOT_STAMP: "图章",
            pymupdf.PDF_ANNOT_POLYGON: "多边形",
            pymupdf.PDF_ANNOT_REDACT: "密文",
            pymupdf.PDF_ANNOT_FILE_ATTACHMENT: "附件",
        }
        try:
            return names.get(value, f"注释 {value}")
        except Exception:
            return "注释"

    def widgets(self, index: int | None = None) -> list[WidgetInfo]:
        doc = self.require_doc()
        pages = range(self.page_count) if index is None else [index]
        out: list[WidgetInfo] = []
        for pno in pages:
            page = doc[pno]
            for widget in page.widgets() or []:
                try:
                    out.append(
                        WidgetInfo(
                            page=pno,
                            xref=widget.xref,
                            field_type=widget.field_type_string or "Unknown",
                            name=widget.field_name or "(未命名)",
                            value=widget.field_value,
                            rect=pymupdf.Rect(widget.rect),
                            options=list(widget.choice_values or []),
                            is_signed=bool(getattr(widget, "is_signed", False)),
                        )
                    )
                except Exception:
                    continue
        return out

    def outline(self) -> list[list[Any]]:
        doc = self.require_doc()
        try:
            return [list(row) for row in doc.get_toc(simple=True)]
        except Exception:
            return []

    def attachments(self) -> list[dict[str, Any]]:
        doc = self.require_doc()
        result: list[dict[str, Any]] = []
        try:
            names = doc.embfile_names()
        except Exception:
            return result
        for name in names:
            try:
                info = doc.embfile_info(name) or {}
                result.append({"name": name, "info": info, "size": info.get("size", 0)})
            except Exception:
                result.append({"name": name, "info": {}, "size": 0})
        return result

    def search(self, query: str, limit: int = 500) -> list[SearchHit]:
        if not query:
            return []
        doc = self.require_doc()
        hits: list[SearchHit] = []
        for pno in range(self.page_count):
            try:
                for rect in doc[pno].search_for(query):
                    hits.append(SearchHit(pno, pymupdf.Rect(rect), query))
                    if len(hits) >= limit:
                        return hits
            except Exception:
                continue
        return hits

    def all_text(self, max_chars: int = 400000) -> str:
        chunks: list[str] = []
        total = 0
        for pno in range(self.page_count):
            t = self.text(pno)
            chunks.append(t)
            total += len(t)
            if total >= max_chars:
                break
        return "\n".join(chunks)

    # -------------------------------------------------------------- undo/save
    def checkpoint(self) -> None:
        if self.doc is None:
            return
        try:
            data = self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        except Exception:
            try:
                data = self.doc.tobytes(garbage=0, deflate=False)
            except Exception:
                return
        self.undo_stack.append(data)
        if len(self.undo_stack) > self._max_undo:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def mark_dirty(self) -> None:
        self.dirty = True

    def _reload_bytes(self, data: bytes) -> None:
        doc = pymupdf.open(stream=data, filetype="pdf")
        encrypted = bool(doc.needs_pass or doc.is_encrypted)
        if doc.needs_pass:
            if not self.password or not doc.authenticate(self.password):
                doc.close()
                raise PdfError("无法恢复撤销快照（密码验证失败）")
        self._encrypted = encrypted
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = doc
        self.page = min(self.page, max(0, self.page_count - 1))
        self.dirty = True

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self) -> bool:
        if not self.undo_stack or self.doc is None:
            return False
        try:
            current = self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        except Exception:
            current = None
        target = self.undo_stack.pop()
        if current is not None:
            self.redo_stack.append(current)
        self._reload_bytes(target)
        return True

    def redo(self) -> bool:
        if not self.redo_stack or self.doc is None:
            return False
        try:
            current = self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        except Exception:
            current = None
        target = self.redo_stack.pop()
        if current is not None:
            self.undo_stack.append(current)
        self._reload_bytes(target)
        return True

    def save(self, target: str | Path | None = None) -> str:
        doc = self.require_doc()
        target_path = str(target or self.path or "")
        if not target_path:
            raise PdfError("请选择保存位置")
        target_path = os.path.abspath(target_path)
        if not target_path.lower().endswith(".pdf"):
            target_path += ".pdf"
        folder = os.path.dirname(target_path) or "."
        os.makedirs(folder, exist_ok=True)
        ensure_dirs()
        fd, tmp = tempfile.mkstemp(prefix="stellar_save_", suffix=".pdf", dir=str(UNDO_DIR))
        os.close(fd)
        password = self.password
        old_path = self.path
        moved = False
        try:
            try:
                doc.subset_fonts()
            except Exception:
                pass
            encryption = pymupdf.PDF_ENCRYPT_KEEP if self._encrypted else pymupdf.PDF_ENCRYPT_NONE
            doc.save(
                tmp,
                garbage=4,
                deflate=True,
                clean=True,
                encryption=encryption,
            )
            # Release the source file before atomically replacing it.  On
            # Windows an open PDF keeps a read handle which blocks os.replace.
            doc.close()
            self.doc = None
            if os.path.exists(target_path):
                os.replace(tmp, target_path)
            else:
                shutil.move(tmp, target_path)
            moved = True
            reopened = pymupdf.open(target_path)
            encrypted = bool(reopened.needs_pass or reopened.is_encrypted)
            if reopened.needs_pass and password and not reopened.authenticate(password):
                reopened.close()
                raise PdfError("保存成功，但重新打开时密码验证失败")
            self._encrypted = encrypted
            self.doc = reopened
            self.path = target_path
            self.dirty = False
            if old_path != target_path:
                self.undo_stack.clear()
                self.redo_stack.clear()
            return target_path
        except Exception:
            # Best effort: reopen whichever file is intact so the editor does
            # not lose the working document after a failed save.
            if self.doc is None and old_path and os.path.exists(old_path):
                try:
                    recovered = pymupdf.open(old_path)
                    if recovered.needs_pass and password and not recovered.authenticate(password):
                        recovered.close()
                    else:
                        self.doc = recovered
                except Exception:
                    pass
            raise
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def export(self, target: str | Path, **kwargs: Any) -> str:
        doc = self.require_doc()
        target = str(target)
        if not target.lower().endswith(".pdf"):
            target += ".pdf"
        options: dict[str, Any] = dict(garbage=3, deflate=True)
        options.update(kwargs)
        doc.save(target, **options)
        return target

    # ------------------------------------------------------------- page utils
    def page_label(self, index: int) -> str:
        try:
            label = self.require_doc()[index].get_label()
            return label or str(index + 1)
        except Exception:
            return str(index + 1)

    def page_rotation(self, index: int) -> int:
        return int(self.require_doc()[index].rotation)

    def font_list(self) -> list[str]:
        doc = self.require_doc()
        fonts: set[str] = set()
        for pno in range(min(self.page_count, 50)):
            for f in doc[pno].get_fonts(full=True):
                if len(f) >= 4:
                    fonts.add(str(f[3]))
        return sorted(fonts)

    def close(self) -> None:
        self._close_current()
        self.path = None
        self.password = None
        self._encrypted = False
