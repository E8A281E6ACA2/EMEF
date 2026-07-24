"""Language-aware prompt router for four-stage extractors."""

from __future__ import annotations

import importlib
import os
import re
from typing import Any, Dict, Optional


_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
_EN_TOKEN_RE = re.compile(r"[A-Za-z]{2,}")
_SUPPORTED_LANGS = {"cn", "en"}


def _normalize_lang(raw: Optional[str]) -> Optional[str]:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    aliases = {
        "zh": "cn",
        "zh-cn": "cn",
        "zh_hans": "cn",
        "chinese": "cn",
        "cn": "cn",
        "en": "en",
        "en-us": "en",
        "english": "en",
    }
    value = aliases.get(value, value)
    return value if value in _SUPPORTED_LANGS else None


def _detect_text_lang(text: str) -> Optional[str]:
    source = text or ""
    zh_count = len(_ZH_RE.findall(source))
    en_token_count = len(_EN_TOKEN_RE.findall(source))
    if en_token_count >= 6 and zh_count == 0:
        return "en"
    if zh_count >= 12 and zh_count >= en_token_count:
        return "cn"
    if en_token_count >= 12 and zh_count <= 6:
        return "en"
    if en_token_count >= zh_count * 2 and en_token_count >= 12:
        return "en"
    return None


def resolve_prompt_lang(
    input_text: str,
    context_info: Optional[Dict[str, Any]] = None,
    default_lang: str = "cn",
) -> str:
    raw_lang = (
        os.getenv("EXTRACTION_PROMPT_LANG")
        or os.getenv("PROMPT_LANG")
        or os.getenv("LLM_PROMPT_LANG")
        or ""
    ).strip()
    normalized = _normalize_lang(raw_lang)
    if normalized:
        return normalized

    if isinstance(context_info, dict):
        for key in ("language", "lang", "doc_language"):
            normalized = _normalize_lang(context_info.get(key))
            if normalized:
                return normalized

    auto_lang = _detect_text_lang(input_text)
    if auto_lang:
        return auto_lang

    env_default = _normalize_lang(os.getenv("EXTRACTION_PROMPT_DEFAULT_LANG"))
    return env_default or _normalize_lang(default_lang) or "cn"


def _load_prompt_getter(lang: str, module_name: str):
    module_path = f"src.core.extraction.four_stage.resources.prompts.{lang}.extractors.{module_name}"
    module = importlib.import_module(module_path)
    fn = getattr(module, "get_prompt", None)
    if fn is None:
        raise AttributeError(f"{module_path} missing get_prompt")
    return fn


def _load_legacy_getter(module_name: str):
    module_path = f"src.core.extraction.four_stage.resources.prompts.extractors.{module_name}"
    module = importlib.import_module(module_path)
    fn = getattr(module, "get_prompt", None)
    if fn is None:
        raise AttributeError(f"{module_path} missing get_prompt")
    return fn


def get_extractor_prompt(
    module_name: str,
    input_text: str,
    context_info: Optional[Dict[str, Any]] = None,
) -> str:
    lang = resolve_prompt_lang(input_text, context_info)
    tried = []
    for candidate in (lang, "cn"):
        if candidate in tried:
            continue
        tried.append(candidate)
        try:
            getter = _load_prompt_getter(candidate, module_name)
            return getter(input_text, context_info)
        except Exception:
            continue
    return _load_legacy_getter(module_name)(input_text, context_info)


def get_domain_static_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("domain_static_prompt", input_text, context_info)


def get_domain_event_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("domain_event_prompt", input_text, context_info)


def get_domain_temporal_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("domain_temporal_prompt", input_text, context_info)


def get_domain_causal_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("domain_causal_prompt", input_text, context_info)


def get_section_summary_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("section_summary_prompt", input_text, context_info)


def get_table_data_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("table_data_prompt", input_text, context_info)


def get_table_context_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("table_context_prompt", input_text, context_info)


def get_table_context_fields_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("table_context_fields_prompt", input_text, context_info)


def get_metadata_prompt(input_text: str, context_info: Optional[Dict[str, Any]] = None) -> str:
    return get_extractor_prompt("metadata_prompt", input_text, context_info)
