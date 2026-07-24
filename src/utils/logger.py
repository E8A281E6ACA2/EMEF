"""
日志工具模块
提供结构化日志记录功能
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.config.settings import get_settings


class JSONFormatter(logging.Formatter):
    """JSON格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            log_entry.update(extra_fields)
        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """文本格式化器"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


class StructuredLogger:
    """结构化日志器"""

    def __init__(self, name: str, extra_fields: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.extra_fields = extra_fields or {}
        self._logger = logging.getLogger(name)

    def _merge_fields(self, **kwargs: Any) -> Dict[str, Any]:
        payload = dict(self.extra_fields)
        payload.update(kwargs)
        return payload

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.debug(message, extra={"extra_fields": self._merge_fields(**kwargs)})

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, extra={"extra_fields": self._merge_fields(**kwargs)})

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, extra={"extra_fields": self._merge_fields(**kwargs)})

    def error(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        payload = self._merge_fields(**kwargs)
        if error:
            payload["error_type"] = type(error).__name__
            payload["error_message"] = str(error)
        self._logger.error(message, exc_info=error if error else None, extra={"extra_fields": payload})

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        payload = self._merge_fields(**kwargs)
        if error:
            payload["error_type"] = type(error).__name__
            payload["error_message"] = str(error)
        self._logger.critical(message, exc_info=error if error else None, extra={"extra_fields": payload})

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        payload = dict(self.extra_fields)
        payload.update(kwargs)
        return StructuredLogger(self.name, payload)


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    file_path: Optional[str] = None,
    max_file_size: str = "0M",
    backup_count: int = 5,
) -> None:
    level_name = level.upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level_name, logging.INFO))
    root_logger.handlers.clear()

    if format_type.lower() == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if file_path:
        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)
        size_bytes = _parse_size(max_file_size)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=file_path,
            maxBytes=size_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def setup_logging_from_config(
    settings: Optional[object] = None,
    file_path: Optional[str] = None,
    max_file_size: Optional[str] = None,
    backup_count: Optional[int] = None,
) -> None:
    settings_obj = settings if settings is not None else get_settings()
    log_level = getattr(settings_obj, "log_level", "INFO")
    log_format = getattr(settings_obj, "log_format", "json")
    file_path = file_path or os.getenv("LOG_FILE", "") or os.getenv("LOG_FIL", "")
    max_file_size = max_file_size or os.getenv("LOG_MAX_SIZE", "") or os.getenv("LOG_MX_SIZ", "0M")
    if backup_count is None:
        raw = os.getenv("LOG_BACKUP_COUNT", "") or os.getenv("LOG_KUP_OUNT", "5")
        try:
            backup_count = int(raw)
        except ValueError:
            backup_count = 5
    setup_logging(
        level=log_level,
        format_type=log_format,
        file_path=file_path if file_path else None,
        max_file_size=max_file_size,
        backup_count=backup_count,
    )


def _parse_size(size_str: str) -> int:
    text = size_str.strip().upper()
    if not text:
        return 0
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1024
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1024 * 1024
        text = text[:-1]
    elif text.endswith("G"):
        multiplier = 1024 * 1024 * 1024
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def get_logger(name: str, **extra_fields: Any) -> StructuredLogger:
    return StructuredLogger(name, extra_fields)
