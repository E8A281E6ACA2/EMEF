"""Language-aware prompt access for the four released extraction stages."""

from .i18n_extractors import (
    get_domain_causal_prompt,
    get_domain_event_prompt,
    get_domain_static_prompt,
    get_domain_temporal_prompt,
    resolve_prompt_lang,
)

__all__ = [
    "resolve_prompt_lang",
    "get_domain_static_prompt",
    "get_domain_event_prompt",
    "get_domain_temporal_prompt",
    "get_domain_causal_prompt",
]
