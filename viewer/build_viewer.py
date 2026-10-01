"""Build viewer/grid_path_viewer.html — a self-contained page that walks through the traversal.

    python viewer/build_viewer.py            # simulates no-op, baseline, naive scaler (~2 min)

It also writes the baseline dataset to data/ (same as `python -m gpc.runner --out data`).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.naive_scaler import NaiveScaler  # noqa: E402
from gpc.policy import DeterministicTraversal, NoOpPolicy  # noqa: E402
from gpc.runner import simulate, write_outputs  # noqa: E402
from gpc.score import summarize  # noqa: E402
from gpc.world import RUN_DAYS, WARMUP_DAYS, build_world  # noqa: E402


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def rows(df: pd.DataFrame | None, cols: list[str] | None = None) -> list[dict]:
    if df is None or not len(df):
        return []
    d = df[cols] if cols else df
    return [{k: _clean(v) for k, v in r.items()} for r in d.to_dict("records")]


def weekly(res) -> list[dict]:
    s, f = res.sku_city_daily, res.daily_facts
    out = []
    periods = [("Warm-up", 0, WARMUP_DAYS)] + [(f"Run {r}", WARMUP_DAYS + (r - 1) * RUN_DAYS, WARMUP_DAYS + r * RUN_DAYS)
                                              for r in range(1, 7)]
    for label, a, b in periods:
        ss, ff = s[(s.day >= a) & (s.day < b)], f[(f.day >= a) & (f.day < b)]
        n = b - a
        out.append({"label": label, "offtake_day": round(ss.offtake_inr.sum() / n),
                    "spend_day": round(ff.spend_inr.sum() / n),
                    "droas": round(ff.ad_revenue_inr.sum() / ff.spend_inr.sum(), 3) if ff.spend_inr.sum() else None})
    return out


def main() -> None:
    results = {}
    for name, pol in [("no_op", NoOpPolicy()), ("baseline", DeterministicTraversal()), ("naive", NaiveScaler())]:
        print("simulating", name, flush=True)
        results[name] = simulate(build_world(), pol)
    base_res = results["baseline"]
    write_outputs(build_world(), base_res, ROOT / "data")

    w = build_world().public
    runs = []
    for r in base_res.runs:
        t = r["trace"]
        grid = t["grid"][["campaign_id", "keyword_id", "daypart", "slot", "cpm_inr", "impressions_day", "orders_day",
                          "spend_day", "revenue_day", "droas", "reach_source", "tier", "current_slot"]]
        v = t["verdicts"]
        runs.append({
            "run": r["run"], "date": r["date"], "notes": {k: _clean(x) for k, x in t["notes"].items()},
            "guardrail_summary": {k: _clean(x) for k, x in (r["guardrail_summary"] or {}).items()},
            "verdict_counts": v.verdict.value_counts().to_dict(),
            "grid": rows(grid), "verdicts": rows(v), "pacing": rows(t["pacing"]),
            "bids": rows(t["bid_choices"]), "options": rows(t["bid_options"]),
            "sources": rows(t["sources"]), "demands": rows(t["demands"]), "transfers": rows(t["transfers"]),
            "dayparts": rows(t["dayparts"]), "ledger_log": rows(t["ledger_log"]),
            "proposed": rows(r["proposed"]), "actions": rows(r["final"]), "guardrail_log": rows(r["guardrail_log"]),
            "bids_before": rows(r["campaign_keywords_before"]), "campaigns_before": rows(r["campaigns_before"]),
        })
    data = {
        "base": {k: rows(w[k]) for k in ("cities", "products", "keywords", "keyword_sku", "campaigns", "plan",
                                         "industry_rank_curve", "dayparts")},
        "series": {k: weekly(v) for k, v in results.items()},
        "summary": {k: {kk: _clean(vv) if not isinstance(vv, dict) else vv for kk, vv in summarize(v).items()}
                    for k, v in results.items()},
        "runs": runs,
    }
    tpl = (ROOT / "viewer" / "template.html").read_text()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    out = ROOT / "viewer" / "grid_path_viewer.html"
    out.write_text(html)
    print("wrote", out, f"{len(html)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
