#!/usr/bin/env python3
"""
Fine-grained evaluation for MAKER predictions against gold labels.

Metrics:
- Slot-level micro P/R/F1 for entities, events, temporal relations, causal relations
- Argument completeness (events/temporal/causal)
- Attribute coverage (avg attrs per entity, avg args per event)
- Evidence coverage (events/temporal/causal/static relations + overall)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


_WS_RE = re.compile(r"\s+")
_RELAX_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_code_fences(text: str) -> str:
    if "```" not in text:
        return text.strip()
    lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def _extract_json_block(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _safe_json_load(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = _strip_code_fences(text)
    candidates = [cleaned]
    block = _extract_json_block(cleaned)
    if block and block != cleaned:
        candidates.append(block)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        for idx, ch in enumerate(candidate):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _load_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = _safe_json_load(_read_text(path))
    return payload if isinstance(payload, dict) else {}


def _norm(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip()
    value = _WS_RE.sub(" ", value)
    return value


def _norm_relaxed(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip().lower()
    value = _RELAX_RE.sub("", value)
    return value


def _maybe_import_lexicon():
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    try:
        from src.core.knowledge_graph.alignment.match_rules import (  # type: ignore
            load_entity_lexicon,
            resolve_lexicon_path,
        )
    except Exception:
        return None, None
    return load_entity_lexicon, resolve_lexicon_path


def _canonicalize(name: str, alias_map: Dict[str, str]) -> str:
    key = _norm_relaxed(name)
    return alias_map.get(key, name)


def _match_name(a: str, b: str, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    if not a or not b:
        return False
    a_can = _canonicalize(a, alias_map)
    b_can = _canonicalize(b, alias_map)
    a_norm = _norm_relaxed(a_can)
    b_norm = _norm_relaxed(b_can)
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    if len(a_norm) >= 2 and len(b_norm) >= 2:
        return a_norm in b_norm or b_norm in a_norm
    if mode in {"relaxed_plus", "relaxed_ultra"}:
        min_len = min(len(a_norm), len(b_norm))
        if min_len >= 3:
            ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
            if mode == "relaxed_plus":
                ok = (min_len <= 4 and ratio >= 0.9) or (min_len > 4 and ratio >= 0.85)
            else:
                ok = (min_len <= 4 and ratio >= 0.85) or (min_len > 4 and ratio >= 0.80)
            if ok:
                return True
    return False


def _normalize_rel_type(rel_type: str) -> str:
    if not rel_type:
        return ""
    t = _norm_relaxed(rel_type)
    if any(key in t for key in ["先于", "早于", "之前", "先后"]):
        return "先于"
    if any(key in t for key in ["同时", "同期", "同一时间"]):
        return "同时"
    if any(key in t for key in ["发生于", "发生在", "发生", "位于", "处于", "在"]):
        return "发生于"
    if any(key in t for key in ["开始于", "起始于", "起于"]):
        return "开始于"
    if any(key in t for key in ["结束于", "终止于", "止于"]):
        return "结束于"
    if any(key in t for key in ["期间", "持续", "历时"]):
        return "期间"
    if any(key in t for key in ["导致", "引起", "造成", "使得"]):
        return "导致"
    if any(key in t for key in ["促进", "提升", "增强", "提高"]):
        return "促进"
    if any(key in t for key in ["抑制", "降低", "减少", "削弱"]):
        return "抑制"
    if any(key in t for key in ["相关", "关联", "关系"]):
        return "相关"
    if any(key in t for key in ["目的", "旨在", "为"]):
        return "目的"
    if any(key in t for key in ["前提", "条件", "依赖"]):
        return "前提"
    if any(key in t for key in ["属于", "归属", "隶属", "是", "为"]):
        return "属于"
    if any(key in t for key in ["别名", "又称", "简称"]):
        return "别名"
    if any(key in t for key in ["包含", "包括", "组成", "构成", "由"]):
        return "包含"
    if any(key in t for key in ["位于", "分布于", "位处"]):
        return "位于"
    if any(key in t for key in ["用于", "用途", "用以", "用来"]):
        return "用于"
    if any(key in t for key in ["适用于", "适用"]):
        return "适用于"
    return t


def _get_rel_type(item: dict) -> str:
    return _norm(item.get("type") or item.get("relation_type") or "")


def _relaxed_match_entity(gold: dict, pred: dict, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    g_name = _norm(gold.get("name"))
    p_name = _norm(pred.get("name"))
    if not _match_name(g_name, p_name, alias_map, mode=mode):
        return False
    if mode == "relaxed_ultra":
        return True
    g_type = _norm_relaxed(gold.get("type") or "")
    p_type = _norm_relaxed(pred.get("type") or "")
    if g_type and p_type and g_type != p_type:
        return False
    return True


def _relaxed_match_event(gold: dict, pred: dict, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    g_trigger = _norm(gold.get("trigger") or gold.get("event") or gold.get("description") or "")
    p_trigger = _norm(pred.get("trigger") or pred.get("event") or pred.get("description") or "")
    if not _match_name(g_trigger, p_trigger, alias_map, mode=mode):
        return False
    if mode == "relaxed_ultra":
        return True
    g_cat = _norm_relaxed(gold.get("category") or "")
    p_cat = _norm_relaxed(pred.get("category") or "")
    if g_cat and p_cat and g_cat != p_cat:
        return False
    return True


def _relaxed_match_relation(gold: dict, pred: dict, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    g_source = _norm(gold.get("source"))
    g_target = _norm(gold.get("target"))
    p_source = _norm(pred.get("source"))
    p_target = _norm(pred.get("target"))
    if not (_match_name(g_source, p_source, alias_map, mode=mode) and _match_name(g_target, p_target, alias_map, mode=mode)):
        return False
    if mode == "relaxed_ultra":
        return True
    g_type = _normalize_rel_type(_get_rel_type(gold)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(gold))
    p_type = _normalize_rel_type(_get_rel_type(pred)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(pred))
    if g_type and p_type and g_type != p_type:
        return False
    return True


def _relaxed_match_temporal(gold: dict, pred: dict, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    g_source = _norm(gold.get("source_event") or gold.get("source") or "")
    g_target = _norm(gold.get("target_event") or gold.get("target_time") or gold.get("target") or "")
    p_source = _norm(pred.get("source_event") or pred.get("source") or "")
    p_target = _norm(pred.get("target_event") or pred.get("target_time") or pred.get("target") or "")
    if not (_match_name(g_source, p_source, alias_map, mode=mode) and _match_name(g_target, p_target, alias_map, mode=mode)):
        return False
    if mode == "relaxed_ultra":
        return True
    g_type = _normalize_rel_type(_get_rel_type(gold)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(gold))
    p_type = _normalize_rel_type(_get_rel_type(pred)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(pred))
    if g_type and p_type and g_type != p_type:
        return False
    return True


def _relaxed_match_causal(gold: dict, pred: dict, alias_map: Dict[str, str], mode: str = "relaxed") -> bool:
    g_cause = _norm(gold.get("cause_event") or gold.get("source_event") or "")
    g_effect = _norm(gold.get("effect_event") or gold.get("target_event") or "")
    p_cause = _norm(pred.get("cause_event") or pred.get("source_event") or "")
    p_effect = _norm(pred.get("effect_event") or pred.get("target_event") or "")
    if not (_match_name(g_cause, p_cause, alias_map, mode=mode) and _match_name(g_effect, p_effect, alias_map, mode=mode)):
        return False
    if mode == "relaxed_ultra":
        return True
    g_type = _normalize_rel_type(_get_rel_type(gold)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(gold))
    p_type = _normalize_rel_type(_get_rel_type(pred)) if mode == "relaxed_plus" else _norm_relaxed(_get_rel_type(pred))
    if g_type and p_type and g_type != p_type:
        return False
    return True


def _flatten_value(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: List[str] = []
        for v in value:
            items.extend(_flatten_value(v))
        return items
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False)]
    return [str(value)]


def _add_slot(slots: set[tuple[str, str]], key: str, value: object) -> None:
    for v in _flatten_value(value):
        norm = _norm_relaxed(v)
        if norm:
            slots.add((key, norm))


def _slots_entity(item: dict) -> set[tuple[str, str]]:
    slots: set[tuple[str, str]] = set()
    _add_slot(slots, "name", item.get("name"))
    _add_slot(slots, "type", item.get("type"))
    _add_slot(slots, "description", item.get("description"))
    for alias in item.get("aliases") or []:
        _add_slot(slots, "alias", alias)
    for k, v in (item.get("attributes") or {}).items():
        _add_slot(slots, f"attr:{k}", v)
    return slots


def _slots_event(item: dict) -> set[tuple[str, str]]:
    slots: set[tuple[str, str]] = set()
    _add_slot(slots, "category", item.get("category"))
    _add_slot(slots, "subtype", item.get("subtype"))
    _add_slot(slots, "trigger", item.get("trigger"))
    for k, v in (item.get("arguments") or {}).items():
        _add_slot(slots, f"arg:{k}", v)
    return slots


def _slots_temporal(item: dict, match_mode: str) -> set[tuple[str, str]]:
    slots: set[tuple[str, str]] = set()
    rel_type = _get_rel_type(item)
    rel_norm = _normalize_rel_type(rel_type) if match_mode in {"relaxed_plus", "relaxed_ultra"} else _norm_relaxed(rel_type)
    if rel_norm:
        slots.add(("relation_type", rel_norm))
    _add_slot(slots, "source_event", item.get("source_event") or item.get("source"))
    _add_slot(slots, "target_event", item.get("target_event"))
    _add_slot(slots, "target_time", item.get("target_time"))
    return slots


def _slots_causal(item: dict, match_mode: str) -> set[tuple[str, str]]:
    slots: set[tuple[str, str]] = set()
    rel_type = _get_rel_type(item)
    rel_norm = _normalize_rel_type(rel_type) if match_mode in {"relaxed_plus", "relaxed_ultra"} else _norm_relaxed(rel_type)
    if rel_norm:
        slots.add(("relation_type", rel_norm))
    _add_slot(slots, "cause_event", item.get("cause_event") or item.get("source_event"))
    _add_slot(slots, "effect_event", item.get("effect_event") or item.get("target_event"))
    _add_slot(slots, "logic_type", item.get("logic_type"))
    _add_slot(slots, "polarity", item.get("polarity"))
    _add_slot(slots, "strength", item.get("strength"))
    _add_slot(slots, "time_lag", item.get("time_lag"))
    _add_slot(slots, "stage", item.get("stage"))
    for v in item.get("crop") or []:
        _add_slot(slots, "crop", v)
    for v in item.get("conditions") or []:
        _add_slot(slots, "condition", v)
    for v in item.get("mechanism") or []:
        _add_slot(slots, "mechanism", v)
    return slots


def _match_pairs(
    gold_items: List[dict],
    pred_items: List[dict],
    match_fn,
    alias_map: Dict[str, str],
    match_mode: str,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    used_pred: set[int] = set()
    pairs: List[Tuple[int, int]] = []
    for gi, g in enumerate(gold_items):
        matched_pi = None
        for pi, p in enumerate(pred_items):
            if pi in used_pred:
                continue
            if match_fn(g, p, alias_map, mode=match_mode):
                matched_pi = pi
                break
        if matched_pi is not None:
            used_pred.add(matched_pi)
            pairs.append((gi, matched_pi))
    unmatched_gold = [i for i in range(len(gold_items)) if i not in {g for g, _ in pairs}]
    unmatched_pred = [i for i in range(len(pred_items)) if i not in used_pred]
    return pairs, unmatched_gold, unmatched_pred


def _calc_prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp > 0 else 0.0
    r = tp / (tp + fn) if tp + fn > 0 else 0.0
    f1 = 2 * p * r / (p + r) if p + r > 0 else 0.0
    return {"precision": p, "recall": r, "f1": f1}


def _has_evidence(item: dict) -> bool:
    ev = item.get("evidence")
    if ev is None:
        return False
    if isinstance(ev, list):
        return any(_norm(e) for e in ev)
    return bool(_norm(ev))


def _count_nonempty_args(args: dict) -> int:
    count = 0
    for v in (args or {}).values():
        if _flatten_value(v):
            count += 1
    return count


def _entity_attr_count(item: dict) -> int:
    aliases = item.get("aliases") or []
    attrs = item.get("attributes") or {}
    desc = 1 if _norm(item.get("description")) else 0
    attr_keys = 0
    for v in attrs.values():
        if _flatten_value(v):
            attr_keys += 1
    return len(aliases) + attr_keys + desc


def _event_arg_count(item: dict) -> int:
    return _count_nonempty_args(item.get("arguments") or {})


def _event_complete(item: dict) -> bool:
    trigger = _norm(item.get("trigger"))
    category = _norm(item.get("category"))
    return bool(trigger and category and _event_arg_count(item) > 0)


def _temporal_complete(item: dict) -> bool:
    rel_type = _norm(_get_rel_type(item))
    source = _norm(item.get("source_event") or item.get("source"))
    target = _norm(item.get("target_event") or item.get("target_time") or item.get("target"))
    return bool(rel_type and source and target)


def _causal_complete(item: dict) -> bool:
    rel_type = _norm(_get_rel_type(item))
    cause = _norm(item.get("cause_event") or item.get("source_event"))
    effect = _norm(item.get("effect_event") or item.get("target_event"))
    return bool(rel_type and cause and effect)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-grained evaluation for MAKER predictions")
    parser.add_argument("--gold-dir", default="results/evaluation")
    parser.add_argument("--pred-dir", required=True)
    parser.add_argument("--output", required=True, help="Output prefix without extension")
    parser.add_argument("--model", default=None, help="Model name for reporting")
    parser.add_argument("--match-mode", choices=["strict", "relaxed", "relaxed_plus", "relaxed_ultra"], default="relaxed_ultra")
    parser.add_argument("--lexicon", default=None, help="Optional entity lexicon JSONL")
    parser.add_argument("--eval-scope", choices=["all", "positive_only"], default="positive_only")
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    pred_dir = Path(args.pred_dir)
    output_prefix = Path(args.output)
    model_name = args.model or pred_dir.name

    load_entity_lexicon, resolve_lexicon_path = _maybe_import_lexicon()
    alias_map: Dict[str, str] = {}
    if load_entity_lexicon and resolve_lexicon_path:
        lex_path = resolve_lexicon_path(args.lexicon)
        _, alias_map = load_entity_lexicon(lex_path)

    # Accumulators
    slot_counts = {
        "entity": {"tp": 0, "fp": 0, "fn": 0},
        "event": {"tp": 0, "fp": 0, "fn": 0},
        "temporal": {"tp": 0, "fp": 0, "fn": 0},
        "causal": {"tp": 0, "fp": 0, "fn": 0},
    }
    completeness = {
        "event": {"complete": 0, "total": 0},
        "temporal": {"complete": 0, "total": 0},
        "causal": {"complete": 0, "total": 0},
    }
    attr_cov = {
        "entity": {"sum": 0, "count": 0},
        "event": {"sum": 0, "count": 0},
    }
    evidence = {
        "event": {"with": 0, "total": 0},
        "temporal": {"with": 0, "total": 0},
        "causal": {"with": 0, "total": 0},
        "static_relation": {"with": 0, "total": 0},
    }

    doc_ids = [p.name for p in sorted(gold_dir.iterdir()) if p.is_dir() and p.name.startswith("wheat_gold_")]
    for doc_id in doc_ids:
        gold_doc = gold_dir / doc_id
        pred_doc = pred_dir / doc_id

        gold_static = _load_payload(gold_doc / "static.json")
        gold_event = _load_payload(gold_doc / "event.json")
        gold_temporal = _load_payload(gold_doc / "temporal.json")
        gold_causal = _load_payload(gold_doc / "causal.json")

        pred_static = _load_payload(pred_doc / "static.json")
        pred_event = _load_payload(pred_doc / "event.json")
        pred_temporal = _load_payload(pred_doc / "temporal.json")
        pred_causal = _load_payload(pred_doc / "causal.json")

        gold_entities = gold_static.get("entities") or []
        pred_entities = pred_static.get("entities") or []
        gold_events = gold_event.get("events") or []
        pred_events = pred_event.get("events") or []
        gold_temporal_rel = gold_temporal.get("temporal_relations") or []
        pred_temporal_rel = pred_temporal.get("temporal_relations") or []
        gold_causal_rel = gold_causal.get("causal_relations") or []
        pred_causal_rel = pred_causal.get("causal_relations") or []
        gold_static_rel = gold_static.get("relations") or []
        pred_static_rel = pred_static.get("relations") or []

        # Slot-F1: entities
        if args.eval_scope == "all" or gold_entities:
            pairs, ug, up = _match_pairs(gold_entities, pred_entities, _relaxed_match_entity, alias_map, args.match_mode)
            for gi, pi in pairs:
                g_slots = _slots_entity(gold_entities[gi])
                p_slots = _slots_entity(pred_entities[pi])
                slot_counts["entity"]["tp"] += len(g_slots & p_slots)
                slot_counts["entity"]["fp"] += len(p_slots - g_slots)
                slot_counts["entity"]["fn"] += len(g_slots - p_slots)
                attr_cov["entity"]["sum"] += _entity_attr_count(pred_entities[pi])
                attr_cov["entity"]["count"] += 1
            for gi in ug:
                g_slots = _slots_entity(gold_entities[gi])
                slot_counts["entity"]["fn"] += len(g_slots)
            for pi in up:
                p_slots = _slots_entity(pred_entities[pi])
                slot_counts["entity"]["fp"] += len(p_slots)

        # Slot-F1: events
        if args.eval_scope == "all" or gold_events:
            pairs, ug, up = _match_pairs(gold_events, pred_events, _relaxed_match_event, alias_map, args.match_mode)
            for gi, pi in pairs:
                g_slots = _slots_event(gold_events[gi])
                p_slots = _slots_event(pred_events[pi])
                slot_counts["event"]["tp"] += len(g_slots & p_slots)
                slot_counts["event"]["fp"] += len(p_slots - g_slots)
                slot_counts["event"]["fn"] += len(g_slots - p_slots)
                completeness["event"]["total"] += 1
                if _event_complete(pred_events[pi]):
                    completeness["event"]["complete"] += 1
                attr_cov["event"]["sum"] += _event_arg_count(pred_events[pi])
                attr_cov["event"]["count"] += 1
                evidence["event"]["total"] += 1
                if _has_evidence(pred_events[pi]):
                    evidence["event"]["with"] += 1
            for gi in ug:
                g_slots = _slots_event(gold_events[gi])
                slot_counts["event"]["fn"] += len(g_slots)
            for pi in up:
                p_slots = _slots_event(pred_events[pi])
                slot_counts["event"]["fp"] += len(p_slots)

        # Slot-F1: temporal
        if args.eval_scope == "all" or gold_temporal_rel:
            pairs, ug, up = _match_pairs(gold_temporal_rel, pred_temporal_rel, _relaxed_match_temporal, alias_map, args.match_mode)
            for gi, pi in pairs:
                g_slots = _slots_temporal(gold_temporal_rel[gi], args.match_mode)
                p_slots = _slots_temporal(pred_temporal_rel[pi], args.match_mode)
                slot_counts["temporal"]["tp"] += len(g_slots & p_slots)
                slot_counts["temporal"]["fp"] += len(p_slots - g_slots)
                slot_counts["temporal"]["fn"] += len(g_slots - p_slots)
                completeness["temporal"]["total"] += 1
                if _temporal_complete(pred_temporal_rel[pi]):
                    completeness["temporal"]["complete"] += 1
                evidence["temporal"]["total"] += 1
                if _has_evidence(pred_temporal_rel[pi]):
                    evidence["temporal"]["with"] += 1
            for gi in ug:
                g_slots = _slots_temporal(gold_temporal_rel[gi], args.match_mode)
                slot_counts["temporal"]["fn"] += len(g_slots)
            for pi in up:
                p_slots = _slots_temporal(pred_temporal_rel[pi], args.match_mode)
                slot_counts["temporal"]["fp"] += len(p_slots)

        # Slot-F1: causal
        if args.eval_scope == "all" or gold_causal_rel:
            pairs, ug, up = _match_pairs(gold_causal_rel, pred_causal_rel, _relaxed_match_causal, alias_map, args.match_mode)
            for gi, pi in pairs:
                g_slots = _slots_causal(gold_causal_rel[gi], args.match_mode)
                p_slots = _slots_causal(pred_causal_rel[pi], args.match_mode)
                slot_counts["causal"]["tp"] += len(g_slots & p_slots)
                slot_counts["causal"]["fp"] += len(p_slots - g_slots)
                slot_counts["causal"]["fn"] += len(g_slots - p_slots)
                completeness["causal"]["total"] += 1
                if _causal_complete(pred_causal_rel[pi]):
                    completeness["causal"]["complete"] += 1
                evidence["causal"]["total"] += 1
                if _has_evidence(pred_causal_rel[pi]):
                    evidence["causal"]["with"] += 1
            for gi in ug:
                g_slots = _slots_causal(gold_causal_rel[gi], args.match_mode)
                slot_counts["causal"]["fn"] += len(g_slots)
            for pi in up:
                p_slots = _slots_causal(pred_causal_rel[pi], args.match_mode)
                slot_counts["causal"]["fp"] += len(p_slots)

        # Evidence coverage: static relations (matched only)
        if args.eval_scope == "all" or gold_static_rel:
            pairs, _, _ = _match_pairs(gold_static_rel, pred_static_rel, _relaxed_match_relation, alias_map, args.match_mode)
            for gi, pi in pairs:
                evidence["static_relation"]["total"] += 1
                if _has_evidence(pred_static_rel[pi]):
                    evidence["static_relation"]["with"] += 1

    slot_f1 = {}
    for key, counts in slot_counts.items():
        prf = _calc_prf(counts["tp"], counts["fp"], counts["fn"])
        slot_f1[key] = {**counts, **prf}

    completeness_ratio = {}
    for key, c in completeness.items():
        ratio = c["complete"] / c["total"] if c["total"] > 0 else 0.0
        completeness_ratio[key] = {"ratio": ratio, **c}

    attr_cov_out = {
        "entity_avg_attrs": attr_cov["entity"]["sum"] / attr_cov["entity"]["count"] if attr_cov["entity"]["count"] > 0 else 0.0,
        "event_avg_args": attr_cov["event"]["sum"] / attr_cov["event"]["count"] if attr_cov["event"]["count"] > 0 else 0.0,
        "entity_count": attr_cov["entity"]["count"],
        "event_count": attr_cov["event"]["count"],
    }

    evidence_ratio = {}
    total_with = 0
    total_all = 0
    for key, e in evidence.items():
        ratio = e["with"] / e["total"] if e["total"] > 0 else 0.0
        evidence_ratio[key] = {"ratio": ratio, **e}
        total_with += e["with"]
        total_all += e["total"]
    evidence_ratio["overall"] = {
        "ratio": total_with / total_all if total_all > 0 else 0.0,
        "with": total_with,
        "total": total_all,
    }

    output = {
        "model": model_name,
        "pred_dir": str(pred_dir),
        "gold_dir": str(gold_dir),
        "match_mode": args.match_mode,
        "eval_scope": args.eval_scope,
        "slot_f1": slot_f1,
        "completeness": completeness_ratio,
        "attribute_coverage": attr_cov_out,
        "evidence_coverage": evidence_ratio,
    }

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    output_prefix.with_suffix(".json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV summary (single row)
    csv_fields = [
        "model",
        "entity_slot_f1",
        "event_slot_f1",
        "temporal_slot_f1",
        "causal_slot_f1",
        "event_completeness",
        "temporal_completeness",
        "causal_completeness",
        "entity_avg_attrs",
        "event_avg_args",
        "evidence_overall",
    ]
    row = [
        model_name,
        f"{slot_f1['entity']['f1']:.4f}",
        f"{slot_f1['event']['f1']:.4f}",
        f"{slot_f1['temporal']['f1']:.4f}",
        f"{slot_f1['causal']['f1']:.4f}",
        f"{completeness_ratio['event']['ratio']:.4f}",
        f"{completeness_ratio['temporal']['ratio']:.4f}",
        f"{completeness_ratio['causal']['ratio']:.4f}",
        f"{attr_cov_out['entity_avg_attrs']:.4f}",
        f"{attr_cov_out['event_avg_args']:.4f}",
        f"{evidence_ratio['overall']['ratio']:.4f}",
    ]
    csv_text = ",".join(csv_fields) + "\n" + ",".join(row) + "\n"
    output_prefix.with_suffix(".csv").write_text(csv_text, encoding="utf-8")

    print(f"Fine-grained scores saved to {output_prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
