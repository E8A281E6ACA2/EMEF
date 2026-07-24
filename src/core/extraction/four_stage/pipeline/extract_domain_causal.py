#!/usr/bin/env python3
"""
因果关系抽取入口。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


def _find_project_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "src").is_dir():
            return parent
    raise RuntimeError("无法定位项目根目录（未找到src目录）")


file_path = Path(__file__).resolve()
project_root = _find_project_root(file_path)
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

four_stage_dir = file_path.parent.parent
pipeline_dir = four_stage_dir / "pipeline"
resources_dir = four_stage_dir / "resources"
for path in (four_stage_dir, pipeline_dir, resources_dir):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.config.settings import Settings  # noqa: E402
from src.utils.logger import setup_logging_from_config  # noqa: E402
from cypher_utils import escape_cypher_string, normalize_relation_type  # noqa: E402
from logging_utils import TeeLogger, resolve_log_file  # noqa: E402
from result_paths import get_doc_dir, get_results_dirs  # noqa: E402
from llm_retry_client import LLMRetryClient  # noqa: E402
from chunk_utils import split_content  # noqa: E402
from source_locator import annotate_items, build_section_index  # noqa: E402
from schema_validator import validate_payload, schema_retry_config  # noqa: E402
from src.core.extraction.four_stage.resources.prompts.i18n_extractors import (  # noqa: E402
    get_domain_causal_prompt as get_prompt,
)
from event_name_align import align_event_name, load_event_names  # noqa: E402


def _restore_env(name: str, value: Optional[str]) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _finalize_log(tee: TeeLogger, log_file: Path) -> None:
    sys.stdout = tee.terminal
    tee.close()
    print(f"日志已保存: {log_file}")


def _should_write_neo4j() -> bool:
    return False


def _safe_json_load(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        def _escape_invalid_backslashes(raw: str) -> str:
            return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", raw)

        escaped = _escape_invalid_backslashes(cleaned)
        try:
            return json.loads(escaped)
        except json.JSONDecodeError:
            cleaned = escaped
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(cleaned):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(cleaned[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _env_int(names: List[str], default: int) -> int:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return default


def _normalize_rel_key(raw: str) -> str:
    text = str(raw or "").strip().lower()
    text = text.replace("-", "_").replace(" ", "_")
    return text


_CAUSAL_REL_CANONICAL = {
    "CAUSES",
    "RESULTS_IN",
    "PROMOTES",
    "INHIBITS",
    "CORRELATES_WITH",
    "TRIGGERS",
    "PREREQUISITE_FOR",
    "PURPOSE_OF",
}

_CAUSAL_REL_ALIASES = {
    "cause": "CAUSES",
    "causes": "CAUSES",
    "lead_to": "CAUSES",
    "leads_to": "CAUSES",
    "result_in": "RESULTS_IN",
    "results_in": "RESULTS_IN",
    "results": "RESULTS_IN",
    "result": "RESULTS_IN",
    "trigger": "TRIGGERS",
    "triggers": "TRIGGERS",
    "promote": "PROMOTES",
    "promotes": "PROMOTES",
    "increase": "PROMOTES",
    "increases": "PROMOTES",
    "enhance": "PROMOTES",
    "enhances": "PROMOTES",
    "improve": "PROMOTES",
    "improves": "PROMOTES",
    "inhibit": "INHIBITS",
    "inhibits": "INHIBITS",
    "decrease": "INHIBITS",
    "decreases": "INHIBITS",
    "reduce": "INHIBITS",
    "reduces": "INHIBITS",
    "suppress": "INHIBITS",
    "suppresses": "INHIBITS",
    "correlate": "CORRELATES_WITH",
    "correlates": "CORRELATES_WITH",
    "correlation": "CORRELATES_WITH",
    "associated_with": "CORRELATES_WITH",
    "associate_with": "CORRELATES_WITH",
    "prerequisite": "PREREQUISITE_FOR",
    "prerequisite_for": "PREREQUISITE_FOR",
    "precondition": "PREREQUISITE_FOR",
    "purpose": "PURPOSE_OF",
    "purpose_of": "PURPOSE_OF",
    "导致": "CAUSES",
    "引起": "CAUSES",
    "造成": "CAUSES",
    "使得": "CAUSES",
    "结果是": "RESULTS_IN",
    "促进": "PROMOTES",
    "提高": "PROMOTES",
    "增加": "PROMOTES",
    "改善": "PROMOTES",
    "抑制": "INHIBITS",
    "降低": "INHIBITS",
    "减少": "INHIBITS",
    "减轻": "INHIBITS",
    "触发": "TRIGGERS",
    "相关": "CORRELATES_WITH",
    "正相关": "CORRELATES_WITH",
    "负相关": "CORRELATES_WITH",
    "前提": "PREREQUISITE_FOR",
    "目的": "PURPOSE_OF",
}

_POLARITY_ALIASES = {
    "promote": "PROMOTE",
    "positive": "PROMOTE",
    "促进": "PROMOTE",
    "inhibit": "INHIBIT",
    "negative": "INHIBIT",
    "抑制": "INHIBIT",
    "neutral": "NEUTRAL",
    "中性": "NEUTRAL",
    "correlate": "CORRELATE",
    "correlation": "CORRELATE",
    "相关": "CORRELATE",
    "正相关": "CORRELATE",
    "负相关": "CORRELATE",
}

_LOGIC_TYPE_CANONICAL = {
    "physiological_response",
    "stress_disturbance",
    "agronomic_intervention",
    "temporal_evolution",
    "other",
}

_LOGIC_TYPE_ALIASES = {
    "physiological_response": "physiological_response",
    "physiology_response": "physiological_response",
    "physiological": "physiological_response",
    "生理响应": "physiological_response",
    "生理反应": "physiological_response",
    "stress_disturbance": "stress_disturbance",
    "stress": "stress_disturbance",
    "disturbance": "stress_disturbance",
    "逆境胁迫": "stress_disturbance",
    "胁迫": "stress_disturbance",
    "agronomic_intervention": "agronomic_intervention",
    "agronomic": "agronomic_intervention",
    "management_intervention": "agronomic_intervention",
    "农事干预": "agronomic_intervention",
    "农业干预": "agronomic_intervention",
    "管理干预": "agronomic_intervention",
    "temporal_evolution": "temporal_evolution",
    "temporal": "temporal_evolution",
    "time_evolution": "temporal_evolution",
    "时序演化": "temporal_evolution",
    "时序变化": "temporal_evolution",
    "other": "other",
    "others": "other",
    "其他": "other",
}


def _canonical_causal_relation(raw: str) -> str:
    key = _normalize_rel_key(raw)
    if not key:
        return ""
    mapped = _CAUSAL_REL_ALIASES.get(key)
    if mapped:
        return mapped
    cleaned = normalize_relation_type(str(raw))
    return cleaned if cleaned in _CAUSAL_REL_CANONICAL else ""


def _canonical_polarity(raw: str) -> str:
    key = _normalize_rel_key(raw)
    if not key:
        return ""
    mapped = _POLARITY_ALIASES.get(key)
    if mapped:
        return mapped
    cleaned = normalize_relation_type(str(raw))
    return cleaned if cleaned in {"PROMOTE", "INHIBIT", "NEUTRAL", "CORRELATE"} else ""


def _canonical_logic_type(raw: str) -> str:
    key = _normalize_rel_key(raw)
    if not key:
        return "other"
    mapped = _LOGIC_TYPE_ALIASES.get(key)
    if mapped:
        return mapped
    # normalize_relation_type returns uppercase tokens; logic_type remains lowercase snake_case.
    cleaned = normalize_relation_type(str(raw)).lower()
    cleaned = cleaned.replace("-", "_")
    return cleaned if cleaned in _LOGIC_TYPE_CANONICAL else "other"


def _resolve_relation_and_polarity(raw_rel_type: str, raw_polarity: str) -> Tuple[str, str]:
    rel_type = _canonical_causal_relation(raw_rel_type)
    polarity = _canonical_polarity(raw_polarity)

    if not rel_type:
        if polarity == "PROMOTE":
            rel_type = "PROMOTES"
        elif polarity == "INHIBIT":
            rel_type = "INHIBITS"
        elif polarity == "CORRELATE":
            rel_type = "CORRELATES_WITH"
        else:
            rel_type = "CAUSES"

    if rel_type == "CORRELATES_WITH":
        polarity = "CORRELATE"
    elif rel_type in {"PREREQUISITE_FOR", "PURPOSE_OF"}:
        polarity = "NEUTRAL"
    elif rel_type == "PROMOTES":
        polarity = "PROMOTE"
    elif rel_type == "INHIBITS":
        polarity = "INHIBIT"
    elif rel_type in {"CAUSES", "RESULTS_IN", "TRIGGERS"}:
        if polarity not in {"PROMOTE", "INHIBIT", "NEUTRAL"}:
            polarity = "NEUTRAL"
    return rel_type, polarity


def _canonicalize_causal_relation_item(item: dict) -> dict:
    rel_type, polarity = _resolve_relation_and_polarity(
        str(item.get("relation_type") or item.get("type") or ""),
        str(item.get("polarity") or ""),
    )
    logic_type = _canonical_logic_type(str(item.get("logic_type") or ""))
    item["relation_type"] = rel_type
    item["polarity"] = polarity
    item["logic_type"] = logic_type
    return item


def _canonicalize_causal_relations(relations: List[dict]) -> None:
    for rel in relations or []:
        if isinstance(rel, dict):
            _canonicalize_causal_relation_item(rel)


def _merge_list_value(base_value, new_value):
    if base_value in (None, "", [], {}):
        return new_value
    if isinstance(base_value, list):
        if isinstance(new_value, list):
            for item in new_value:
                if item not in base_value:
                    base_value.append(item)
        else:
            if new_value not in base_value:
                base_value.append(new_value)
        return base_value
    if isinstance(base_value, str) and isinstance(new_value, str):
        if new_value == base_value:
            return base_value
        return [base_value, new_value]
    return base_value


def _merge_relations(target: List[dict], new_relations: List[dict]) -> None:
    index: Dict[Tuple[str, str, str, str], dict] = {}
    for item in target:
        if not isinstance(item, dict):
            continue
        item = _canonicalize_causal_relation_item(item)
        cause = str(item.get("cause_event") or item.get("source_event") or "").strip()
        effect = str(item.get("effect_event") or item.get("target_event") or "").strip()
        rel_type = str(item.get("relation_type") or "CAUSES").strip()
        polarity = str(item.get("polarity") or "").strip()
        if cause and effect:
            index[(cause, effect, rel_type, polarity)] = item
    for item in new_relations or []:
        if not isinstance(item, dict):
            continue
        item = _canonicalize_causal_relation_item(item)
        cause = str(item.get("cause_event") or item.get("source_event") or "").strip()
        effect = str(item.get("effect_event") or item.get("target_event") or "").strip()
        rel_type = str(item.get("relation_type") or "CAUSES").strip()
        polarity = str(item.get("polarity") or "").strip()
        if not cause or not effect:
            continue
        key = (cause, effect, rel_type, polarity)
        existing = index.get(key)
        if existing is None:
            target.append(item)
            index[key] = item
            continue
        if not existing.get("cause_event") and item.get("cause_event"):
            existing["cause_event"] = item.get("cause_event")
        if not existing.get("effect_event") and item.get("effect_event"):
            existing["effect_event"] = item.get("effect_event")
        for key_name in ("relation_type", "type", "logic_type", "polarity"):
            if not existing.get(key_name) and item.get(key_name):
                existing[key_name] = item.get(key_name)
        existing_evidence = str(existing.get("evidence") or "").strip()
        new_evidence = str(item.get("evidence") or "").strip()
        if not existing_evidence and new_evidence:
            existing["evidence"] = new_evidence
        if existing.get("strength") in (None, "", 0) and item.get("strength") not in (None, "", 0):
            existing["strength"] = item.get("strength")
        for key_name in ("time_lag", "stage", "crop"):
            if existing.get(key_name) in (None, "", [], {}):
                if item.get(key_name) not in (None, "", [], {}):
                    existing[key_name] = item.get(key_name)
            else:
                merged = _merge_list_value(existing.get(key_name), item.get(key_name))
                if merged is not None:
                    existing[key_name] = merged
        for key_name in ("mechanism", "conditions"):
            merged = _merge_list_value(existing.get(key_name), item.get(key_name))
            if merged is not None:
                existing[key_name] = merged


def _build_causal_cypher(doc_id: str, relations: List[dict], event_name_candidates: List[str]) -> str:
    lines = []
    for rel in relations:
        cause_raw = str(rel.get("cause_event") or rel.get("source_event") or "").strip()
        effect_raw = str(rel.get("effect_event") or rel.get("target_event") or "").strip()
        evidence_text = str(rel.get("evidence") or "")
        cause_raw = align_event_name(cause_raw, event_name_candidates, evidence_text)
        effect_raw = align_event_name(effect_raw, event_name_candidates, evidence_text)
        if cause_raw and effect_raw and cause_raw == effect_raw:
            continue
        cause = escape_cypher_string(cause_raw)
        effect = escape_cypher_string(effect_raw)
        rel_type_raw = str(rel.get("relation_type") or rel.get("type") or "")
        polarity_raw = str(rel.get("polarity") or "")
        rel_type, polarity_norm = _resolve_relation_and_polarity(rel_type_raw, polarity_raw)
        evidence = escape_cypher_string(str(rel.get("evidence") or ""))
        section_id = escape_cypher_string(str(rel.get("section_id") or ""))
        section_title = escape_cypher_string(str(rel.get("section_title") or ""))
        paragraph_index = rel.get("paragraph_index")
        section_clause = f', r.section_id = "{section_id}"' if section_id else ""
        title_clause = f', r.section_title = "{section_title}"' if section_title else ""
        para_clause = f", r.paragraph_index = {int(paragraph_index)}" if isinstance(paragraph_index, int) else ""
        located = rel.get("source_located")
        method = escape_cypher_string(str(rel.get("locate_method") or ""))
        located_clause = f", r.source_located = {str(bool(located)).lower()}" if located is not None else ""
        method_clause = f', r.locate_method = "{method}"' if method else ""
        if not cause or not effect:
            continue
        logic_type_norm = _canonical_logic_type(str(rel.get("logic_type") or ""))
        logic_type = escape_cypher_string(logic_type_norm)
        polarity = escape_cypher_string(polarity_norm)
        strength = rel.get("strength")
        attributes = {}
        for key in ("time_lag", "stage", "conditions", "mechanism", "crop"):
            value = rel.get(key)
            if value not in (None, "", []):
                attributes[key] = value
        attrs_json = escape_cypher_string(json.dumps(attributes, ensure_ascii=False))
        strength_clause = ""
        if isinstance(strength, (int, float)):
            strength_clause = f", r.strength = {float(strength)}"
        lines.append(
            f"MERGE (c:Event {{name: \"{cause}\", doc_id: \"{doc_id}\"}}) "
            f"MERGE (e:Event {{name: \"{effect}\", doc_id: \"{doc_id}\"}}) "
            f"MERGE (c)-[r:{rel_type} {{doc_id: \"{doc_id}\"}}]->(e) "
            f"SET r.evidence = \"{evidence}\", r.logic_type = \"{logic_type}\", "
            f"r.polarity = \"{polarity}\", r.attributes = \"{attrs_json}\"{strength_clause}"
            f"{section_clause}{title_clause}{para_clause}{located_clause}{method_clause}"
        )
    return ";\n".join(lines) + ";\n"


async def _apply_cypher(cypher_file: Path, settings: Settings) -> None:
    driver = AsyncGraphDatabase.driver(
        settings.graph_storage.neo4j_uri,
        auth=(settings.graph_storage.neo4j_user, settings.graph_storage.neo4j_password),
    )
    try:
        async with driver.session(database=settings.graph_storage.neo4j_database) as session:
            statements = cypher_file.read_text(encoding="utf-8").split(";\n")
            for statement in statements:
                stmt = statement.strip()
                if not stmt:
                    continue
                await session.run(stmt)
    finally:
        await driver.close()


async def run_domain_causal() -> None:
    _, knowledge_dir, log_dir = get_results_dirs()
    sample_doc = four_stage_dir / "resources" / "samples" / "causal_sample.md"
    raw_arg = sys.argv[1].strip().strip("\"'") if len(sys.argv) > 1 else ""
    doc_path = Path(raw_arg) if raw_arg else sample_doc
    if doc_path.exists() and doc_path.is_dir():
        if sample_doc.exists():
            print(f"传入的是目录，改用样本: {sample_doc}", flush=True)
            doc_path = sample_doc
        else:
            print(f"传入的是目录，请提供MD文件路径: {doc_path}", flush=True)
            return
    if not doc_path.exists():
        print(f"未找到MD文件: {doc_path}", flush=True)
        return

    doc_id = doc_path.stem
    log_file = log_dir / f"domain_causal_prompt_log_{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file, append_log = resolve_log_file(log_file)
    tee = TeeLogger(log_file, name="domain_causal", append=append_log)
    sys.stdout = tee

    load_dotenv(dotenv_path=project_root / ".env", override=True)
    previous_stream_stdout = os.getenv("LLM_STREAM_STDOUT")
    previous_stream_raw_file = os.getenv("LLM_STREAM_RAW_FILE")
    os.environ["LLM_STREAM_STDOUT"] = "0"
    setup_logging_from_config()

    print("=" * 60)
    print("因果关系抽取")
    print("=" * 60)
    print(f"日志文件: {log_file}")
    print()

    settings = Settings()
    if not settings.llm.openai_api_key:
        print("未配置OPENAI_API_KEY，无法调用LLM", flush=True)
        _restore_env("LLM_STREAM_STDOUT", previous_stream_stdout)
        _restore_env("LLM_STREAM_RAW_FILE", previous_stream_raw_file)
        _finalize_log(tee, log_file)
        raise SystemExit("LLM调用失败: 未配置OPENAI_API_KEY")

    content = doc_path.read_text(encoding="utf-8", errors="ignore")
    chunk_max_chars = _env_int(["EXTRACTION_CHUNK_MAX_CHARS", "LLM_CHUNK_MAX_CHARS"], 0)
    chunk_overlap_chars = _env_int(
        ["EXTRACTION_CHUNK_OVERLAP_CHARS", "LLM_CHUNK_OVERLAP_CHARS"], 0
    )
    chunks = split_content(content, chunk_max_chars, chunk_overlap_chars)
    if not chunks:
        print("文档内容为空，跳过抽取", flush=True)
        _restore_env("LLM_STREAM_STDOUT", previous_stream_stdout)
        _restore_env("LLM_STREAM_RAW_FILE", previous_stream_raw_file)
        _finalize_log(tee, log_file)
        return
    if len(chunks) > 1:
        print(
            f"文本过长，拆分为 {len(chunks)} 段 (max_chars={chunk_max_chars}, overlap={chunk_overlap_chars})",
            flush=True,
        )

    schema_validate, schema_retry_max, schema_retry_suffix = schema_retry_config()
    if schema_validate:
        print(f"Schema校验已开启: retry_max={schema_retry_max}", flush=True)

    llm_client = LLMRetryClient(
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_base_url,
        model=settings.llm.openai_model,
        max_retries=settings.llm.openai_max_retries,
        timeout=settings.llm.openai_timeout,
    )

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_dir = get_doc_dir(doc_id, knowledge_dir)
    raw_output_file = doc_dir / f"domain_causal_prompt_raw_{doc_id}_{run_ts}.jsonl"

    merged_payload = {
        "schema_version": "1.0",
        "doc_id": doc_id,
        "source": {"source_type": "domain_causal"},
        "causal_relations": [],
        "warnings": [],
    }
    warnings_seen = set()
    for idx, chunk in enumerate(chunks, 1):
        print(f"分块 {idx}/{len(chunks)} | 字符数 {len(chunk)}", flush=True)
        base_prompt = get_prompt(chunk, {"doc_id": doc_id})
        os.environ["LLM_STREAM_RAW_FILE"] = str(raw_output_file)
        chunk_payload: dict = {}
        last_reason = ""
        for attempt in range(schema_retry_max + 1):
            prompt = base_prompt if attempt == 0 else base_prompt + "\n\n" + schema_retry_suffix
            response = await llm_client.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.extraction_temperature,
                max_tokens=settings.llm.extraction_max_tokens,
            )
            chunk_payload = _safe_json_load(response) or {}
            if not schema_validate:
                break
            ok, reason = validate_payload("causal", chunk_payload)
            if ok:
                if attempt > 0:
                    warnings_seen.add(f"chunk_{idx}_schema_retry_success_{attempt}")
                break
            last_reason = reason
            warnings_seen.add(f"chunk_{idx}_schema_invalid_{attempt+1}:{reason}")
            if attempt >= schema_retry_max:
                chunk_payload = {}
        if schema_validate and last_reason:
            print(f"schema校验未通过: chunk={idx}, reason={last_reason}", flush=True)
        if not isinstance(chunk_payload, dict):
            warnings_seen.add(f"chunk_{idx}_invalid_json")
            continue
        _merge_relations(merged_payload["causal_relations"], chunk_payload.get("causal_relations") or [])
        for warning in chunk_payload.get("warnings") or []:
            if isinstance(warning, str):
                warnings_seen.add(warning)

    merged_payload["warnings"] = sorted(warnings_seen)
    payload = merged_payload
    section_index = build_section_index(content, doc_id)
    unmatched = 0
    unmatched += annotate_items(
        payload.get("causal_relations") or [], section_index, evidence_key="evidence"
    )
    candidates = payload.get("candidates") or {}
    if isinstance(candidates, dict):
        unmatched += annotate_items(
            candidates.get("causal_relations") or [], section_index, evidence_key="evidence"
        )
    if unmatched:
        warnings = payload.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
            payload["warnings"] = warnings
        warnings.append(f"source_locate_unmatched:{unmatched}")

    relations = payload.get("causal_relations") or []
    _canonicalize_causal_relations(relations)
    candidates = payload.get("candidates") or {}
    if isinstance(candidates, dict):
        _canonicalize_causal_relations(candidates.get("causal_relations") or [])

    result_file = doc_dir / f"domain_causal_prompt_results_{doc_id}_{run_ts}.json"
    result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {result_file}")

    cypher_file = doc_dir / f"domain_causal_prompt_graph_{doc_id}_{run_ts}.cypher"
    event_name_candidates = load_event_names(doc_dir, doc_id)
    cypher_file.write_text(
        _build_causal_cypher(doc_id, relations, event_name_candidates),
        encoding="utf-8",
    )
    print(f"Cypher已保存: {cypher_file}")

    if _should_write_neo4j():
        try:
            await _apply_cypher(cypher_file, settings)
            print("Neo4j写入完成")
        except Exception as exc:
            print(f"Neo4j写入失败: {exc}")

    await llm_client.close()
    _restore_env("LLM_STREAM_STDOUT", previous_stream_stdout)
    _restore_env("LLM_STREAM_RAW_FILE", previous_stream_raw_file)
    _finalize_log(tee, log_file)


if __name__ == "__main__":
    asyncio.run(run_domain_causal())
