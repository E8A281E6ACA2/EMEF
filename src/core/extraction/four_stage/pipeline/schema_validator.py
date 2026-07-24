"""
Lightweight schema validation for dynamic retry.
"""

from __future__ import annotations

import os
from typing import Any, Tuple


def _env_bool(names: list[str], default: bool) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _env_int(names: list[str], default: int) -> int:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return default


def schema_retry_config() -> tuple[bool, int, str]:
    enabled = _env_bool(["SCHEMA_VALIDATE", "LLM_SCHEMA_VALIDATE"], False)
    retry_max = _env_int(["SCHEMA_RETRY_MAX", "LLM_SCHEMA_RETRY_MAX"], 1)
    suffix = os.getenv(
        "SCHEMA_RETRY_SUFFIX",
        "请严格输出JSON对象，仅包含结果字段，不要附加解释或代码块。",
    )
    return enabled, max(0, retry_max), suffix


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _require_list(payload: dict, key: str) -> Tuple[bool, str]:
    if key not in payload:
        return False, f"missing:{key}"
    if not isinstance(payload.get(key), list):
        return False, f"type:{key}"
    return True, ""


def _validate_items(items: list, required: list[str]) -> Tuple[bool, str]:
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f"item_not_dict:{idx}"
        for field in required:
            if not _is_str(item.get(field)):
                return False, f"field:{field}"
    return True, ""


def validate_payload(stage: str, payload: Any) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "payload_not_dict"

    if stage == "static":
        ok, reason = _require_list(payload, "entities")
        if not ok:
            return ok, reason
        ok, reason = _require_list(payload, "relations")
        if not ok:
            return ok, reason
        entities = payload.get("entities") or []
        relations = payload.get("relations") or []
        ok, reason = _validate_items(entities, ["name", "type"])
        if not ok:
            return ok, reason
        ok, reason = _validate_items(relations, ["source", "target", "type", "evidence"])
        return ok, reason

    if stage == "event":
        ok, reason = _require_list(payload, "events")
        if not ok:
            return ok, reason
        events = payload.get("events") or []
        return _validate_items(events, ["trigger", "category", "subtype", "evidence"])

    if stage == "temporal":
        ok, reason = _require_list(payload, "events")
        if not ok:
            return ok, reason
        ok, reason = _require_list(payload, "temporal_relations")
        if not ok:
            return ok, reason
        events = payload.get("events") or []
        ok, reason = _validate_items(events, ["trigger", "category", "evidence"])
        if not ok:
            return ok, reason
        relations = payload.get("temporal_relations") or []
        for idx, rel in enumerate(relations):
            if not isinstance(rel, dict):
                return False, f"item_not_dict:{idx}"
            if not _is_str(rel.get("source_event")):
                return False, "field:source_event"
            if not _is_str(rel.get("relation_type")):
                return False, "field:relation_type"
            if not _is_str(rel.get("evidence")):
                return False, "field:evidence"
            if not (_is_str(rel.get("target_event")) or _is_str(rel.get("target_time"))):
                return False, "field:target_event_or_time"
        return True, ""

    if stage == "causal":
        ok, reason = _require_list(payload, "causal_relations")
        if not ok:
            return ok, reason
        relations = payload.get("causal_relations") or []
        for idx, rel in enumerate(relations):
            if not isinstance(rel, dict):
                return False, f"item_not_dict:{idx}"
            if not _is_str(rel.get("cause_event")):
                return False, "field:cause_event"
            if not _is_str(rel.get("effect_event")):
                return False, "field:effect_event"
            if not _is_str(rel.get("relation_type")):
                return False, "field:relation_type"
            if not _is_str(rel.get("logic_type")):
                return False, "field:logic_type"
            if not _is_str(rel.get("evidence")):
                return False, "field:evidence"
        return True, ""

    return True, ""
