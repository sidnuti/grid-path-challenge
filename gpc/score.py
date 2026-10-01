"""Scoring. The objective is the brief's, in one line:

    maximise total SKU offtake (ad + organic, ₹) over the 6 runs
    subject to portfolio direct ROAS over the same 42 days ≥ warm-up direct ROAS × 0.98.

    python -m gpc.score --policy my_module:MyPolicy      # vs baseline and no-op, dev scenario

The eval scenario (different shocks, different seed) is run by Gobblecube, not shipped.
"""

from __future__ import annotations

import argparse
import json

from .runner import ROAS_TOLERANCE, SimResult, load_policy, simulate
from .world import WARMUP_DAYS, build_world


def summarize(res: SimResult) -> dict:
    f = res.daily_facts[res.daily_facts.day >= WARMUP_DAYS]
    s = res.sku_city_daily[res.sku_city_daily.day >= WARMUP_DAYS]
    w = res.sku_city_daily[res.sku_city_daily.day < WARMUP_DAYS]
    n_days = s.day.nunique()
    spend, adrev = f.spend_inr.sum(), f.ad_revenue_inr.sum()
    droas = adrev / spend if spend else 0.0
    floor = res.warmup_droas * (1 - ROAS_TOLERANCE)
    return {
        "policy": res.policy,
        "offtake_inr": round(float(s.offtake_inr.sum())),
        "offtake_inr_per_day": round(float(s.offtake_inr.sum() / n_days)),
        "warmup_offtake_inr_per_day": round(float(w.offtake_inr.sum() / w.day.nunique())),
        "ad_spend_inr_per_day": round(float(spend / n_days)),
        "direct_roas": round(float(droas), 3),
        "warmup_direct_roas": round(res.warmup_droas, 3),
        "roas_floor": round(floor, 3),
        "roas_constraint_met": bool(droas >= floor),
        "offtake_by_sku_per_day": {k: round(float(v / n_days)) for k, v in s.groupby("sku_id").offtake_inr.sum().items()},
        "actions_shipped": int(sum(len(r["final"]) for r in res.runs)),
        "actions_proposed": int(sum(len(r["proposed"]) for r in res.runs)),
    }


def compare(results: list[SimResult]) -> list[dict]:
    rows = [summarize(r) for r in results]
    base = next((r for r in rows if r["policy"] == "deterministic_traversal"), rows[0])
    for r in rows:
        r["offtake_vs_baseline_pct"] = round((r["offtake_inr"] / base["offtake_inr"] - 1) * 100, 2)
        r["score"] = r["offtake_vs_baseline_pct"] if r["roas_constraint_met"] else None
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="baseline")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scenario", default="dev")
    a = ap.parse_args()
    world = lambda: build_world(a.seed, a.scenario)  # noqa: E731 — fresh world per policy
    specs = ["no_op", "baseline"] + ([a.policy] if a.policy not in ("baseline", "no_op") else [])
    out = compare([simulate(world(), load_policy(s)) for s in specs])
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
