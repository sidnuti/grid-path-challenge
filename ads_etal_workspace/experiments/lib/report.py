"""Tiny markdown/JSON output helpers shared by the experiment scripts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parents[1] / "results"


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    cols = list(df.columns)
    def cell(v):
        if isinstance(v, float):
            return floatfmt.format(v)
        return str(v)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines)


def save(name: str, data: dict, markdown: str, hashes: set[str] | None = None) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    if hashes is not None:
        data["_code_hashes_seen"] = sorted(hashes)
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=2, default=str))
    header = ""
    if hashes is not None:
        header = f"<!-- code hashes: {', '.join(sorted(hashes))}{'  (MIXED)' if len(hashes) > 1 else ''} -->\n"
    (RESULTS / f"{name}.md").write_text(header + markdown + "\n")
