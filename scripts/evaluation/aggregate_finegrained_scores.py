#!/usr/bin/env python3
"""
Aggregate fine-grained score JSON files into markdown/CSV tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate fine-grained scores")
    parser.add_argument("--input-dir", required=True, help="Directory containing fine-grained JSON files")
    parser.add_argument("--output-md", required=True, help="Output markdown file")
    parser.add_argument("--output-csv", required=True, help="Output CSV file")
    parser.add_argument("--order", default=None, help="Comma-separated model order")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(input_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No JSON files found in {input_dir}")

    rows = []
    for path in files:
        data = _load_json(path)
        rows.append(data)

    if args.order:
        order = [s.strip() for s in args.order.split(",") if s.strip()]
        rows.sort(key=lambda r: order.index(r["model"]) if r.get("model") in order else 9999)
    else:
        rows.sort(key=lambda r: r.get("model", ""))

    # Build markdown tables (P/R/F1 only)
    md_lines: List[str] = []
    md_lines.append("**细粒度 P/R/F1（仅保留 PRF1）**")
    md_lines.append("| 模型 | 实体P | 实体R | 实体F1 | 事件P | 事件R | 事件F1 | 时序P | 时序R | 时序F1 | 事理P | 事理R | 事理F1 |")
    md_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        slot = r["slot_f1"]
        md_lines.append(
            f"| {r['model']} | {_fmt(slot['entity']['precision'])} | {_fmt(slot['entity']['recall'])} | {_fmt(slot['entity']['f1'])} | "
            f"{_fmt(slot['event']['precision'])} | {_fmt(slot['event']['recall'])} | {_fmt(slot['event']['f1'])} | "
            f"{_fmt(slot['temporal']['precision'])} | {_fmt(slot['temporal']['recall'])} | {_fmt(slot['temporal']['f1'])} | "
            f"{_fmt(slot['causal']['precision'])} | {_fmt(slot['causal']['recall'])} | {_fmt(slot['causal']['f1'])} |"
        )

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # CSV output (P/R/F1 only)
    csv_header = [
        "model",
        "entity_p",
        "entity_r",
        "entity_f1",
        "event_p",
        "event_r",
        "event_f1",
        "temporal_p",
        "temporal_r",
        "temporal_f1",
        "causal_p",
        "causal_r",
        "causal_f1",
    ]
    csv_lines = [",".join(csv_header)]
    for r in rows:
        slot = r["slot_f1"]
        csv_lines.append(
            ",".join(
                [
                    r["model"],
                    f"{slot['entity']['precision']:.4f}",
                    f"{slot['entity']['recall']:.4f}",
                    f"{slot['entity']['f1']:.4f}",
                    f"{slot['event']['precision']:.4f}",
                    f"{slot['event']['recall']:.4f}",
                    f"{slot['event']['f1']:.4f}",
                    f"{slot['temporal']['precision']:.4f}",
                    f"{slot['temporal']['recall']:.4f}",
                    f"{slot['temporal']['f1']:.4f}",
                    f"{slot['causal']['precision']:.4f}",
                    f"{slot['causal']['recall']:.4f}",
                    f"{slot['causal']['f1']:.4f}",
                ]
            )
        )

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    print(f"Markdown table written to {output_md}")
    print(f"CSV table written to {output_csv}")


if __name__ == "__main__":
    main()
