from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.core.extraction.smart_hierarchy_parser import SmartHierarchyParser

from models import Section


@dataclass
class HierarchyMeta:
    strategy: str
    total_sections: int
    max_level: int
    has_numbering: bool


def build_section_tree(
    markdown: str, doc_id: str
) -> Tuple[List[Section], List[Tuple[str, str]], HierarchyMeta, Dict[str, str]]:
    parser = SmartHierarchyParser(mode="auto")
    parsed_sections, meta = parser.parse(markdown)

    root_id = f"{doc_id}_root"
    root = Section(
        id=root_id,
        doc_id=doc_id,
        parent_id=None,
        level=0,
        title=doc_id,
        content="",
        summary=None,
        token_count=0,
    )

    sections: List[Section] = [root]
    edges: List[Tuple[str, str]] = []
    number_to_id: Dict[str, str] = {}
    section_numbers: Dict[str, str] = {}
    stack: List[Tuple[int, str]] = [(0, root_id)]

    for idx, sec in enumerate(parsed_sections):
        level = max(1, sec.level)

        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else root_id

        if sec.number:
            section_id = f"{doc_id}_s{sec.number.replace('.', '_')}"
            number_to_id[sec.number] = section_id
            section_numbers[section_id] = sec.number
            parent_number = ".".join(sec.number.split(".")[:-1])
            if parent_number and parent_number in number_to_id:
                parent_id = number_to_id[parent_number]
        else:
            section_id = f"{doc_id}_s{idx}"

        stack.append((level, section_id))

        content = sec.content.strip()
        sections.append(
            Section(
                id=section_id,
                doc_id=doc_id,
                parent_id=parent_id,
                level=level,
                title=sec.title.strip(),
                content=content,
                summary=None,
                token_count=max(1, len(content) // 4),
            )
        )
        edges.append((parent_id, section_id))

    hierarchy_meta = HierarchyMeta(
        strategy=str(meta.get("strategy", "auto")),
        total_sections=int(meta.get("total_sections", len(parsed_sections))),
        max_level=int(meta.get("max_level", 0)),
        has_numbering=bool(meta.get("has_numbering", False)),
    )

    return sections, edges, hierarchy_meta, section_numbers
