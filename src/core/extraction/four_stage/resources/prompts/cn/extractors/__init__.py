"""Chinese prompt pack used by the four-stage review artifact."""

from .domain_static_prompt import get_prompt as domain_static_prompt
from .domain_temporal_prompt import get_prompt as domain_temporal_prompt
from .domain_event_prompt import get_prompt as domain_event_prompt
from .domain_causal_prompt import get_prompt as domain_causal_prompt

__all__ = [
    "domain_static_prompt",
    "domain_temporal_prompt",
    "domain_event_prompt",
    "domain_causal_prompt",
]
