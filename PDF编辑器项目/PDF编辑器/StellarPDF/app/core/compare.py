"""Simple text-level PDF comparison."""
from __future__ import annotations

import difflib
from typing import Sequence

from .document import PdfDocument


def compare_texts(left: PdfDocument, right_path: str, max_chars: int = 120000) -> str:
    try:
        import pymupdf

        right = pymupdf.open(right_path)
    except Exception as exc:
        return f"无法打开比较文件：{exc}"
    try:
        if right.needs_pass:
            return "比较文件受密码保护，暂时无法比较。"
        left_text = left.all_text(max_chars)[:max_chars]
        right_chunks: list[str] = []
        total = 0
        for i in range(len(right)):
            text = right[i].get_text("text")
            right_chunks.append(text)
            total += len(text)
            if total >= max_chars:
                break
        right_text = "\n".join(right_chunks)[:max_chars]
        left_lines = [line.strip() for line in left_text.splitlines() if line.strip()]
        right_lines = [line.strip() for line in right_text.splitlines() if line.strip()]
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
        added, removed, changed = 0, 0, 0
        details: list[str] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "insert":
                added += j2 - j1
                details.append(f"+ 新增 {j2 - j1} 行：")
                details.extend("  + " + line for line in right_lines[j1:j2][:8])
            elif tag == "delete":
                removed += i2 - i1
                details.append(f"- 删除 {i2 - i1} 行：")
                details.extend("  - " + line for line in left_lines[i1:i2][:8])
            else:
                changed += max(i2 - i1, j2 - j1)
                details.append(f"~ 修改 {max(i2 - i1, j2 - j1)} 行：")
                details.extend("  - " + line for line in left_lines[i1:i2][:5])
                details.extend("  + " + line for line in right_lines[j1:j2][:5])
        summary = [
            "文档比较结果",
            "",
            f"页数：{left.page_count} 页  →  {len(right)} 页",
            f"新增：{added} 行   删除：{removed} 行   修改：{changed} 行",
            f"相似度：{matcher.ratio() * 100:.1f}%",
            "",
        ]
        if not details:
            summary.append("两份文档的文本内容一致。")
        else:
            summary.extend(details[:120])
        return "\n".join(summary)
    finally:
        right.close()
