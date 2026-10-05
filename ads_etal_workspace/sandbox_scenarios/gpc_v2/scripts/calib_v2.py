"""Sim v2 calibration readout for one scenario: CALIBRATION.md ranges plus the emergent ι by keyword type.

    PYTHONPATH=. .venv/bin/python scripts/calib_v2.py sc1_cannibal --seeds 7 11
"""
from __future__ import annotations

import argparse

import pandas as pd

from gpc.policy import NoOpPolicy
from gpc.runner import simulate
from gpc.world import WARMUP_DAYS, build_world


def readout(seed: int, scenario: str) -> dict:
    w = build_world(seed=seed, scenario=scenario)
    res = simulate(w, NoOpPolicy(), n_runs=0)          # warm-up only
    f, sc, cd = res.daily_facts, res.sku_city_daily, res.campaign_daily
    kt = w.public["keywords"].set_index("keyword_id").keyword_type
    f = f.assign(kt=f.keyword_id.map(kt))
    g = f.groupby("kt")[["ad_revenue_inr", "spend_inr"]].sum()
    out = {"seed": seed, **{f"droas_{k}": round(v, 2) for k, v in (g.ad_revenue_inr / g.spend_inr).items()},
           "droas_all": round(f.ad_revenue_inr.sum() / f.spend_inr.sum(), 2),
           "spend_per_day": round(f.spend_inr.sum() / WARMUP_DAYS),
           "ad_share_units": round(sc.ad_units.sum() / sc.total_units.sum(), 3),
           "runout_share": round(cd.ran_out.mean(), 3)}
    dec = res.truth_tables.get("truth_decomp")
    if dec is not None and len(dec):
        dec = dec.assign(kt=dec.keyword_id.map(kt))
        s = dec.groupby("kt")[["ad_orders", "self", "sibling", "competitor", "expansion", "excess"]].sum()
        for k, r in s.iterrows():
            out[f"iota_sku_{k}"] = round(1 - r["self"] / r.ad_orders, 3)
            out[f"iota_brand_{k}"] = round((r.competitor + r.expansion) / r.ad_orders, 3)
            out[f"sib_{k}"] = round(r.sibling / r.ad_orders, 3)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seeds", type=int, nargs="+", default=[7])
    a = ap.parse_args()
    df = pd.DataFrame([readout(s, a.scenario) for s in a.seeds]).set_index("seed").T
    print(df.to_string())
