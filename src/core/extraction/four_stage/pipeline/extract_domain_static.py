#!/usr/bin/env python3
"""
静态知识抽取入口（实体与关系）。
"""

from __future__ import annotations

import asyncio
import json
import string
import os
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
from cypher_utils import escape_cypher_string, format_entity_label, normalize_relation_type  # noqa: E402
from logging_utils import TeeLogger, resolve_log_file  # noqa: E402
from models import Relation, Entity  # noqa: E402
from result_paths import get_doc_dir, get_results_dirs  # noqa: E402
from llm_retry_client import LLMRetryClient  # noqa: E402
from chunk_utils import split_content  # noqa: E402
from source_locator import annotate_items, build_section_index  # noqa: E402
from schema_validator import validate_payload, schema_retry_config  # noqa: E402
from src.core.extraction.four_stage.resources.prompts.i18n_extractors import (  # noqa: E402
    get_domain_static_prompt as get_prompt,
)

_PERSON_TYPES = {
    "人",
    "人物",
    "人员",
    "作者",
    "研究人员",
    "person",
    "people",
    "researcher",
    "author",
}
_ORG_TYPES = {
    "机构",
    "单位",
    "组织",
    "公司",
    "学校",
    "高校",
    "研究院",
    "研究所",
    "部门",
    "局",
    "organization",
    "organisation",
    "institute",
    "institution",
    "university",
    "company",
    "department",
    "lab",
    "laboratory",
}


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
    candidates = [cleaned]
    repaired = _repair_invalid_json_escapes(cleaned)
    if repaired != cleaned:
        candidates.append(repaired)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for idx, ch in enumerate(candidate):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _repair_invalid_json_escapes(text: str) -> str:
    if not text:
        return text
    out: List[str] = []
    in_string = False
    escaped = False
    hex_digits = set(string.hexdigits)
    i = 0
    while i < len(text):
        ch = text[i]
        if not in_string:
            if ch == "\"":
                in_string = True
            out.append(ch)
            i += 1
            continue
        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt == "u":
                hex_part = text[i + 2 : i + 6]
                if len(hex_part) != 4 or any(c not in hex_digits for c in hex_part):
                    out.append("\\\\")
                    i += 1
                    continue
            if nxt and nxt not in {"\"", "\\", "/", "b", "f", "n", "r", "t", "u"}:
                out.append("\\\\")
                i += 1
                continue
            out.append("\\")
            escaped = True
            i += 1
            continue
        if ch == "\"":
            in_string = False
        out.append(ch)
        i += 1
    if escaped:
        out.append("\\")
    return "".join(out)


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


def _merge_dict_values(base: Dict[str, object], new: Dict[str, object]) -> None:
    for key, value in (new or {}).items():
        if key not in base or base[key] in ("", None, [], {}):
            base[key] = value
            continue
        base_value = base.get(key)
        if isinstance(base_value, list):
            if isinstance(value, list):
                for item in value:
                    if item not in base_value:
                        base_value.append(item)
            else:
                if value not in base_value:
                    base_value.append(value)
        elif isinstance(base_value, dict) and isinstance(value, dict):
            _merge_dict_values(base_value, value)


def _merge_entities(target: List[dict], new_entities: List[dict]) -> None:
    index: Dict[Tuple[str, str], dict] = {}
    for item in target:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or "").strip()
        if name and entity_type:
            index[(name, entity_type)] = item
    for item in new_entities or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or "").strip()
        if not name or not entity_type:
            continue
        key = (name, entity_type)
        existing = index.get(key)
        if existing is None:
            target.append(item)
            index[key] = item
            continue
        if not existing.get("description") and item.get("description"):
            existing["description"] = item.get("description")
        if not existing.get("aliases") and item.get("aliases"):
            existing["aliases"] = item.get("aliases")
        if isinstance(existing.get("aliases"), list) and isinstance(item.get("aliases"), list):
            _merge_dict_values(
                {"aliases": existing.get("aliases")},
                {"aliases": item.get("aliases")},
            )
        existing_attrs = existing.get("attributes") if isinstance(existing.get("attributes"), dict) else {}
        new_attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        _merge_dict_values(existing_attrs, new_attrs)
        existing["attributes"] = existing_attrs


