"""
LLM 重试封装（实验阶段使用）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from typing import Any, Callable, Dict, List, Optional

from src.core.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


FAIL_FAST_SENTINEL = "LLM_FAIL_FAST"


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


def _env_bool(names: List[str], default: bool) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _env_float(names: List[str], default: float) -> float:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return default


def _env_list_int(name: str, default: List[int]) -> List[int]:
    raw = os.getenv(name)
    if not raw:
        return default
    values: List[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values or default


def _env_list_str(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    values: List[str] = []
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        values.append(item)
    return values or default


class LLMRetryClient(LLMClient):
    """在基础 LLMClient 上增加重试与退避策略。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None,
        retry_max: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
        retry_jitter: Optional[float] = None,
        retry_statuses: Optional[List[int]] = None,
        fail_fast: Optional[bool] = None,
        fail_fast_statuses: Optional[List[int]] = None,
        fail_fast_keywords: Optional[List[str]] = None,
    ) -> None:
        http_retries = max_retries if max_retries is not None else _env_int(
            ["LLM_HTTP_RETRIES", "LLM_HTTP_RETRY"], 5
        )
        timeout_val = timeout if timeout is not None else _env_float(
            ["LLM_HTTP_TIMEOUT", "LLM_TIMEOUT"], 20.0
        )
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_retries=http_retries,
            timeout=timeout_val,
        )
        self.retry_max = retry_max if retry_max is not None else _env_int(["LLM_RETRY_MAX"], 5)
        self.retry_base_delay = retry_base_delay if retry_base_delay is not None else _env_float(
            ["LLM_RETRY_BASE_DELAY"], 2.0
        )
        self.retry_max_delay = retry_max_delay if retry_max_delay is not None else _env_float(
            ["LLM_RETRY_MAX_DELAY"], 0.0
        )
        self.retry_jitter = retry_jitter if retry_jitter is not None else _env_float(
            ["LLM_RETRY_JITTER"], 0.3
        )
        self.retry_statuses = set(
            retry_statuses
            if retry_statuses is not None
            else _env_list_int("LLM_RETRY_STATUSES", [408, 429, 500, 502, 503, 504])
        )
        self.fail_fast_enabled = fail_fast if fail_fast is not None else _env_bool(
            ["LLM_FAIL_FAST", "PIPELINE_LLM_FAIL_FAST"], True
        )
        self.fail_fast_statuses = set(
            fail_fast_statuses
            if fail_fast_statuses is not None
            else _env_list_int("LLM_FAIL_FAST_STATUSES", [401, 403, 404, 500, 502, 503, 504])
        )
        self.fail_fast_keywords = [
            keyword
            for keyword in (
                fail_fast_keywords
                if fail_fast_keywords is not None
                else _env_list_str(
                    "LLM_FAIL_FAST_KEYWORDS",
                    [
                        "gateway.upstream_error",
                        "service unavailable",
                        "bad gateway",
                        "gateway time-out",
                        "unauthorized",
                        "invalid api key",
                        "permission denied",
                        "access denied",
                        "model not found",
                        "not found",
                        "connection refused",
                    ],
                )
            )
            if keyword
        ]

    @staticmethod
    def _truncate_text(text: str, limit: int = 500) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _format_error_detail(self, exc: Exception) -> str:
        parts: List[str] = []
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code is not None:
            parts.append(f"status={status_code}")
        body = getattr(exc, "body", None)
        if body is not None:
            try:
                if isinstance(body, (dict, list)):
                    body_text = json.dumps(body, ensure_ascii=True)
                else:
                    body_text = str(body)
                body_text = self._truncate_text(body_text)
                parts.append(f"body={body_text}")
            except Exception:
                pass
        if response is not None:
            try:
                text = getattr(response, "text", None)
                if text:
                    parts.append(f"response={self._truncate_text(str(text))}")
            except Exception:
                pass
        return "; ".join(parts)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        return await self._call_with_retry(
            "LLM调用",
            lambda: super(LLMRetryClient, self).generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                **kwargs,
            ),
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, Any]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        **kwargs: Any,
    ) -> str:
        has_chunks: Dict[str, bool] = {"value": False}

        def _wrapped_chunk(chunk: str) -> None:
            if chunk:
                has_chunks["value"] = True
            if on_chunk:
                on_chunk(chunk)

        return await self._call_with_retry(
            "LLM流式调用",
            lambda: super(LLMRetryClient, self).generate_stream(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                on_chunk=_wrapped_chunk,
                **kwargs,
            ),
            has_chunks=has_chunks,
        )

    async def _call_with_retry(
        self,
        label: str,
        call: Callable[[], Any],
        has_chunks: Optional[Dict[str, bool]] = None,
    ) -> Any:
        attempts = max(1, int(self.retry_max))
        for attempt in range(1, attempts + 1):
            try:
                return await call()
            except Exception as exc:
                fail_fast = self.fail_fast_enabled and self._is_fail_fast_error(exc)
                retryable = self._is_retryable_error(exc)
                if fail_fast and not retryable:
                    self._raise_fail_fast(label, exc)
                if attempt >= attempts or not retryable:
                    if fail_fast:
                        self._raise_fail_fast(label, exc)
                    detail = self._format_error_detail(exc)
                    if detail:
                        logger.error(
                            "%s最终失败 (%s/%s, retryable=%s): %s: %s | %s",
                            label,
                            attempt,
                            attempts,
                            retryable,
                            type(exc).__name__,
                            str(exc),
                            detail,
                        )
                    else:
                        logger.error(
                            "%s最终失败 (%s/%s, retryable=%s): %s: %s",
                            label,
                            attempt,
                            attempts,
                            retryable,
                            type(exc).__name__,
                            str(exc),
                        )
                    raise
                base_delay = self.retry_base_delay * (2 ** (attempt - 1))
                delay = base_delay
                if self.retry_max_delay and self.retry_max_delay > 0:
                    delay = min(base_delay, self.retry_max_delay)
                if self.retry_jitter > 0:
                    jitter = 1.0 + random.uniform(-self.retry_jitter, self.retry_jitter)
                    delay = max(0.0, delay * jitter)
                suffix = ""
                if has_chunks and has_chunks.get("value"):
                    suffix = "（已产生部分流式输出）"
                logger.warning(
                    "%s失败%s，准备重试 %s/%s，等待 %.2fs: %s",
                    label,
                    suffix,
                    attempt,
                    attempts,
                    delay,
                    str(exc),
                )
                await asyncio.sleep(delay)
        return await call()

    def _raise_fail_fast(self, label: str, exc: Exception) -> None:
        detail = self._format_error_detail(exc)
        message = (
            f"{FAIL_FAST_SENTINEL}: {label}失败，LLM服务不可用或配置异常。"
            f"请检查base_url/model/key或稍后重试。错误: {exc}"
        )
        if detail:
            message = f"{message} | 详情: {detail}"
        logger.error(message)
        raise SystemExit(message)

    def _is_fail_fast_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code in self.fail_fast_statuses:
            return True
        message = str(exc).lower()
        return any(keyword in message for keyword in self.fail_fast_keywords)

    def _is_retryable_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code in self.retry_statuses:
            return True
        message = str(exc).lower()
        keywords = [
            "timeout",
            "timed out",
            "connection reset",
            "connection aborted",
            "connection refused",
            "peer closed connection",
            "incomplete chunked read",
            "temporarily unavailable",
            "rate limit",
            "too many requests",
            "gateway time-out",
            "bad gateway",
            "service unavailable",
            "internal server error",
        ]
        return any(key in message for key in keywords)
