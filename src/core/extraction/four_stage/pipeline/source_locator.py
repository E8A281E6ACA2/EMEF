"""
Source location helpers: map evidence text to section + paragraph.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import hierarchy_utils


_DOC_TITLE_PATTERN = re.compile(r"^#{1,6}\s+(.+)$")


def _split_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    return paragraphs


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", "", text)


def _extract_doc_title(content: str, fallback: str) -> str:
    for line in (content or "").splitlines():
        text = line.strip()
        if not text:
            continue
        match = _DOC_TITLE_PATTERN.match(text)
        if match:
            title = match.group(1).strip()
            if title:
                return title
    return fallback


def build_section_index(markdown: str, doc_id: str) -> List[Dict[str, Any]]:
    sections, _, _, _ = hierarchy_utils.build_section_tree(markdown or "", doc_id)
    doc_title = _extract_doc_title(markdown or "", doc_id)
    if doc_title:
        for section in sections:
            if getattr(section, "title", "") == "正文":
                section.title = doc_title
                break
    return build_section_index_from_sections(sections)


def build_section_index_from_sections(sections: List[Any]) -> List[Dict[str, Any]]:
    index: List[Dict[str, Any]] = []
    for section in sections or []:
        content = str(getattr(section, "content", "") or "").strip()
        if not content:
            continue
        paragraphs = _split_paragraphs(content)
        index.append(
            {
                "id": str(getattr(section, "id", "") or ""),
                "title": str(getattr(section, "title", "") or ""),
                "content": content,
                "content_norm": _normalize_text(content),
                "paragraphs": paragraphs,
                "paragraphs_norm": [_normalize_text(p) for p in paragraphs],
            }
        )
    return index


def _locate_in_paragraphs(
    text: str, text_norm: str, paragraphs: List[str], paragraphs_norm: List[str]
) -> Optional[int]:
    if not text:
        return None
    for idx, para in enumerate(paragraphs, start=1):
        if text in para:
            return idx
    if text_norm:
        for idx, para_norm in enumerate(paragraphs_norm, start=1):
            if text_norm in para_norm:
                return idx
    return None


def locate_text(
    text: str, section_index: List[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    raw = str(text or "").strip()
    if not raw:
        return None, None, None
    raw_norm = _normalize_text(raw)
    for section in section_index or []:
        content = section.get("content") or ""
        if not content:
            continue
        if raw in content or (raw_norm and raw_norm in (section.get("content_norm") or "")):
            para_idx = _locate_in_paragraphs(
                raw,
                raw_norm,
                section.get("paragraphs") or [],
                section.get("paragraphs_norm") or [],
            )
            return section.get("id") or None, section.get("title") or None, para_idx
    return None, None, None


def annotate_items(
    items: List[Dict[str, Any]],
    section_index: List[Dict[str, Any]],
    evidence_key: Optional[str] = "evidence",
    name_key: Optional[str] = None,
) -> int:
    if not items:
        return 0
    unmatched = 0
    for item in items:
        if not isinstance(item, dict):
            unmatched += 1
            continue
        text = ""
        if evidence_key and item.get(evidence_key):
            text = str(item.get(evidence_key) or "").strip()
        if not text and name_key and item.get(name_key):
            text = str(item.get(name_key) or "").strip()
        if not text:
            unmatched += 1
            continue
        section_id, section_title, paragraph_index = locate_text(text, section_index)
        locate_method = None
        if evidence_key and item.get(evidence_key):
            locate_method = "evidence"
        elif name_key and item.get(name_key):
            locate_method = "name"
        if section_id:
            item.setdefault("section_id", section_id)
            item.setdefault("section_title", section_title or "")
            if paragraph_index is not None:
                item.setdefault("paragraph_index", paragraph_index)
            item.setdefault("source_located", True)
            if locate_method:
                item.setdefault("locate_method", locate_method)
        else:
            item.setdefault("source_located", False)
            if locate_method:
                item.setdefault("locate_method", locate_method)
            unmatched += 1
    return unmatched
