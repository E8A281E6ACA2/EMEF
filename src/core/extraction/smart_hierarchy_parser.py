"""
智能层级解析器

自动识别文档的层级结构，支持：
1. Markdown标题（#、##、###）
2. 编号标题（1、1.1、1.1.1）
3. 中文序号标题（一、（一））
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    """解析后的章节"""

    title: str
    content: str
    level: int
    number: Optional[str] = None
    start_line: int = 0
    end_line: int = 0


class SmartHierarchyParser:
    """智能层级解析器"""

    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode
        self._numeric_pattern = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
        self._chinese_pattern = re.compile(
            r"^([一二三四五六七八九十]+[、）]|[（(][一二三四五六七八九十]+[）)])\s*(.+)$"
        )

    def parse(self, markdown: str) -> Tuple[List[ParsedSection], Dict[str, object]]:
        if self.mode == "auto":
            strategy = self._detect_best_strategy(markdown)
            logger.info("自动检测到最佳策略: %s", strategy)
        else:
            strategy = self.mode

        if strategy == "markdown":
            sections = self._parse_markdown_standard(markdown)
        elif strategy == "numbering":
            sections = self._parse_by_numbering(markdown)
        elif strategy == "mixed":
            sections = self._parse_mixed(markdown)
        else:
            sections = self._parse_markdown_standard(markdown)

        metadata = {
            "strategy": strategy,
            "total_sections": len(sections),
            "max_level": max((s.level for s in sections), default=0),
            "has_numbering": any(s.number for s in sections),
        }
        logger.info("解析完成: %s", metadata)
        return sections, metadata

    def _detect_best_strategy(self, markdown: str) -> str:
        lines = markdown.splitlines()
        markdown_headers = 0
        numbered_headers = 0
        has_numeric_title = False

        for line in lines:
            text = line.strip()
            if not text:
                continue
            if text.startswith("#"):
                match = re.match(r"^(#{1,6})\s+(.+)$", text)
                if match:
                    markdown_headers += 1
                    title = match.group(2)
                    if self._numeric_pattern.match(title):
                        has_numeric_title = True
            else:
                if self._numeric_pattern.match(text) or self._chinese_pattern.match(text):
                    numbered_headers += 1

        if markdown_headers > 0 and has_numeric_title:
            return "mixed"
        if markdown_headers > 0:
            return "markdown"
        if numbered_headers > 0:
            return "numbering"
        return "markdown"

    def _parse_markdown_standard(self, markdown: str) -> List[ParsedSection]:
        lines = markdown.splitlines()
        sections: List[ParsedSection] = []
        current_title = ""
        current_level = 1
        current_number: Optional[str] = None
        start_line = 0
        buffer: List[str] = []

        def _flush(end_idx: int) -> None:
            if not current_title and not buffer:
                return
            content = "\n".join(buffer).strip()
            title = current_title or "正文"
            sections.append(
                ParsedSection(
                    title=title,
                    content=content,
                    level=current_level,
                    number=current_number,
                    start_line=start_line,
                    end_line=end_idx,
                )
            )

        for idx, line in enumerate(lines):
            match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
            if match:
                _flush(idx - 1)
                buffer = []
                start_line = idx
                current_level = len(match.group(1))
                title = match.group(2).strip()
                number, title = self._split_number_title(title)
                current_title = title
                current_number = number
                continue
            buffer.append(line)

        _flush(len(lines) - 1)
        return sections

    def _parse_by_numbering(self, markdown: str) -> List[ParsedSection]:
        lines = markdown.splitlines()
        sections: List[ParsedSection] = []
        current_title = ""
        current_level = 1
        current_number: Optional[str] = None
        start_line = 0
        buffer: List[str] = []

        def _flush(end_idx: int) -> None:
            if not current_title and not buffer:
                return
            content = "\n".join(buffer).strip()
            title = current_title or "正文"
            sections.append(
                ParsedSection(
                    title=title,
                    content=content,
                    level=current_level,
                    number=current_number,
                    start_line=start_line,
                    end_line=end_idx,
                )
            )

        for idx, line in enumerate(lines):
            text = line.strip()
            number, title = self._match_number_title(text)
            if title:
                _flush(idx - 1)
                buffer = []
                start_line = idx
                current_number = number
                current_level = max(1, number.count(".") + 1) if number else 1
                current_title = title
                continue
            buffer.append(line)

        _flush(len(lines) - 1)
        return sections

    def _parse_mixed(self, markdown: str) -> List[ParsedSection]:
        lines = markdown.splitlines()
        sections: List[ParsedSection] = []
        current_title = ""
        current_level = 1
        current_number: Optional[str] = None
        start_line = 0
        buffer: List[str] = []

        def _flush(end_idx: int) -> None:
            if not current_title and not buffer:
                return
            content = "\n".join(buffer).strip()
            title = current_title or "正文"
            sections.append(
                ParsedSection(
                    title=title,
                    content=content,
                    level=current_level,
                    number=current_number,
                    start_line=start_line,
                    end_line=end_idx,
                )
            )

        for idx, line in enumerate(lines):
            text = line.strip()
            match = re.match(r"^(#{1,6})\s+(.+)$", text)
            if match:
                _flush(idx - 1)
                buffer = []
                start_line = idx
                current_level = len(match.group(1))
                title = match.group(2).strip()
                number, title = self._split_number_title(title)
                current_title = title
                current_number = number
                continue
            number, title = self._match_number_title(text)
            if title:
                _flush(idx - 1)
                buffer = []
                start_line = idx
                current_number = number
                current_level = max(1, number.count(".") + 1) if number else 1
                current_title = title
                continue
            buffer.append(line)

        _flush(len(lines) - 1)
        return sections

    def _match_number_title(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        if not text:
            return None, None
        numeric_match = self._numeric_pattern.match(text)
        if numeric_match:
            return numeric_match.group(1), numeric_match.group(2).strip()
        chinese_match = self._chinese_pattern.match(text)
        if chinese_match:
            return None, chinese_match.group(2).strip()
        return None, None

    def _split_number_title(self, text: str) -> Tuple[Optional[str], str]:
        numeric_match = self._numeric_pattern.match(text)
        if numeric_match:
            return numeric_match.group(1), numeric_match.group(2).strip()
        return None, text
