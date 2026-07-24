#!/usr/bin/env python3
"""
事件知识抽取入口。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
    get_domain_event_prompt as get_prompt,
)


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


def _event_name(event: dict) -> str:
    return str(
        event.get("event")
        or event.get("description")
        or event.get("trigger")
        or event.get("event_id")
        or ""
    ).strip()


def _normalize_events(payload: dict) -> List[dict]:
    events = []
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        events.append(item)
    return events


def _merge_argument_value(base_value, new_value):
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
    if isinstance(base_value, dict) and isinstance(new_value, dict):
        for key, value in new_value.items():
            if key not in base_value or base_value[key] in (None, "", [], {}):
                base_value[key] = value
        return base_value
    if isinstance(base_value, str) and isinstance(new_value, str):
        if new_value == base_value:
            return base_value
        return [base_value, new_value]
    return base_value


def _merge_events(target: List[dict], new_events: List[dict]) -> None:
    index: Dict[str, dict] = {}
    for item in target:
        if not isinstance(item, dict):
            continue
        name = _event_name(item)
        if name:
            index[name] = item
    for item in new_events or []:
        if not isinstance(item, dict):
            continue
        name = _event_name(item)
        if not name:
            continue
        existing = index.get(name)
        if existing is None:
            target.append(item)
            index[name] = item
            continue
        for key in ("description", "trigger", "category", "subtype", "event_id", "evidence"):
            if not existing.get(key) and item.get(key):
                existing[key] = item.get(key)
        existing_args = existing.get("arguments") if isinstance(existing.get("arguments"), dict) else {}
        new_args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        for role, value in new_args.items():
            if role not in existing_args:
                existing_args[role] = value
            else:
                existing_args[role] = _merge_argument_value(existing_args[role], value)
        if existing_args:
            existing["arguments"] = existing_args


def _merge_candidates(target: Dict[str, list], new_candidates: Dict[str, list]) -> None:
    if not isinstance(new_candidates, dict):
        return
    items = new_candidates.get("events")
    if not isinstance(items, list):
        return
    bucket = target.setdefault("events", [])
    for item in items:
        if item not in bucket:
            bucket.append(item)


def _build_event_cypher(doc_id: str, events: List[dict]) -> str:
    lines = []
    for event in events:
        name = _event_name(event)
        if not name:
            continue
        name = escape_cypher_string(str(name))
        desc = escape_cypher_string(str(event.get("description") or ""))
        trigger = escape_cypher_string(str(event.get("trigger") or ""))
        category = escape_cypher_string(str(event.get("category") or ""))
        subtype = escape_cypher_string(str(event.get("subtype") or ""))
        event_id = escape_cypher_string(str(event.get("event_id") or ""))
        evidence = escape_cypher_string(str(event.get("evidence") or ""))
        section_id = escape_cypher_string(str(event.get("section_id") or ""))
        section_title = escape_cypher_string(str(event.get("section_title") or ""))
        paragraph_index = event.get("paragraph_index")
        section_clause = f', e.section_id = "{section_id}"' if section_id else ""
        title_clause = f', e.section_title = "{section_title}"' if section_title else ""
        para_clause = f", e.paragraph_index = {int(paragraph_index)}" if isinstance(paragraph_index, int) else ""
        located = event.get("source_located")
        method = escape_cypher_string(str(event.get("locate_method") or ""))
        located_clause = f", e.source_located = {str(bool(located)).lower()}" if located is not None else ""
        method_clause = f', e.locate_method = "{method}"' if method else ""
        arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
        args_json = escape_cypher_string(json.dumps(arguments, ensure_ascii=False))
        lines.append(
            f"MERGE (e:Event {{name: \"{name}\", doc_id: \"{doc_id}\"}}) "
            f"SET e.description = \"{desc}\", e.trigger = \"{trigger}\", "
            f"e.category = \"{category}\", e.subtype = \"{subtype}\", "
            f"e.event_id = \"{event_id}\", e.evidence = \"{evidence}\", "
            f"e.arguments = \"{args_json}\""
            f"{section_clause}{title_clause}{para_clause}{located_clause}{method_clause}"
        )
    return ";\n".join(lines) + ";\n"


def _split_argument_text(value: str) -> List[str]:
    if not value:
        return []
    for sep in ("、", "，", ",", ";", "；", "/"):
        value = value.replace(sep, "|")
    parts = [part.strip() for part in value.split("|")]
    return [part for part in parts if part]


def _expand_argument_values(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, dict):
        # rate 等结构化字段保留在事件属性中，不做建边
        return []
    else:
        values = [value]
    results: List[str] = []
    for item in values:
        text = str(item).strip()
        results.extend(_split_argument_text(text))
    return results


def _build_event_argument_cypher(doc_id: str, events: List[dict]) -> str:
    lines = []
    role_to_label = {
        "time": "Time",
        "stage": "Time",
    }
    role_to_relation = {
        "indicator": "INDICATOR",
        "comparator": "COMPARED_TO",
        "crop": "APPLIES_TO",
        "variety": "APPLIES_TO",
        "location": "AT_LOCATION",
        "method": "USES_METHOD",
        "treatment_level": "HAS_LEVEL",
        "time": "OCCUR_AT",
        "stage": "OCCUR_AT",
    }
    argument_roles = {
        "crop",
        "variety",
        "location",
        "indicator",
        "method",
        "treatment_level",
        "comparator",
        "time",
        "stage",
    }
    for event in events:
        name = _event_name(event)
        if not name:
            continue
        trigger_raw = str(event.get("trigger") or "").strip()
        source = escape_cypher_string(name)
        evidence = escape_cypher_string(str(event.get("evidence") or ""))
        section_id = escape_cypher_string(str(event.get("section_id") or ""))
        section_title = escape_cypher_string(str(event.get("section_title") or ""))
        paragraph_index = event.get("paragraph_index")
        section_clause = f', r.section_id = "{section_id}"' if section_id else ""
        title_clause = f', r.section_title = "{section_title}"' if section_title else ""
        para_clause = f", r.paragraph_index = {int(paragraph_index)}" if isinstance(paragraph_index, int) else ""
        located = event.get("source_located")
        method = escape_cypher_string(str(event.get("locate_method") or ""))
        located_clause = f", r.source_located = {str(bool(located)).lower()}" if located is not None else ""
        method_clause = f', r.locate_method = "{method}"' if method else ""
        arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
        for role, raw_value in arguments.items():
            if role not in argument_roles:
                continue
            values = _expand_argument_values(raw_value)
            for value in values:
                if role == "method" and value in {name, trigger_raw}:
                    continue
                rel_type = normalize_relation_type(role_to_relation.get(role, "RELATES_TO"))
                role_escaped = escape_cypher_string(role)
                target = escape_cypher_string(value)
                label = role_to_label.get(role, "Entity")
                if label == "Time":
                    lines.append(
                        f"MERGE (t:Time {{name: \"{target}\", doc_id: \"{doc_id}\"}}) "
                        f"MERGE (e:Event {{name: \"{source}\", doc_id: \"{doc_id}\"}}) "
                        f"MERGE (e)-[r:{rel_type} {{doc_id: \"{doc_id}\", role: \"{role_escaped}\"}}]->(t) "
                        f"SET r.evidence = \"{evidence}\"{section_clause}{title_clause}{para_clause}{located_clause}{method_clause}"
                    )
                else:
                    role_type = escape_cypher_string(role)
                    lines.append(
                        f"MERGE (t:Entity {{name: \"{target}\", doc_id: \"{doc_id}\"}}) "
                        f"SET t.type = coalesce(t.type, \"{role_type}\") "
                        f"MERGE (e:Event {{name: \"{source}\", doc_id: \"{doc_id}\"}}) "
                        f"MERGE (e)-[r:{rel_type} {{doc_id: \"{doc_id}\", role: \"{role_escaped}\"}}]->(t) "
                        f"SET r.evidence = \"{evidence}\"{section_clause}{title_clause}{para_clause}{located_clause}{method_clause}"
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


async def run_domain_event() -> None:
    _, knowledge_dir, log_dir = get_results_dirs()
    sample_doc = four_stage_dir / "resources" / "samples" / "event_sample.md"
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
    log_file = log_dir / f"domain_event_prompt_log_{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file, append_log = resolve_log_file(log_file)
    tee = TeeLogger(log_file, name="domain_event", append=append_log)
    sys.stdout = tee

    load_dotenv(dotenv_path=project_root / ".env", override=True)
    previous_stream_stdout = os.getenv("LLM_STREAM_STDOUT")
    previous_stream_raw_file = os.getenv("LLM_STREAM_RAW_FILE")
    os.environ["LLM_STREAM_STDOUT"] = "0"
    setup_logging_from_config()

    print("=" * 60)
    print("事件知识抽取")
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
    raw_output_file = doc_dir / f"domain_event_prompt_raw_{doc_id}_{run_ts}.jsonl"

    merged_payload = {
        "schema_version": "1.0",
        "doc_id": doc_id,
        "source": {"source_type": "domain_event"},
        "events": [],
        "candidates": {"events": []},
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
            ok, reason = validate_payload("event", chunk_payload)
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
        _merge_events(merged_payload["events"], chunk_payload.get("events") or [])
        _merge_candidates(merged_payload.get("candidates", {}), chunk_payload.get("candidates") or {})
        for warning in chunk_payload.get("warnings") or []:
            if isinstance(warning, str):
                warnings_seen.add(warning)

    merged_payload["warnings"] = sorted(warnings_seen)
    payload = merged_payload
    section_index = build_section_index(content, doc_id)
    unmatched = 0
    unmatched += annotate_items(payload.get("events") or [], section_index, evidence_key="evidence")
    candidates = payload.get("candidates") or {}
    if isinstance(candidates, dict):
        unmatched += annotate_items(
            candidates.get("events") or [], section_index, evidence_key="evidence"
        )
    if unmatched:
        warnings = payload.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
            payload["warnings"] = warnings
        warnings.append(f"source_locate_unmatched:{unmatched}")

    events = _normalize_events(payload)

    result_file = doc_dir / f"domain_event_prompt_results_{doc_id}_{run_ts}.json"
    result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {result_file}")

    cypher_file = doc_dir / f"domain_event_prompt_graph_{doc_id}_{run_ts}.cypher"
    cypher = _build_event_cypher(doc_id, events)
    cypher += _build_event_argument_cypher(doc_id, events)
    cypher_file.write_text(cypher, encoding="utf-8")
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
    asyncio.run(run_domain_event())
