#!/usr/bin/env python3
"""
Convert baseline outputs to MAKER format and run evaluation in one step.

Examples:
  # AutoSchemaKG (JSONL or JSON files with entity_relation_dict/event_*_dict)
  python scripts/baselines/run_baseline_eval.py \
    --baseline autoschemakg \
    --input /path/to/autoschemakg_outputs \
    --match-mode relaxed_ultra \
    --eval-scope positive_only

  # OneKE (per-doc folders containing ner.json/re.json/ee.json/triple.json)
  python scripts/baselines/run_baseline_eval.py \
    --baseline oneke \
    --input /path/to/oneke_outputs \
    --match-mode relaxed_ultra \
    --eval-scope positive_only

  # KG-Gen (per-doc folders containing graph.json)
  python scripts/baselines/run_baseline_eval.py \
    --baseline kggen \
    --input /path/to/kggen_outputs \
    --match-mode relaxed_ultra \
    --eval-scope positive_only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
    if stripped.endswith("```"):
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _extract_json_block(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _safe_json_load(text: str) -> Optional[Any]:
    if not text:
        return None
    cleaned = _strip_code_fence(text)
    candidates = [cleaned]
    block = _extract_json_block(cleaned)
    if block and block != cleaned:
        candidates.append(block)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _iter_json_records(path: Path) -> Iterable[dict]:
    if path.is_file():
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    obj = _safe_json_load(line)
                    if isinstance(obj, dict):
                        yield obj
            return
        text = _read_text(path)
        obj = _safe_json_load(text)
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    yield item
            return
        if isinstance(obj, dict):
            yield obj
            return
        # Fallback: treat .json as JSONL (one JSON object per line)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = _safe_json_load(line)
                if isinstance(obj, dict):
                    yield obj
        return
    else:
        for file in sorted(path.rglob("*.jsonl")):
            yield from _iter_json_records(file)
        for file in sorted(path.rglob("*.json")):
            yield from _iter_json_records(file)


def _collect_gold_ids(gold_dir: Path) -> List[str]:
    ids: List[str] = []
    for path in sorted(gold_dir.iterdir()):
        if path.is_dir() and path.name.startswith("wheat_gold_"):
            ids.append(path.name)
    return ids


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_doc_dirs(output_dir: Path, doc_ids: Iterable[str]) -> None:
    for doc_id in doc_ids:
        (output_dir / doc_id).mkdir(parents=True, exist_ok=True)


def _normalize_rel(text: str) -> str:
    if not text:
        return ""
    return str(text).strip().lower()


def _classify_relation(rel: str) -> Optional[str]:
    r = _normalize_rel(rel)
    if not r:
        return None
    causal_keywords = [
        "because",
        "cause",
        "causes",
        "caused",
        "due to",
        "as a result",
        "result in",
        "results in",
        "lead to",
        "leads to",
        "therefore",
        "thus",
        "hence",
        "since",
        "导致",
        "因为",
        "由于",
        "引起",
        "造成",
        "促使",
        "促进",
        "抑制",
        "降低",
        "提高",
    ]
    temporal_keywords = [
        "before",
        "after",
        "earlier",
        "later",
        "prior",
        "previous",
        "following",
        "at the same time",
        "simultaneous",
        "simultaneously",
        "during",
        "when",
        "while",
        "start",
        "begin",
        "end",
        "finish",
        "之前",
        "之后",
        "同时",
        "期间",
        "开始",
        "结束",
    ]
    if any(k in r for k in causal_keywords):
        return "causal"
    if any(k in r for k in temporal_keywords):
        return "temporal"
    return None


def _normalize_temporal_type(rel: str) -> str:
    r = _normalize_rel(rel)
    if any(k in r for k in ["before", "prior", "earlier", "之前"]):
        return "先于"
    if any(k in r for k in ["after", "later", "之后", "following"]):
        return "后于"
    if any(k in r for k in ["at the same time", "simultaneous", "simultaneously", "同时"]):
        return "同时"
    if any(k in r for k in ["during", "while", "期间"]):
        return "期间"
    if any(k in r for k in ["start", "begin", "开始"]):
        return "开始于"
    if any(k in r for k in ["end", "finish", "结束"]):
        return "结束于"
    return rel or "发生于"


def _normalize_causal_type(rel: str) -> str:
    r = _normalize_rel(rel)
    if any(k in r for k in ["promote", "increase", "促进", "提高"]):
        return "促进"
    if any(k in r for k in ["inhibit", "decrease", "reduce", "抑制", "降低"]):
        return "抑制"
    if any(k in r for k in ["cause", "because", "due to", "导致", "引起", "造成", "result", "lead"]):
        return "导致"
    return "相关"


def _autoschemakg_record_to_maker(record: dict) -> Tuple[List[dict], List[dict], List[dict], List[dict], List[dict]]:
    entity_rel = record.get("entity_relation_dict")
    event_entity = record.get("event_entity_relation_dict")
    event_rel = record.get("event_relation_dict")

    if not isinstance(entity_rel, list):
        entity_rel = []
    if not isinstance(event_entity, list):
        event_entity = []
    if not isinstance(event_rel, list):
        event_rel = []

    if not entity_rel and isinstance(record.get("output_stage_one"), str):
        parsed = _safe_json_load(record.get("output_stage_one", ""))
        if isinstance(parsed, list):
            entity_rel = parsed
    if not event_entity and isinstance(record.get("output_stage_two"), str):
        parsed = _safe_json_load(record.get("output_stage_two", ""))
        if isinstance(parsed, list):
            event_entity = parsed
    if not event_rel and isinstance(record.get("output_stage_three"), str):
        parsed = _safe_json_load(record.get("output_stage_three", ""))
        if isinstance(parsed, list):
            event_rel = parsed

    entities: Dict[str, dict] = {}
    relations: List[dict] = []
    events: List[dict] = []
    temporal: List[dict] = []
    causal: List[dict] = []

    for item in entity_rel:
        if not isinstance(item, dict):
            continue
        head = str(item.get("Head", "")).strip()
        rel = str(item.get("Relation", "")).strip()
        tail = str(item.get("Tail", "")).strip()
        if not head or not tail or not rel:
            continue
        relations.append({"source": head, "target": tail, "type": rel})
        if head not in entities:
            entities[head] = {"name": head, "type": "未指定"}
        if tail not in entities:
            entities[tail] = {"name": tail, "type": "未指定"}

    for item in event_entity:
        if not isinstance(item, dict):
            continue
        event_text = str(item.get("Event", "")).strip()
        if not event_text:
            continue
        args = item.get("Entity")
        if isinstance(args, str):
            args = [args]
        if not isinstance(args, list):
            args = []
        events.append({"trigger": event_text, "category": "", "subtype": "", "arguments": {"participants": args}})

    for item in event_rel:
        if not isinstance(item, dict):
            continue
        head = str(item.get("Head", "")).strip()
        rel = str(item.get("Relation", "")).strip()
        tail = str(item.get("Tail", "")).strip()
        if not head or not tail or not rel:
            continue
        relation_type = _classify_relation(rel)
        if relation_type == "temporal":
            temporal.append({
                "source_event": head,
                "target_event": tail,
                "relation_type": _normalize_temporal_type(rel),
            })
        elif relation_type == "causal":
            causal.append({
                "cause_event": head,
                "effect_event": tail,
                "relation_type": _normalize_causal_type(rel),
            })

    return list(entities.values()), relations, events, temporal, causal


def _oneke_record_to_maker(record: dict) -> Tuple[List[dict], List[dict], List[dict]]:
    entities: Dict[str, dict] = {}
    relations: List[dict] = []
    events: List[dict] = []

    if isinstance(record.get("entity_list"), list):
        for ent in record.get("entity_list", []):
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name", "")).strip()
            etype = str(ent.get("type", "")).strip() or "未指定"
            if not name:
                continue
            entities[name] = {"name": name, "type": etype}

    if isinstance(record.get("relation_list"), list):
        for rel in record.get("relation_list", []):
            if not isinstance(rel, dict):
                continue
            head = str(rel.get("head", "")).strip()
            tail = str(rel.get("tail", "")).strip()
            r = str(rel.get("relation", "")).strip()
            if not head or not tail or not r:
                continue
            relations.append({"source": head, "target": tail, "type": r})
            if head not in entities:
                entities[head] = {"name": head, "type": "未指定"}
            if tail not in entities:
                entities[tail] = {"name": tail, "type": "未指定"}

    if isinstance(record.get("triple_list"), list):
        for triple in record.get("triple_list", []):
            if not isinstance(triple, dict):
                continue
            head = str(triple.get("head", "")).strip()
            tail = str(triple.get("tail", "")).strip()
            rel = str(triple.get("relation", "")).strip()
            if not head or not tail or not rel:
                continue
            relations.append({"source": head, "target": tail, "type": rel})
            head_type = str(triple.get("head_type", "")).strip() or "未指定"
            tail_type = str(triple.get("tail_type", "")).strip() or "未指定"
            if head not in entities:
                entities[head] = {"name": head, "type": head_type}
            if tail not in entities:
                entities[tail] = {"name": tail, "type": tail_type}

    if isinstance(record.get("event_list"), list):
        for evt in record.get("event_list", []):
            if not isinstance(evt, dict):
                continue
            trigger = str(evt.get("event_trigger", "")).strip()
            category = str(evt.get("event_type", "")).strip()
            if not trigger:
                continue
            events.append({
                "trigger": trigger,
                "category": category,
                "subtype": "",
                "arguments": evt.get("event_argument", {}),
            })

    return list(entities.values()), relations, events


def _kggen_record_to_maker(record: dict) -> Tuple[List[dict], List[dict]]:
    entities: Dict[str, dict] = {}
    relations: List[dict] = []
    ent_list = record.get("entities") if isinstance(record, dict) else None
    rel_list = record.get("relations") if isinstance(record, dict) else None
    if isinstance(ent_list, list):
        for ent in ent_list:
            name = str(ent).strip()
            if not name:
                continue
            entities[name] = {"name": name, "type": "未指定"}
    if isinstance(rel_list, list):
        for rel in rel_list:
            if isinstance(rel, (list, tuple)) and len(rel) >= 3:
                head, predicate, tail = rel[0], rel[1], rel[2]
            elif isinstance(rel, dict):
                head = rel.get("head") or rel.get("source")
                predicate = rel.get("relation") or rel.get("predicate")
                tail = rel.get("tail") or rel.get("target")
            else:
                continue
            head = str(head).strip() if head is not None else ""
            tail = str(tail).strip() if tail is not None else ""
            predicate = str(predicate).strip() if predicate is not None else ""
            if not head or not tail or not predicate:
                continue
            relations.append({"source": head, "target": tail, "type": predicate})
            if head not in entities:
                entities[head] = {"name": head, "type": "未指定"}
            if tail not in entities:
                entities[tail] = {"name": tail, "type": "未指定"}
    return list(entities.values()), relations


def _convert_autoschemakg(input_path: Path, output_dir: Path, gold_ids: List[str], match_by: str) -> None:
    records: List[dict] = list(_iter_json_records(input_path))
    mapping: Dict[str, dict] = {}
    if match_by == "id":
        for record in records:
            doc_id = str(record.get("doc_id") or record.get("id") or "").strip()
            if not doc_id:
                continue
            if doc_id not in mapping:
                mapping[doc_id] = {"entity_relation_dict": [], "event_entity_relation_dict": [], "event_relation_dict": []}
            for key in ["entity_relation_dict", "event_entity_relation_dict", "event_relation_dict"]:
                if isinstance(record.get(key), list):
                    mapping[doc_id][key].extend(record.get(key))
                elif record.get(key) is not None:
                    mapping[doc_id][key].append(record.get(key))
            for stage_key, target in [
                ("output_stage_one", "entity_relation_dict"),
                ("output_stage_two", "event_entity_relation_dict"),
                ("output_stage_three", "event_relation_dict"),
            ]:
                if record.get(stage_key):
                    mapping[doc_id][stage_key] = record.get(stage_key)
        if not mapping and records:
            print("No doc_id/id matched. Fallback to index-based alignment.")
            for idx, doc_id in enumerate(gold_ids):
                if idx >= len(records):
                    break
                mapping[doc_id] = records[idx]
    else:
        # index-based alignment
        for idx, doc_id in enumerate(gold_ids):
            if idx >= len(records):
                break
            mapping[doc_id] = records[idx]

    _ensure_doc_dirs(output_dir, gold_ids)
    for doc_id in gold_ids:
        record = mapping.get(doc_id, {})
        entities, relations, events, temporal, causal = _autoschemakg_record_to_maker(record)
        doc_dir = output_dir / doc_id
        _write_json(doc_dir / "static.json", {"entities": entities, "relations": relations})
        _write_json(doc_dir / "event.json", {"events": events})
        _write_json(doc_dir / "temporal.json", {"temporal_relations": temporal})
        _write_json(doc_dir / "causal.json", {"causal_relations": causal})


def _find_file_case_insensitive(dir_path: Path, names: List[str]) -> Optional[Path]:
    if not dir_path.exists():
        return None
    lower_map = {p.name.lower(): p for p in dir_path.iterdir() if p.is_file()}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def _load_oneke_doc(dir_path: Path, names: List[str]) -> Optional[dict]:
    path = _find_file_case_insensitive(dir_path, names)
    if not path:
        return None
    text = _read_text(path)
    obj = _safe_json_load(text)
    if isinstance(obj, dict):
        return obj
    return None


def _convert_oneke(input_path: Path, output_dir: Path, gold_ids: List[str], match_by: str) -> None:
    if input_path.is_file():
        records = list(_iter_json_records(input_path))
        mapping: Dict[str, dict] = {}
        if match_by == "id":
            for record in records:
                doc_id = str(record.get("doc_id") or record.get("id") or "").strip()
                if not doc_id:
                    continue
                mapping[doc_id] = record
            if not mapping and records:
                print("No doc_id/id matched. Fallback to index-based alignment.")
                for idx, doc_id in enumerate(gold_ids):
                    if idx >= len(records):
                        break
                    mapping[doc_id] = records[idx]
        else:
            for idx, doc_id in enumerate(gold_ids):
                if idx >= len(records):
                    break
                mapping[doc_id] = records[idx]
        _ensure_doc_dirs(output_dir, gold_ids)
        for doc_id in gold_ids:
            record = mapping.get(doc_id, {})
            entities, relations, events = _oneke_record_to_maker(record)
            doc_dir = output_dir / doc_id
            _write_json(doc_dir / "static.json", {"entities": entities, "relations": relations})
            _write_json(doc_dir / "event.json", {"events": events})
            _write_json(doc_dir / "temporal.json", {"temporal_relations": []})
            _write_json(doc_dir / "causal.json", {"causal_relations": []})
        return

    _ensure_doc_dirs(output_dir, gold_ids)
    for doc_id in gold_ids:
        doc_dir = input_path / doc_id
        entities: List[dict] = []
        relations: List[dict] = []
        events: List[dict] = []

        ner = _load_oneke_doc(doc_dir, ["ner.json", "NER.json"]) or {}
        rel = _load_oneke_doc(doc_dir, ["re.json", "RE.json"]) or {}
        ee = _load_oneke_doc(doc_dir, ["ee.json", "EE.json"]) or {}
        triple = _load_oneke_doc(doc_dir, ["triple.json", "Triple.json", "triple_extraction.json", "TripleExtraction.json"]) or {}

        for record in [ner, rel, ee, triple]:
            if not isinstance(record, dict):
                continue
            ent_list, rel_list, evt_list = _oneke_record_to_maker(record)
            if ent_list:
                entities.extend(ent_list)
            if rel_list:
                relations.extend(rel_list)
            if evt_list:
                events.extend(evt_list)

        # de-dup entities by name
        ent_map: Dict[str, dict] = {}
        for ent in entities:
            name = str(ent.get("name", "")).strip()
            if not name:
                continue
            if name not in ent_map:
                ent_map[name] = ent

        doc_out = output_dir / doc_id
        _write_json(doc_out / "static.json", {"entities": list(ent_map.values()), "relations": relations})
        _write_json(doc_out / "event.json", {"events": events})
        _write_json(doc_out / "temporal.json", {"temporal_relations": []})
        _write_json(doc_out / "causal.json", {"causal_relations": []})


def _convert_kggen(input_path: Path, output_dir: Path, gold_ids: List[str], match_by: str) -> None:
    if input_path.is_file():
        records = list(_iter_json_records(input_path))
        mapping: Dict[str, dict] = {}
        if match_by == "id":
            for record in records:
                doc_id = str(record.get("doc_id") or record.get("id") or "").strip()
                if not doc_id:
                    continue
                mapping[doc_id] = record
            if not mapping and records:
                print("No doc_id/id matched. Fallback to index-based alignment.")
                for idx, doc_id in enumerate(gold_ids):
                    if idx >= len(records):
                        break
                    mapping[doc_id] = records[idx]
        else:
            for idx, doc_id in enumerate(gold_ids):
                if idx >= len(records):
                    break
                mapping[doc_id] = records[idx]
        _ensure_doc_dirs(output_dir, gold_ids)
        for doc_id in gold_ids:
            record = mapping.get(doc_id, {})
            entities, relations = _kggen_record_to_maker(record)
            doc_dir = output_dir / doc_id
            _write_json(doc_dir / "static.json", {"entities": entities, "relations": relations})
            _write_json(doc_dir / "event.json", {"events": []})
            _write_json(doc_dir / "temporal.json", {"temporal_relations": []})
            _write_json(doc_dir / "causal.json", {"causal_relations": []})
        return

    _ensure_doc_dirs(output_dir, gold_ids)
    for doc_id in gold_ids:
        doc_dir = input_path / doc_id
        graph_path = _find_file_case_insensitive(doc_dir, ["graph.json"]) or _find_file_case_insensitive(doc_dir, [f"{doc_id}.json"])
        record: dict = {}
        if graph_path:
            obj = _safe_json_load(_read_text(graph_path))
            if isinstance(obj, dict):
                record = obj
        entities, relations = _kggen_record_to_maker(record)
        doc_out = output_dir / doc_id
        _write_json(doc_out / "static.json", {"entities": entities, "relations": relations})
        _write_json(doc_out / "event.json", {"events": []})
        _write_json(doc_out / "temporal.json", {"temporal_relations": []})
        _write_json(doc_out / "causal.json", {"causal_relations": []})


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert baseline outputs and score against MAKER gold data")
    parser.add_argument("--baseline", required=True, choices=["autoschemakg", "oneke", "kggen"], help="Baseline name")
    parser.add_argument("--input", required=True, help="Baseline output path (file or directory)")
    parser.add_argument("--gold-dir", default="results/evaluation", help="Gold data directory")
    parser.add_argument("--output-pred", default=None, help="Output dir for converted predictions")
    parser.add_argument("--output-score", default=None, help="Output prefix for score files (without extension)")
    parser.add_argument("--match-by", choices=["id", "index"], default="id", help="How to align baseline outputs to gold docs")
    parser.add_argument("--match-mode", choices=["strict", "relaxed", "relaxed_plus", "relaxed_ultra"], default="relaxed_ultra")
    parser.add_argument("--eval-scope", choices=["all", "positive_only"], default="positive_only")
    parser.add_argument("--static-metric", choices=["relations", "entities", "combined"], default="combined")
    parser.add_argument("--convert-only", action="store_true", help="Only convert, do not score")
    args = parser.parse_args()

    gold_dir = PROJECT_ROOT / args.gold_dir
    input_path = Path(args.input)
    baseline = args.baseline
    output_pred = Path(args.output_pred) if args.output_pred else PROJECT_ROOT / "results" / "baseline_predictions" / baseline
    output_score = Path(args.output_score) if args.output_score else PROJECT_ROOT / "results" / "baseline_scores" / baseline

    output_pred.mkdir(parents=True, exist_ok=True)
    output_score.parent.mkdir(parents=True, exist_ok=True)

    gold_ids = _collect_gold_ids(gold_dir)
    if not gold_ids:
        raise SystemExit(f"No gold samples found in {gold_dir}")

    if baseline == "autoschemakg":
        _convert_autoschemakg(input_path, output_pred, gold_ids, args.match_by)
    elif baseline == "oneke":
        _convert_oneke(input_path, output_pred, gold_ids, args.match_by)
    elif baseline == "kggen":
        _convert_kggen(input_path, output_pred, gold_ids, args.match_by)

    if args.convert_only:
        print(f"Converted outputs written to {output_pred}")
        return

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "evaluation" / "score_gold_predictions.py"),
        "--gold-dir",
        str(gold_dir),
        "--pred-dir",
        str(output_pred),
        "--output",
        str(output_score),
        "--static-metric",
        args.static_metric,
        "--match-mode",
        args.match_mode,
        "--eval-scope",
        args.eval_scope,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
