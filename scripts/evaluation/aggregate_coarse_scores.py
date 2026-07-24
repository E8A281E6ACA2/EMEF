#!/usr/bin/env python3
"""
Aggregate coarse-grained P/R/F1 scores (static/event/temporal/causal) into tables.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple


def _load_scores(path: Path) -> Dict[str, Dict[str, float]]:
    scores: Dict[str, Dict[str, float]] = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row.get("type")
            if not t:
                continue
            scores[t] = {
                "precision": float(row.get("precision", 0) or 0),
                "recall": float(row.get("recall", 0) or 0),
                "f1": float(row.get("f1", 0) or 0),
            }
    return scores


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate coarse-grained scores into markdown/CSV tables")
    parser.add_argument("--output-md", required=True, help="Output markdown file")
    parser.add_argument("--output-csv", required=True, help="Output CSV file")
    parser.add_argument("--spec", action="append", help="Model=path.csv (repeatable)")
    args = parser.parse_args()

    specs: List[Tuple[str, Path]] = []
    if args.spec:
        for item in args.spec:
            if "=" not in item:
                raise SystemExit(f"Invalid --spec {item}, expected Model=path.csv")
            name, path = item.split("=", 1)
            specs.append((name.strip(), Path(path.strip())))
    else:
        # Example paths; pass --spec Model=path.csv to select actual inputs.
        specs = [
            ("Primary method", Path("results/evaluation_scores/primary.csv")),
            ("AutoSchemaKG", Path("results/baseline_scores/autoschemakg.csv")),
            ("OneKE", Path("results/baseline_scores/oneke.csv")),
            ("KG-Gen", Path("results/baseline_scores/kggen.csv")),
        ]

    rows: List[Tuple[str, Dict[str, Dict[str, float]]]] = []
    for name, path in specs:
        if not path.exists():
            raise SystemExit(f"Score file not found: {path}")
        rows.append((name, _load_scores(path)))

    md_lines: List[str] = []
    md_lines.append("**粗粒度 P/R/F1（静态/事件/时序/事理）**")
    md_lines.append("| 模型 | 静态P | 静态R | 静态F1 | 事件P | 事件R | 事件F1 | 时序P | 时序R | 时序F1 | 事理P | 事理R | 事理F1 |")
    md_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, scores in rows:
        s = scores.get("static", {})
        e = scores.get("event", {})
        t = scores.get("temporal", {})
        c = scores.get("causal", {})
        md_lines.append(
            f"| {name} | {_fmt(s.get('precision',0))} | {_fmt(s.get('recall',0))} | {_fmt(s.get('f1',0))} | "
            f"{_fmt(e.get('precision',0))} | {_fmt(e.get('recall',0))} | {_fmt(e.get('f1',0))} | "
            f"{_fmt(t.get('precision',0))} | {_fmt(t.get('recall',0))} | {_fmt(t.get('f1',0))} | "
            f"{_fmt(c.get('precision',0))} | {_fmt(c.get('recall',0))} | {_fmt(c.get('f1',0))} |"
        )

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    csv_header = [
        "model",
        "static_p",
        "static_r",
        "static_f1",
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
    for name, scores in rows:
        s = scores.get("static", {})
        e = scores.get("event", {})
        t = scores.get("temporal", {})
        c = scores.get("causal", {})
        csv_lines.append(
            ",".join(
                [
                    name,
                    f"{s.get('precision',0):.4f}",
                    f"{s.get('recall',0):.4f}",
                    f"{s.get('f1',0):.4f}",
                    f"{e.get('precision',0):.4f}",
                    f"{e.get('recall',0):.4f}",
                    f"{e.get('f1',0):.4f}",
                    f"{t.get('precision',0):.4f}",
                    f"{t.get('recall',0):.4f}",
                    f"{t.get('f1',0):.4f}",
                    f"{c.get('precision',0):.4f}",
                    f"{c.get('recall',0):.4f}",
                    f"{c.get('f1',0):.4f}",
                ]
            )
        )

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_csv.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    print(f"Markdown table written to {out_md}")
    print(f"CSV table written to {out_csv}")


if __name__ == "__main__":
    main()
