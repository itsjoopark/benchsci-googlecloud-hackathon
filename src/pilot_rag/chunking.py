from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_type: str
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def chunk_document(doc_id: str, doc_type: str, text: str, max_chars: int, overlap_chars: int) -> list[Chunk]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [Chunk(f"{doc_id}#0", doc_id, doc_type, 0, text, 0, len(text))]

    sentences = split_sentences(text)
    chunks: list[Chunk] = []
    cur = ""
    start = 0
    idx = 0

    for sent in sentences:
        candidate = f"{cur} {sent}".strip()
        if cur and len(candidate) > max_chars:
            end = start + len(cur)
            chunks.append(Chunk(f"{doc_id}#{idx}", doc_id, doc_type, idx, cur, start, end))
            idx += 1
            overlap = cur[max(0, len(cur) - overlap_chars):]
            start = max(0, end - len(overlap))
            cur = f"{overlap} {sent}".strip()
        else:
            cur = candidate

    if cur:
        end = start + len(cur)
        chunks.append(Chunk(f"{doc_id}#{idx}", doc_id, doc_type, idx, cur, start, end))

    return chunks
