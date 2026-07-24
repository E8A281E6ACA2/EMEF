from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0


_doc_usage = UsageStats()
_total_usage = UsageStats()


def reset_doc_usage() -> None:
    global _doc_usage
    _doc_usage = UsageStats()


def record_usage(prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    prompt = max(0, int(prompt_tokens or 0))
    completion = max(0, int(completion_tokens or 0))
    total = int(total_tokens or 0)
    if total <= 0:
        total = prompt + completion
    if total <= 0 and prompt <= 0 and completion <= 0:
        return
    global _doc_usage, _total_usage
    _doc_usage.prompt_tokens += prompt
    _doc_usage.completion_tokens += completion
    _doc_usage.total_tokens += max(total, prompt + completion)
    _doc_usage.requests += 1
    _total_usage.prompt_tokens += prompt
    _total_usage.completion_tokens += completion
    _total_usage.total_tokens += max(total, prompt + completion)
    _total_usage.requests += 1


def snapshot_usage() -> tuple[UsageStats, UsageStats]:
    return _doc_usage, _total_usage
