import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

_PUNCT_RE = re.compile(r"[\\s，。；;、,:：()（）\\[\\]{}<>《》\"'“”‘’]")
_DIRECTIONAL_WORDS = (
    "提高",
    "降低",
    "增加",
    "减少",
    "促进",
    "抑制",
    "改善",
    "恶化",
    "增强",
    "减弱",
    "延长",
    "缩短",
    "提前",
    "推迟",
    "增产",
    "减产",
    "上升",
    "下降",
    "increase",
    "decrease",
    "improve",
    "reduce",
    "promote",
    "inhibit",
    "enhance",
    "suppress",
    "decline",
    "drop",
    "rise",
)
_GENERIC_TERMS = {
    "防治",
    "促进",
    "提高",
    "降低",
    "增加",
    "减少",
    "改善",
    "增产",
    "减产",
    "抑制",
    "控制",
    "预防",
    "治理",
    "control",
    "prevent",
    "management",
    "treatment",
    "increase",
    "decrease",
    "improve",
    "reduce",
    "promote",
    "inhibit",
}


def normalize_event_name(name: str) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if not text:
        return ""
    text = _PUNCT_RE.sub("", text)
    return text


def _has_directional(text: str) -> bool:
    if not text:
        return False
    return any(word in text for word in _DIRECTIONAL_WORDS)


def _is_generic_term(text: str) -> bool:
    if not text:
        return False
    return text in _GENERIC_TERMS


def _count_candidate_hits(norm: str, candidates: List[str]) -> int:
    hits = 0
    for cand in candidates:
        cand_norm = normalize_event_name(cand)
        if not cand_norm:
            continue
        if len(cand_norm) <= 2 and _is_generic_term(cand_norm):
            continue
        if cand_norm in norm:
            hits += 1
            if hits >= 2:
                return hits
    return hits


def _event_name_from_payload(event: dict) -> str:
    for key in ("event", "description", "trigger", "event_id"):
        value = event.get(key)
        if value:
            return str(value).strip()
    return ""


def load_event_names(doc_dir: Path, doc_id: str) -> List[str]:
    pattern = f"domain_event_prompt_results_{doc_id}_*.json"
    matches = sorted(doc_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        matches = sorted(
            doc_dir.glob("domain_event_prompt_results_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not matches:
        return []
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return []
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return []
    names: List[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        name = _event_name_from_payload(event)
        if name:
            names.append(name)
    return names


def align_event_name(name: str, candidates: List[str], evidence: Optional[str] = None) -> str:
    if not name or not candidates:
        return name
    norm = normalize_event_name(name)
    if not norm:
        return name
    if _count_candidate_hits(norm, candidates) >= 2:
        return name
    best: Optional[Tuple[str, int]] = None
    name_has_dir = _has_directional(norm)
    for cand in candidates:
        cand_norm = normalize_event_name(cand)
        if not cand_norm:
            continue
        if cand_norm == norm:
            return cand
        if cand_norm in norm or norm in cand_norm:
            if len(cand_norm) <= 2 and _is_generic_term(cand_norm) and len(norm) > len(cand_norm):
                continue
            if name_has_dir and not _has_directional(cand_norm):
                continue
            score = len(cand_norm)
            if best is None or score > best[1]:
                best = (cand, score)
    if best:
        return best[0]
    if not evidence:
        return name
    evidence_norm = normalize_event_name(evidence)
    if not evidence_norm:
        return name
    best = None
    for cand in candidates:
        cand_norm = normalize_event_name(cand)
        if not cand_norm or cand_norm not in evidence_norm:
            continue
        if len(cand_norm) <= 2 and _is_generic_term(cand_norm) and len(norm) > len(cand_norm):
            continue
        if name_has_dir and not _has_directional(cand_norm):
            continue
        overlap = len(set(cand_norm) & set(norm))
        if overlap < 2:
            continue
        score = (overlap, len(cand_norm))
        if best is None or score > (best[1], best[2]):
            best = (cand, overlap, len(cand_norm))
    return best[0] if best else name
