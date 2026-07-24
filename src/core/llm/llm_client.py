"""
LLM客户端封装
支持兼容OpenAI格式的中转地址
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import AsyncOpenAI

from src.config.settings import Settings

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}

def _extract_usage_value(obj: Any, *names: str) -> int:
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _append_stream_chunk(raw_file: Optional[str], chunk: str) -> None:
    if not raw_file or not chunk:
        return
    try:
        path = Path(raw_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "content": chunk,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


class LLMClient:
    """LLM客户端（兼容OpenAI格式）"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._model_checked = False
        self._model_available = False
        self._model_check_error: Optional[Exception] = None
        self._last_usage: Dict[str, int] = {}

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            return

    async def check_model(self, force: bool = False) -> bool:
        if self._model_checked and not force:
            return self._model_available
        self._model_checked = True
        self._model_available = False
        self._model_check_error = None
        try:
            models = await self.client.models.list()
            data = getattr(models, "data", None)
            if data:
                self._model_available = True
                return True
        except Exception:
            pass
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_tokens=1,
            )
            content = self._extract_content(response)
            if content is not None:
                self._model_available = True
                return True
        except Exception as exc:
            self._model_check_error = exc
            return False
        return False

    def get_model_check_error(self) -> Optional[Exception]:
        return self._model_check_error

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, Any]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        **kwargs: Any,
    ) -> str:
        request_params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if response_format:
            request_params["response_format"] = response_format
        if _env_bool("LLM_STREAM_INCLUDE_USAGE", False):
            request_params["stream_options"] = {"include_usage": True}
        request_params.update(kwargs)
        chunks: List[str] = []
        async for part in await self.client.chat.completions.create(**request_params):
            usage = getattr(part, "usage", None)
            if usage is not None:
                self._record_usage(usage)
            choices = getattr(part, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if not content:
                continue
            chunks.append(content)
            if on_chunk:
                on_chunk(content)
        return "".join(chunks)

    def _extract_content(self, response: Any) -> str:
        try:
            choices = getattr(response, "choices", None) or []
            if not choices:
                return ""
            message = getattr(choices[0], "message", None)
            if message is not None:
                return getattr(message, "content", "") or ""
            return getattr(choices[0], "text", "") or ""
        except Exception:
            return ""

    def _record_usage(self, usage: Any) -> None:
        if usage is None:
            return
        prompt_tokens = _extract_usage_value(usage, "prompt_tokens", "prompt")
        completion_tokens = _extract_usage_value(usage, "completion_tokens", "completion")
        total_tokens = _extract_usage_value(usage, "total_tokens", "total")
        self._last_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        try:
            from src.core.llm.usage_tracker import record_usage
        except Exception:
            return
        record_usage(prompt_tokens, completion_tokens, total_tokens)

    def _looks_like_html(self, content: str) -> bool:
        if not content:
            return False
        stripped = content.lstrip().lower()
        return stripped.startswith("<!doctype html") or stripped.startswith("<html")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        if _env_bool("LLM_STREAM", True):
            raw_file = os.getenv("LLM_STREAM_RAW_FILE")
            stream_stdout = _env_bool("LLM_STREAM_STDOUT", True)
            strip_fence = _env_bool("LLM_STREAM_STRIP_FENCE", True)
            buffer: List[str] = []

            def _emit_line(line: str) -> None:
                if strip_fence and line.strip().startswith("```"):
                    return
                if stream_stdout and not raw_file:
                    print(line, end="\n", flush=True)

            def _on_chunk(text: str) -> None:
                if raw_file:
                    _append_stream_chunk(raw_file, text)
                if not stream_stdout or raw_file:
                    return
                if not strip_fence:
                    print(text, end="", flush=True)
                    return
                buffer.append(text)
                joined = "".join(buffer)
                while "\n" in joined:
                    line, rest = joined.split("\n", 1)
                    _emit_line(line)
                    joined = rest
                buffer.clear()
                if joined:
                    buffer.append(joined)

            content = await self.generate_stream(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                on_chunk=_on_chunk,
                **kwargs,
            )
            if buffer and not raw_file:
                _emit_line("".join(buffer))
            return content
        request_params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            request_params["response_format"] = response_format
        request_params.update(kwargs)
        logger.debug("调用LLM: model=%s temp=%s", self.model, temperature)
        response = await self.client.chat.completions.create(**request_params)
        content = self._extract_content(response)
        self._record_usage(getattr(response, "usage", None))
        if self._looks_like_html(content):
            preview = content.strip().replace("\n", " ")[:200]
            logger.error("LLM返回HTML，疑似鉴权失败: %s", preview)
            raise RuntimeError("LLM返回HTML内容，请检查base_url/model/auth配置。")
        if not content or not content.strip():
            logger.warning("LLM返回内容为空")
            return ""
        return content

def create_llm_client(
    settings: Optional[Settings] = None,
    override_model: Optional[str] = None,
) -> LLMClient:
    settings = settings or Settings()
    model = override_model or settings.llm.openai_model
    return LLMClient(
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_base_url,
        model=model,
        max_retries=settings.llm.openai_max_retries,
        timeout=settings.llm.openai_timeout,
    )
