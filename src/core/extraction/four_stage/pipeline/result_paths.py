"""
四阶段抽取结果路径工具。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


def _find_project_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "src").is_dir():
            return parent
    raise RuntimeError("无法定位项目根目录（未找到src目录）")


def get_results_root() -> Path:
    override = os.getenv("RESULTS_ROOT")
    if override:
        return Path(override)
    project_root = _find_project_root(Path(__file__).resolve())
    return project_root / "results" / "extraction" / "four_stage"


def get_results_dirs() -> Tuple[Path, Path, Path]:
    root = get_results_root()
    knowledge = Path(os.getenv("RESULTS_KNOWLEDGE_DIR", root / "knowledge"))
    log = Path(os.getenv("RESULTS_LOG_DIR", root / "log"))
    knowledge.mkdir(parents=True, exist_ok=True)
    log.mkdir(parents=True, exist_ok=True)
    return root, knowledge, log


def safe_doc_id(doc_id: str) -> str:
    return doc_id.replace(os.sep, "_").replace(" ", "_")


def get_doc_dir(doc_id: str, knowledge_dir: Path) -> Path:
    doc_dir = knowledge_dir / safe_doc_id(doc_id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir
