"""
文本分块工具。
"""

from __future__ import annotations

import re
from typing import List


def split_content(content: str, max_chars: int, overlap_chars: int) -> List[str]:
    text = (content or "").strip()
    if not text:
        return []
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            step = max_chars - overlap_chars if max_chars > overlap_chars else max_chars
            if step <= 0:
                chunks.append(para[:max_chars])
                continue
            start = 0
            while start < len(para):
                end = start + max_chars
                chunks.append(para[start:end])
                start += step
            continue
        if not current:
            current = para
            continue
        if len(current) + 2 + len(para) <= max_chars:
            current = current + "\n\n" + para
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)

    if overlap_chars > 0 and len(chunks) > 1:
        orig = list(chunks)
        overlapped: List[str] = []
        for idx, chunk in enumerate(orig):
            if idx == 0:
                overlapped.append(chunk)
                continue
            overlap = orig[idx - 1][-overlap_chars:] if overlap_chars > 0 else ""
            if overlap and not chunk.startswith(overlap):
                combined = overlap + "\n" + chunk
                if len(combined) > max_chars:
                    combined = combined[-max_chars:]
                overlapped.append(combined)
            else:
                overlapped.append(chunk)
        chunks = overlapped

    return chunks
