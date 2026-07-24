#!/usr/bin/env python3
"""
Prepare baseline input JSONL from MAKER gold evaluation set.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _collect_gold_ids(gold_dir: Path) -> List[str]:
    ids: List[str] = []
    for path in sorted(gold_dir.iterdir()):
        if path.is_dir() and path.name.startswith("wheat_gold_"):
            ids.append(path.name)
    return ids


def _load_meta(doc_dir: Path) -> dict:
    meta_path = doc_dir / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare baseline input JSONL from MAKER gold dataset")
    parser.add_argument("--gold-dir", default="results/evaluation")
    parser.add_argument("--output", default="results/baseline_inputs/wheat_gold.jsonl")
    parser.add_argument("--lang", default="zh-CN")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    gold_dir = PROJECT_ROOT / args.gold_dir
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc_ids = _collect_gold_ids(gold_dir)
    if args.limit:
        doc_ids = doc_ids[: args.limit]

    with output_path.open("w", encoding="utf-8") as f:
        for doc_id in doc_ids:
            doc_dir = gold_dir / doc_id
            meta = _load_meta(doc_dir)
            paragraph = meta.get("paragraph", "")
            record = {
                "id": doc_id,
                "text": paragraph,
                "metadata": {
                    "lang": args.lang,
                    "source_pdf": meta.get("source_pdf"),
                    "source_pdf_path": meta.get("source_pdf_path"),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(doc_ids)} records to {output_path}")


if __name__ == "__main__":
    main()