def _merge_relations(target: List[dict], new_relations: List[dict]) -> None:
    index: Dict[Tuple[str, str, str], dict] = {}
    for item in target:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target_name = str(item.get("target") or "").strip()
        rel_type = str(item.get("type") or item.get("relation_type") or "").strip()
        if source and target_name and rel_type:
            index[(source, target_name, rel_type)] = item
    for item in new_relations or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target_name = str(item.get("target") or "").strip()
        rel_type = str(item.get("type") or item.get("relation_type") or "").strip()
        if not source or not target_name or not rel_type:
            continue
        key = (source, target_name, rel_type)
        existing = index.get(key)
        if existing is None:
            target.append(item)
            index[key] = item
            continue
        existing_evidence = str(existing.get("evidence") or "").strip()
        new_evidence = str(item.get("evidence") or "").strip()
        if not existing_evidence and new_evidence:
            existing["evidence"] = new_evidence
        elif new_evidence and new_evidence != existing_evidence:
            attrs = existing.get("attributes") if isinstance(existing.get("attributes"), dict) else {}
            evidence_list = attrs.get("evidence_list")
            if not isinstance(evidence_list, list):
                evidence_list = [existing_evidence] if existing_evidence else []
            if new_evidence not in evidence_list:
                evidence_list.append(new_evidence)
            attrs["evidence_list"] = evidence_list
            existing["attributes"] = attrs
        existing_attrs = existing.get("attributes") if isinstance(existing.get("attributes"), dict) else {}
        new_attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        _merge_dict_values(existing_attrs, new_attrs)
        existing["attributes"] = existing_attrs


def _merge_candidates(target: Dict[str, list], new_candidates: Dict[str, list]) -> None:
    if not isinstance(new_candidates, dict):
        return
    for key in ("entities", "relations"):
        items = new_candidates.get(key)
        if not isinstance(items, list):
            continue
        bucket = target.setdefault(key, [])
        for item in items:
            if item not in bucket:
                bucket.append(item)


def _normalize_entity_type(entity_type: str, attrs: Dict[str, object]) -> str:
    normalized = (entity_type or "").strip()
    low = normalized.lower()
    if normalized in {"人", "人物", "人员"} or low in {"person", "people"}:
        if any(key in attrs for key in ("单位", "机构", "affiliation", "所属机构")):
            return "作者"
        return "研究人员"
    return normalized


def _normalize_entities(payload: dict, doc_id: str, section_id: str) -> List[Entity]:
    entities: List[Entity] = []
    for item in payload.get("entities") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or "").strip()
        if not name or not entity_type:
            continue
        attrs = dict(item.get("attributes") or {})
        entity_type = _normalize_entity_type(entity_type, attrs)
        item["type"] = entity_type
        if item.get("description"):
            attrs.setdefault("description", item.get("description"))
        aliases = item.get("aliases")
        if aliases:
            attrs.setdefault("aliases", aliases)
        item_section_id = str(item.get("section_id") or section_id)
        entities.append(
            Entity(
                name=name,
                type=entity_type,
                section_id=item_section_id,
                section_title=item.get("section_title"),
                paragraph_index=item.get("paragraph_index"),
                source_located=item.get("source_located"),
                locate_method=item.get("locate_method"),
                doc_id=doc_id,
                attributes=attrs,
            )
        )
    return entities


