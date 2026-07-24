from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


class TeeLogger:
    """同时输出到控制台和日志文件，并为每行增加统一前缀。"""

    def __init__(
        self,
        log_file: Path,
        name: str,
        level: str = "INFO",
        console_suppress_patterns: Optional[Iterable[str]] = None,
        append: bool = False,
    ) -> None:
        self.terminal = sys.stdout
        self.log = log_file.open("a" if append else "w", encoding="utf-8")
        self.name = name
        self.level = level
        self._buffer = ""
        self._prefix_re = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2} \| [A-Z]+ \| .+ \| "
        )
        self._console_suppress = self._build_console_filters(console_suppress_patterns)
        self._console_json_mode = os.getenv("TEE_CONSOLE_JSON_MODE", "message").strip().lower()

    def _build_console_filters(self, patterns: Optional[Iterable[str]]) -> List[re.Pattern]:
        if patterns is None:
            raw = os.getenv("TEE_CONSOLE_SUPPRESS", "") or os.getenv("T_ONSOL_SUPPRSS", "")
            patterns = [item.strip() for item in raw.split(",") if item.strip()]
        compiled: List[re.Pattern] = []
        for pattern in patterns or []:
            try:
                compiled.append(re.compile(pattern))
            except re.error:
                continue
        return compiled

    def _should_suppress_console(self, payload: str) -> bool:
        if not self._console_suppress:
            return False
        return any(regex.search(payload) for regex in self._console_suppress)

    def _prefix(self) -> str:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        return f"{ts} | {self.level} | {self.name} | "

    def _format_console_payload(self, raw_line: str, payload: str) -> str:
        if self._console_json_mode == "full":
            return payload
        stripped = raw_line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                return payload
            message = data.get("message")
            if isinstance(message, str) and message:
                return self._prefix() + message + "\n"
        return payload

    def write(self, message: str) -> None:
        if not message:
            return
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if not line:
                payload = "\n"
                console_payload = payload
            elif self._prefix_re.match(line):
                payload = line + "\n"
                console_payload = payload
            else:
                payload = self._prefix() + line + "\n"
                console_payload = self._format_console_payload(line, payload)
            if not self._should_suppress_console(console_payload):
                self.terminal.write(console_payload)
            self.log.write(payload)
            self.log.flush()

    def flush(self) -> None:
        self.terminal.flush()
        self.log.flush()

    def close(self) -> None:
        if self._buffer:
            if self._prefix_re.match(self._buffer):
                payload = self._buffer
                console_payload = payload
            else:
                payload = self._prefix() + self._buffer
                console_payload = self._format_console_payload(self._buffer, payload)
            if not self._should_suppress_console(console_payload):
                self.terminal.write(console_payload)
            self.log.write(payload)
            self._buffer = ""
        self.log.close()


def resolve_log_file(default_path: Path) -> Tuple[Path, bool]:
    override = os.getenv("PIPELINE_DOC_LOG", "") or os.getenv("PIPELNE_DOC_LOG", "")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, True
    return default_path, False
