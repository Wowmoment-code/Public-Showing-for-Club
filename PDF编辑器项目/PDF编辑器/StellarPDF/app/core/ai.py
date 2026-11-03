"""Small, fully offline language tools for the AI ribbon tab.

These are deliberately local algorithms (extractive summarisation, keyword
scoring and passage retrieval) so documents never leave the computer.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[\u4e00-\u9fff]{2,8}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

STOPWORDS = {
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "与", "及", "或", "为", "对", "从", "以", "被", "把", "而",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
    "was", "were", "be", "as", "at", "by", "from", "that", "this", "it", "we", "you",
    "pdf", "文档", "可以", "进行", "通过", "以及", "相关", "如下", "其中", "如果", "因为",
    "所以", "但是", "并且", "我们", "他们", "以及", "需要", "使用", "支持", "功能",
}


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    # Merge tiny fragments into their predecessor.
    merged: list[str] = []
    for part in parts:
        if merged and len(part) < 8 and len(merged[-1]) < 120:
            merged[-1] += part
        else:
            merged.append(part)
    return merged


def tokens(text: str) -> list[str]:
    result: list[str] = []
    for word in _WORD_RE.findall(text):
        lowered = word.lower()
        if lowered in STOPWORDS or len(lowered) < 2:
            continue
        result.append(lowered)
    # Add CJK character bigrams for better coverage of segmentation-less text.
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for i in range(len(run) - 1):
            bigram = run[i : i + 2]
            if bigram not in STOPWORDS:
                result.append(bigram)
    return result


def _sentence_scores(text: str) -> list[tuple[str, float]]:
    sents = sentences(text)
    if not sents:
        return []
    freq = Counter(tokens(text))
    if not freq:
        return [(s, 0.0) for s in sents]
    max_freq = max(freq.values())
    weights = {k: v / max_freq for k, v in freq.items()}
    scores: list[tuple[str, float]] = []
    for idx, sent in enumerate(sents):
        toks = tokens(sent)
        if not toks:
            scores.append((sent, 0.0))
            continue
        score = sum(weights.get(t, 0) for t in toks) / math.sqrt(len(toks) + 2)
        # Slight preference for earlier and longer sentences.
        position = 1.0 + max(0.0, 0.20 - idx * 0.003)
        length = min(1.25, max(0.8, len(sent) / 42))
        scores.append((sent, score * position * length))
    return scores


def summarize(text: str, max_sentences: int = 6) -> str:
    text = text.strip()
    if not text:
        return "文档中没有可提取的文字。若为扫描件，请先使用“OCR 文字识别”。"
    scored = _sentence_scores(text)
    top = sorted(scored, key=lambda x: x[1], reverse=True)[: max(1, max_sentences)]
    order = {id(s): i for i, s in enumerate(scored)}
    top_sorted = sorted(top, key=lambda x: order.get(id(x[0]), 0))
    lines = [f"• {s.strip()}" for s, _ in top_sorted if s.strip()]
    return "文档摘要\n\n" + "\n".join(lines) + f"\n\n（共分析 {len(scored)} 个句子，本地生成）"


def keywords(text: str, limit: int = 15) -> list[tuple[str, int]]:
    freq = Counter(tokens(text))
    # Prefer meaningful CJK terms and longer Latin words.
    ranked = []
    for word, count in freq.items():
        if len(word) < 2:
            continue
        if _CJK_RE.search(word):
            weight = count * (1.2 if len(word) >= 3 else 0.7)
        else:
            weight = count * min(2.0, len(word) / 5)
        ranked.append((word, count, weight))
    ranked.sort(key=lambda x: x[2], reverse=True)
    return [(word, count) for word, count, _ in ranked[:limit]]


@dataclass
class Answer:
    text: str
    sources: list[str]


def answer_question(text: str, question: str, max_sources: int = 3) -> Answer:
    sents = sentences(text)
    if not sents:
        return Answer("没有可用于回答的文字。扫描版 PDF 请先执行 OCR。", [])
    q_tokens = set(tokens(question))
    if not q_tokens:
        return Answer("请输入更具体的问题，例如“这份文档的主要结论是什么？”", [])
    scored: list[tuple[float, str]] = []
    for sent in sents:
        s_tokens = set(tokens(sent))
        overlap = len(q_tokens & s_tokens)
        if not overlap:
            continue
        score = overlap / math.sqrt(len(s_tokens) + 2)
        if any(k in sent for k in ("因此", "结论", "总之", "综上", "建议", "注意")):
            score *= 1.18
        scored.append((score, sent))
    if not scored:
        return Answer(
            "文档中没有找到与该问题直接相关的内容。可以换一个关键词，或先用 AI 摘要了解全文。",
            [],
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    sources = [s for _, s in scored[:max_sources]]
    body = "\n\n".join(f"• {s}" for s in sources)
    return Answer(f"根据文档内容，可以找到以下相关表述：\n\n{body}", sources)


def build_outline(text: str, limit: int = 12) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if (
            len(line) <= 36
            and not line.endswith(("。", "，", "；", "："))
            and (
                re.match(r"^(第[一二三四五六七八九十百\d]+[章节部分篇]|[一二三四五六七八九十]+、|\d+[\.、])", line)
                or line.isupper()
            )
        ):
            lines.append(line)
        if len(lines) >= limit:
            break
    if not lines:
        return "未检测到明确的章节标题。"
    return "文档结构\n\n" + "\n".join(lines)


def translation_notice() -> str:
    return (
        "星澜 PDF 的智能摘要、问答与关键词功能完全在本地运行，文件不会上传。\n\n"
        "全文翻译需要联网的语言服务，本离线版本不内置第三方翻译接口。"
        "你可以复制选中的文字，在系统的翻译工具中继续处理。"
    )