def _normalize_relations(
    payload: dict,
    doc_id: str,
    section_id: str,
    entity_type_map: Dict[str, str],
) -> List[Relation]:
    relations: List[Relation] = []
    for item in payload.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        rel_type = str(item.get("type") or item.get("relation_type") or "").strip()
        if not source or not target or not rel_type:
            continue
        source_type = entity_type_map.get(source, "")
        target_type = entity_type_map.get(target, "")
        source_type_low = source_type.lower() if isinstance(source_type, str) else ""
        target_type_low = target_type.lower() if isinstance(target_type, str) else ""
        source_is_org = source_type in _ORG_TYPES or source_type_low in _ORG_TYPES
        target_is_person = target_type in _PERSON_TYPES or target_type_low in _PERSON_TYPES
        if rel_type in {"所属机构", "任职于", "就职于"}:
            if source_is_org and target_is_person:
                source, target = target, source
                item["source"] = source
                item["target"] = target
        if rel_type in {"作者"}:
            if source_type in {"文献", "论文", "paper", "document"} and target_is_person:
                source, target = target, source
                item["source"] = source
                item["target"] = target
        item_section_id = str(item.get("section_id") or section_id)
        relations.append(
            Relation(
                source_entity=source,
                target_entity=target,
                relation_type=rel_type,
                section_id=item_section_id,
                section_title=item.get("section_title"),
                paragraph_index=item.get("paragraph_index"),
                source_located=item.get("source_located"),
                locate_method=item.get("locate_method"),
                doc_id=doc_id,
                evidence=item.get("evidence"),
                attributes=item.get("attributes") or {},
            )
        )
    return relations


