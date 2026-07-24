#!/usr/bin/env python3
"""
Score model predictions against gold labels using micro-P/R/F1.

Usage example:
  python scripts/evaluation/score_gold_predictions.py \
    --gold-dir results/evaluation \
    --pred-dir results/predictions/gpt54 \
    --static-metric combined \
    --output results/evaluation_scores/gpt54
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple


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
    text = _read_text(path)
    payload = _safe_json_load(text)
    if isinstance(payload, dict):
        return payload
    return {}


_WS_RE = re.compile(r"\s+")


def _norm(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip()
    value = _WS_RE.sub(" ", value)
    return value


_RELAX_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


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
        from src.core.knowledge_graph.alignment.match_rules import load_entity_lexicon, resolve_lexicon_path  # type: ignore
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
    # relaxed: containment match (avoid very short strings)
    if len(a_norm) >= 2 and len(b_norm) >= 2:
        return a_norm in b_norm or b_norm in a_norm
    if mode in {"relaxed_plus", "relaxed_ultra"}:
        # fuzzy match for longer strings
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
    # temporal
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
    # causal
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
    # static (coarse normalization)
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
    # subtype is ignored in relaxed matching
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


def _get_rel_type(item: dict) -> str:
    return _norm(item.get("type") or item.get("relation_type") or "")


def _static_entities(payload: dict) -> set[Tuple[str, str]]:
    items = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return set()
    result = set()
    for ent in items:
        if not isinstance(ent, dict):
            continue
        name = _norm(ent.get("name"))
        ent_type = _norm(ent.get("type"))
        if name and ent_type:
            result.add((name, ent_type))
    return result


def _static_relations(payload: dict) -> set[Tuple[str, str, str]]:
    items = payload.get("relations") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return set()
    result = set()
    for rel in items:
        if not isinstance(rel, dict):
            continue
        source = _norm(rel.get("source"))
        target = _norm(rel.get("target"))
        rel_type = _get_rel_type(rel)
        if source and target and rel_type:
            result.add((source, target, rel_type))
    return result


def _event_items(payload: dict) -> set[Tuple[str, str, str]]:
    items = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return set()
    result = set()
    for evt in items:
        if not isinstance(evt, dict):
            continue
        trigger = _norm(evt.get("trigger") or evt.get("event") or evt.get("description") or "")
        category = _norm(evt.get("category") or "")
        subtype = _norm(evt.get("subtype") or "")
        if trigger and (category or subtype):
            result.add((trigger, category, subtype))
    return result


def _temporal_items(payload: dict) -> set[Tuple[str, str, str]]:
    items = payload.get("temporal_relations") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return set()
    result = set()
    for rel in items:
        if not isinstance(rel, dict):
            continue
        source = _norm(rel.get("source_event") or rel.get("source") or "")
        target = _norm(rel.get("target_event") or rel.get("target_time") or rel.get("target") or "")
        rel_type = _get_rel_type(rel) or _norm(rel.get("relation_type") or "")
        if source and target and rel_type:
            result.add((source, target, rel_type))
    return result


def _causal_items(payload: dict) -> set[Tuple[str, str, str]]:
    items = payload.get("causal_relations") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return set()
    result = set()
    for rel in items:
        if not isinstance(rel, dict):
            continue
        cause = _norm(rel.get("cause_event") or rel.get("source_event") or "")
        effect = _norm(rel.get("effect_event") or rel.get("target_event") or "")
        rel_type = _get_rel_type(rel) or _norm(rel.get("relation_type") or "")
        if cause and effect and rel_type:
            result.add((cause, effect, rel_type))
    return result


def _count_micro(gold: Iterable, pred: Iterable) -> Tuple[int, int, int]:
    gold_set = set(gold)
    pred_set = set(pred)
    tp = len(gold_set & pred_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    return tp, fp, fn


def _count_micro_relaxed(gold_items: List[dict], pred_items: List[dict], match_fn, alias_map: Dict[str, str]) -> Tuple[int, int, int]:
    matched = set()
    tp = 0
    for pred in pred_items:
        if not isinstance(pred, dict):
            continue
        found = False
        for idx, gold in enumerate(gold_items):
            if idx in matched or not isinstance(gold, dict):
                continue
            if match_fn(gold, pred, alias_map):
                matched.add(idx)
                tp += 1
                found = True
                break
        if not found:
            continue
    fp = len([p for p in pred_items if isinstance(p, dict)]) - tp
    fn = len([g for g in gold_items if isinstance(g, dict)]) - tp
    return tp, fp, fn


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _collect_doc_ids(gold_dir: Path) -> List[str]:
    ids = []
    for path in sorted(gold_dir.iterdir()):
        if not path.is_dir():
            continue
        if path.name.startswith("wheat_gold_"):
            ids.append(path.name)
    return ids


def _has_nonempty_dict_items(items: object) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if isinstance(item, dict):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Score predictions vs gold using micro-P/R/F1")
    parser.add_argument("--gold-dir", default="results/evaluation")
    parser.add_argument("--pred-dir", required=True)
    parser.add_argument("--output", default="results/evaluation_scores/score")
    parser.add_argument(
        "--static-metric",
        choices=["relations", "entities", "combined"],
        default="combined",
        help="How to compute static score: relations, entities, or combined",
    )
    parser.add_argument(
        "--match-mode",
        choices=["strict", "relaxed", "relaxed_plus", "relaxed_ultra"],
        default="strict",
        help="Matching mode: strict (exact) or relaxed (normalized/substring, ignore subtype)",
    )
    parser.add_argument(
        "--entity-lexicon",
        default=None,
        help="Optional entity lexicon JSONL for alias normalization (relaxed mode only).",
    )
    parser.add_argument(
        "--eval-scope",
        choices=["all", "positive_only"],
        default="all",
        help="Evaluation scope: all samples or only samples with non-empty gold items for each type.",
    )
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    pred_dir = Path(args.pred_dir)
    out_prefix = Path(args.output)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    doc_ids = _collect_doc_ids(gold_dir)
    if not doc_ids:
        raise SystemExit(f"No gold samples found in {gold_dir}")

    alias_map: Dict[str, str] = {}
    if args.match_mode != "strict":
        load_lexicon, resolve_lexicon = _maybe_import_lexicon()
        if load_lexicon and resolve_lexicon:
            lexicon_path = resolve_lexicon(args.entity_lexicon)
            _, alias_map = load_lexicon(lexicon_path)

    totals = {
        "static": {"tp": 0, "fp": 0, "fn": 0},
        "event": {"tp": 0, "fp": 0, "fn": 0},
        "temporal": {"tp": 0, "fp": 0, "fn": 0},
        "causal": {"tp": 0, "fp": 0, "fn": 0},
        "static_entities": {"tp": 0, "fp": 0, "fn": 0},
        "static_relations": {"tp": 0, "fp": 0, "fn": 0},
    }

    for doc_id in doc_ids:
        gold_path = gold_dir / doc_id
        pred_path = pred_dir / doc_id

        gold_static = _load_payload(gold_path / "static.json")
        gold_event = _load_payload(gold_path / "event.json")
        gold_temporal = _load_payload(gold_path / "temporal.json")
        gold_causal = _load_payload(gold_path / "causal.json")

        pred_static = _load_payload(pred_path / "static.json")
        pred_event = _load_payload(pred_path / "event.json")
        pred_temporal = _load_payload(pred_path / "temporal.json")
        pred_causal = _load_payload(pred_path / "causal.json")

        g_ent_items_raw = gold_static.get("entities") if isinstance(gold_static, dict) else []
        g_rel_items_raw = gold_static.get("relations") if isinstance(gold_static, dict) else []
        g_evt_items_raw = gold_event.get("events") if isinstance(gold_event, dict) else []
        g_temp_items_raw = gold_temporal.get("temporal_relations") if isinstance(gold_temporal, dict) else []
        g_cau_items_raw = gold_causal.get("causal_relations") if isinstance(gold_causal, dict) else []

        include_static_entities = True
        include_static_relations = True
        include_event = True
        include_temporal = True
        include_causal = True

        if args.eval_scope == "positive_only":
            include_static_entities = _has_nonempty_dict_items(g_ent_items_raw)
            include_static_relations = _has_nonempty_dict_items(g_rel_items_raw)
            include_event = _has_nonempty_dict_items(g_evt_items_raw)
            include_temporal = _has_nonempty_dict_items(g_temp_items_raw)
            include_causal = _has_nonempty_dict_items(g_cau_items_raw)

        if args.match_mode in {"relaxed", "relaxed_plus", "relaxed_ultra"}:
            g_ent_items = g_ent_items_raw
            p_ent_items = pred_static.get("entities") if isinstance(pred_static, dict) else []
            g_rel_items = g_rel_items_raw
            p_rel_items = pred_static.get("relations") if isinstance(pred_static, dict) else []

            tp, fp, fn = _count_micro_relaxed(g_ent_items or [], p_ent_items or [], lambda g, p, a: _relaxed_match_entity(g, p, a, mode=args.match_mode), alias_map)
            if include_static_entities:
                totals["static_entities"]["tp"] += tp
                totals["static_entities"]["fp"] += fp
                totals["static_entities"]["fn"] += fn

            tp, fp, fn = _count_micro_relaxed(g_rel_items or [], p_rel_items or [], lambda g, p, a: _relaxed_match_relation(g, p, a, mode=args.match_mode), alias_map)
            if include_static_relations:
                totals["static_relations"]["tp"] += tp
                totals["static_relations"]["fp"] += fp
                totals["static_relations"]["fn"] += fn

            if args.static_metric == "entities":
                tp, fp, fn = _count_micro_relaxed(g_ent_items or [], p_ent_items or [], lambda g, p, a: _relaxed_match_entity(g, p, a, mode=args.match_mode), alias_map)
                include_static = include_static_entities
            elif args.static_metric == "relations":
                tp, fp, fn = _count_micro_relaxed(g_rel_items or [], p_rel_items or [], lambda g, p, a: _relaxed_match_relation(g, p, a, mode=args.match_mode), alias_map)
                include_static = include_static_relations
            else:
                tp_e, fp_e, fn_e = _count_micro_relaxed(g_ent_items or [], p_ent_items or [], lambda g, p, a: _relaxed_match_entity(g, p, a, mode=args.match_mode), alias_map)
                tp_r, fp_r, fn_r = _count_micro_relaxed(g_rel_items or [], p_rel_items or [], lambda g, p, a: _relaxed_match_relation(g, p, a, mode=args.match_mode), alias_map)
                tp, fp, fn = tp_e + tp_r, fp_e + fp_r, fn_e + fn_r
                include_static = include_static_entities or include_static_relations
            if include_static:
                totals["static"]["tp"] += tp
                totals["static"]["fp"] += fp
                totals["static"]["fn"] += fn

            g_evt = g_evt_items_raw
            p_evt = pred_event.get("events") if isinstance(pred_event, dict) else []
            tp, fp, fn = _count_micro_relaxed(g_evt or [], p_evt or [], lambda g, p, a: _relaxed_match_event(g, p, a, mode=args.match_mode), alias_map)
            if include_event:
                totals["event"]["tp"] += tp
                totals["event"]["fp"] += fp
                totals["event"]["fn"] += fn

            g_temp = g_temp_items_raw
            p_temp = pred_temporal.get("temporal_relations") if isinstance(pred_temporal, dict) else []
            tp, fp, fn = _count_micro_relaxed(g_temp or [], p_temp or [], lambda g, p, a: _relaxed_match_temporal(g, p, a, mode=args.match_mode), alias_map)
            if include_temporal:
                totals["temporal"]["tp"] += tp
                totals["temporal"]["fp"] += fp
                totals["temporal"]["fn"] += fn

            g_cau = g_cau_items_raw
            p_cau = pred_causal.get("causal_relations") if isinstance(pred_causal, dict) else []
            tp, fp, fn = _count_micro_relaxed(g_cau or [], p_cau or [], lambda g, p, a: _relaxed_match_causal(g, p, a, mode=args.match_mode), alias_map)
            if include_causal:
                totals["causal"]["tp"] += tp
                totals["causal"]["fp"] += fp
                totals["causal"]["fn"] += fn
        else:
            g_ent = _static_entities(gold_static)
            p_ent = _static_entities(pred_static)
            g_rel = _static_relations(gold_static)
            p_rel = _static_relations(pred_static)

            tp, fp, fn = _count_micro(g_ent, p_ent)
            if include_static_entities:
                totals["static_entities"]["tp"] += tp
                totals["static_entities"]["fp"] += fp
                totals["static_entities"]["fn"] += fn

            tp, fp, fn = _count_micro(g_rel, p_rel)
            if include_static_relations:
                totals["static_relations"]["tp"] += tp
                totals["static_relations"]["fp"] += fp
                totals["static_relations"]["fn"] += fn

            if args.static_metric == "entities":
                tp, fp, fn = _count_micro(g_ent, p_ent)
                include_static = include_static_entities
            elif args.static_metric == "relations":
                tp, fp, fn = _count_micro(g_rel, p_rel)
                include_static = include_static_relations
            else:
                combined_gold = {("ENT", *item) for item in g_ent} | {("REL", *item) for item in g_rel}
                combined_pred = {("ENT", *item) for item in p_ent} | {("REL", *item) for item in p_rel}
                tp, fp, fn = _count_micro(combined_gold, combined_pred)
                include_static = include_static_entities or include_static_relations
            if include_static:
                totals["static"]["tp"] += tp
                totals["static"]["fp"] += fp
                totals["static"]["fn"] += fn

            tp, fp, fn = _count_micro(_event_items(gold_event), _event_items(pred_event))
            if include_event:
                totals["event"]["tp"] += tp
                totals["event"]["fp"] += fp
                totals["event"]["fn"] += fn

            tp, fp, fn = _count_micro(_temporal_items(gold_temporal), _temporal_items(pred_temporal))
            if include_temporal:
                totals["temporal"]["tp"] += tp
                totals["temporal"]["fp"] += fp
                totals["temporal"]["fn"] += fn

            tp, fp, fn = _count_micro(_causal_items(gold_causal), _causal_items(pred_causal))
            if include_causal:
                totals["causal"]["tp"] += tp
                totals["causal"]["fp"] += fp
                totals["causal"]["fn"] += fn

    metrics: Dict[str, Dict[str, float]] = {}
    for key, counts in totals.items():
        p, r, f1 = _prf(counts["tp"], counts["fp"], counts["fn"])
        metrics[key] = {
            "precision": round(p, 6),
            "recall": round(r, 6),
            "f1": round(f1, 6),
            "tp": counts["tp"],
            "fp": counts["fp"],
            "fn": counts["fn"],
        }

    out_json = out_prefix.with_suffix(".json")
    out_csv = out_prefix.with_suffix(".csv")

    out_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["type,precision,recall,f1,tp,fp,fn"]
    for key in ["static", "event", "temporal", "causal", "static_entities", "static_relations"]:
        row = metrics.get(key, {})
        lines.append(
            f"{key},{row.get('precision',0)},{row.get('recall',0)},{row.get('f1',0)},"
            f"{row.get('tp',0)},{row.get('fp',0)},{row.get('fn',0)}"
        )
    out_csv.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()