def _build_entity_relation_cypher(doc_id: str, entities: List[Entity], relations: List[Relation]) -> str:
    lines = []
    for entity in entities:
        name = escape_cypher_string(entity.name)
        entity_type = escape_cypher_string(entity.type)
        label = format_entity_label(entity.type)
        attrs = escape_cypher_string(json.dumps(entity.attributes or {}, ensure_ascii=False))
        title = escape_cypher_string(str(entity.section_title or ""))
        para = entity.paragraph_index
        title_clause = f', n.section_title = "{title}"' if title else ""
        para_clause = f", n.paragraph_index = {int(para)}" if isinstance(para, int) else ""
        located = entity.source_located
        method = escape_cypher_string(str(entity.locate_method or ""))
        located_clause = f", n.source_located = {str(bool(located)).lower()}" if located is not None else ""
        method_clause = f', n.locate_method = "{method}"' if method else ""
        lines.append(
            f"MERGE (n{label} {{name: \"{name}\", doc_id: \"{doc_id}\"}}) "
            f"SET n.type = \"{entity_type}\", n.section_id = \"{escape_cypher_string(entity.section_id)}\", "
            f"n.attributes = \"{attrs}\"{title_clause}{para_clause}{located_clause}{method_clause}"
        )
    for relation in relations:
        rel_type = normalize_relation_type(relation.relation_type)
        source = escape_cypher_string(relation.source_entity)
        target = escape_cypher_string(relation.target_entity)
        evidence = escape_cypher_string(relation.evidence or "")
        title = escape_cypher_string(str(relation.section_title or ""))
        para = relation.paragraph_index
        title_clause = f', r.section_title = "{title}"' if title else ""
        para_clause = f", r.paragraph_index = {int(para)}" if isinstance(para, int) else ""
        located = relation.source_located
        method = escape_cypher_string(str(relation.locate_method or ""))
        located_clause = f", r.source_located = {str(bool(located)).lower()}" if located is not None else ""
        method_clause = f', r.locate_method = "{method}"' if method else ""
        lines.append(
            f"MATCH (s:Entity {{name: \"{source}\", doc_id: \"{doc_id}\"}}) "
            f"MATCH (t:Entity {{name: \"{target}\", doc_id: \"{doc_id}\"}}) "
            f"MERGE (s)-[r:{rel_type} {{doc_id: \"{doc_id}\"}}]->(t) "
            f"SET r.section_id = \"{escape_cypher_string(relation.section_id)}\", r.evidence = \"{evidence}\""
            f"{title_clause}{para_clause}{located_clause}{method_clause}"
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


async def run_domain_static() -> None:
    _, knowledge_dir, log_dir = get_results_dirs()
    sample_doc = four_stage_dir / "resources" / "samples" / "general_sample.md"
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
    log_file = log_dir / f"text_domain_prompt_log_{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file, append_log = resolve_log_file(log_file)
    tee = TeeLogger(log_file, name="domain_static", append=append_log)
    sys.stdout = tee

    load_dotenv(dotenv_path=project_root / ".env", override=True)
    previous_stream_stdout = os.getenv("LLM_STREAM_STDOUT")
    previous_stream_raw_file = os.getenv("LLM_STREAM_RAW_FILE")
    os.environ["LLM_STREAM_STDOUT"] = "0"
    setup_logging_from_config()

    print("=" * 60)
    print("正文静态知识抽取")
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

    schema_validate, schema_retry_max, schema_retry_suffix = schema_retry_config()
    if schema_validate:
        print(f"Schema校验已开启: retry_max={schema_retry_max}", flush=True)

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_dir = get_doc_dir(doc_id, knowledge_dir)
    raw_file = doc_dir / f"domain_static_prompt_raw_{doc_id}_{run_ts}.jsonl"

    llm_client = LLMRetryClient(
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_base_url,
        model=settings.llm.openai_model,
        max_retries=settings.llm.openai_max_retries,
        timeout=settings.llm.openai_timeout,
    )

    merged_payload = {
        "schema_version": "1.0",
        "doc_id": doc_id,
        "source": {"source_type": "domain_static"},
        "entities": [],
        "relations": [],
        "candidates": {"entities": [], "relations": []},
        "warnings": [],
    }
    warnings_seen = set()
    for idx, chunk in enumerate(chunks, 1):
        print(f"分块 {idx}/{len(chunks)} | 字符数 {len(chunk)}", flush=True)
        base_prompt = get_prompt(chunk, {"doc_id": doc_id})
        os.environ["LLM_STREAM_RAW_FILE"] = str(raw_file)
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
            ok, reason = validate_payload("static", chunk_payload)
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
        _merge_entities(merged_payload["entities"], chunk_payload.get("entities") or [])
        _merge_relations(merged_payload["relations"], chunk_payload.get("relations") or [])
        _merge_candidates(
            merged_payload.get("candidates", {}), chunk_payload.get("candidates") or {}
        )
        for warning in chunk_payload.get("warnings") or []:
            if isinstance(warning, str):
                warnings_seen.add(warning)

    merged_payload["warnings"] = sorted(warnings_seen)
    payload = merged_payload
    section_index = build_section_index(content, doc_id)
    unmatched = 0
    unmatched += annotate_items(payload.get("entities") or [], section_index, evidence_key=None, name_key="name")
    unmatched += annotate_items(payload.get("relations") or [], section_index, evidence_key="evidence")
    candidates = payload.get("candidates") or {}
    if isinstance(candidates, dict):
        unmatched += annotate_items(
            candidates.get("entities") or [], section_index, evidence_key=None, name_key="name"
        )
        unmatched += annotate_items(
            candidates.get("relations") or [], section_index, evidence_key="evidence"
        )
    if unmatched:
        warnings = payload.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
            payload["warnings"] = warnings
        warnings.append(f"source_locate_unmatched:{unmatched}")

    section_id = f"{doc_id}_doc"
    entities = _normalize_entities(payload, doc_id, section_id)
    entity_type_map = {entity.name: entity.type for entity in entities}
    relations = _normalize_relations(payload, doc_id, section_id, entity_type_map)

    result_file = doc_dir / f"domain_static_prompt_results_{doc_id}_{run_ts}.json"
    result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {result_file}")

    cypher_file = doc_dir / f"domain_static_prompt_graph_{doc_id}_{run_ts}.cypher"
    cypher_file.write_text(_build_entity_relation_cypher(doc_id, entities, relations), encoding="utf-8")
    print(f"Cypher已保存: {cypher_file}")

    if _should_write_neo4j():
        try:
            await _apply_cypher(cypher_file, settings)
            print("Neo4j写入完成")
        except Exception as exc:
            print(f"Neo4j写入失败: {exc}")

    _restore_env("LLM_STREAM_STDOUT", previous_stream_stdout)
    _restore_env("LLM_STREAM_RAW_FILE", previous_stream_raw_file)
    await llm_client.close()
    _finalize_log(tee, log_file)


if __name__ == "__main__":
    asyncio.run(run_domain_static())
