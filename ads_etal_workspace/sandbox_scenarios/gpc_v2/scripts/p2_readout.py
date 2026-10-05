"""P2 readout: calibration and mechanism probes for every sim v2 scenario (design/02 §8 traps, §10 gates).

    PYTHONPATH=. .venv/bin/python scripts/p2_readout.py --seeds 7 11 23 --out ../results/p2

Writes one CSV per scenario (rows = metric, columns = seed) and `readout.md`. All probes run the market
without guardrails from a fixed schedule (gpc.score_v2.run_schedule), so they measure the mechanism, not a policy.
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from gpc.score_v2 import ads_off_tables, run_schedule, salvage_value
from gpc.world import WARMUP_DAYS, build_world

SCENARIOS = ["dev", "sc1_cannibal", "sc2_brand_assoc", "sc3_festive", "sc4_seasonal", "sc_all"]


def _brand_offtake(t: dict, d0: int = WARMUP_DAYS) -> float:
    s = t["sku_city_daily"]
    return float(s[s.day >= d0].offtake_inr.sum())


def _pause(kids):
    def f(c, k):
        return c, k.assign(active=k.active & ~k.keyword_id.isin(kids))
    return f


def readout(args) -> dict:
    scenario, seed = args
    t0 = time.time()
    w = build_world(seed, scenario)
    base = run_schedule(w)                                        # starting set-up held for 70 days
    off = ads_off_tables(w)
    f, sc, cd = base["daily_facts"], base["sku_city_daily"], base["campaign_daily"]
    kt = w.public["keywords"].set_index("keyword_id").keyword_type
    warm = f[f.day < WARMUP_DAYS].assign(kt=lambda d: d.keyword_id.map(kt))
    g = warm.groupby("kt")[["ad_revenue_inr", "spend_inr"]].sum()
    r = {"scenario": scenario, "seed": seed}
    r.update({f"warm_droas_{k}": round(v, 2) for k, v in (g.ad_revenue_inr / g.spend_inr).items()})
    ws = sc[sc.day < WARMUP_DAYS]
    r["warm_ad_share_units"] = round(ws.ad_units.sum() / ws.total_units.sum(), 3)
    legacy_camps = cd.campaign_id.str.match(r"C-S[1-5]-")      # ephemeral campaigns cannot spend before launch
    r["warm_runout_share"] = round(cd[(cd.day < WARMUP_DAYS) & legacy_camps].ran_out.mean(), 3)
    post = f[f.day >= WARMUP_DAYS]
    inc = _brand_offtake(base) - _brand_offtake(off)
    for sku, v in salvage_value(w, base.get("pub_stock_daily")).items():
        inc += v - salvage_value(w, off.get("pub_stock_daily"))[sku]
    r["hold_increv"] = round(inc)
    r["hold_spend"] = round(post.spend_inr.sum())
    r["hold_iroas"] = round(inc / post.spend_inr.sum(), 3)
    r["hold_droas"] = round(post.ad_revenue_inr.sum() / post.spend_inr.sum(), 3)
    dec = base.get("truth_decomp")
    if dec is not None:
        d = dec[dec.day >= WARMUP_DAYS]
        for k in ("K01", "K03", "K05", "K07", "K09"):
            dk = d[d.keyword_id == k]
            if len(dk) and dk.ad_orders.sum() > 0:
                r[f"iota_brand_{k}"] = round((dk.competitor.sum() + dk.expansion.sum()) / dk.ad_orders.sum(), 3)
                r[f"sibling_{k}"] = round(dk.sibling.sum() / dk.ad_orders.sum(), 3)
        fk = post[post.keyword_id == "K07"]
        r["droas_K07"] = round(fk.ad_revenue_inr.sum() / fk.spend_inr.sum(), 2) if len(fk) else None
    # competitors: festive CPM ratio on K03 (price multiplier at peak vs a pre-window day)
    tc = base.get("truth_competitors")
    if tc is not None and w.truth.get("calendar", {}).get("events"):
        ag = w.truth["competitors"]["agents"]
        def pm(day, kid="K03"):
            b = tc[tc.day == day].set_index("agent").bid_level
            sh = {a: v["keywords"].get(kid, 0.0) for a, v in ag.items()}
            return sum(sh[a] * b[a] for a in sh) + (1 - sum(sh.values())) * b["rest"]
        peak = w.truth["calendar"]["events"][0]["peak_day"]
        r["festive_cpm_ratio_K03"] = round(pm(peak) / pm(35), 3)
    # stock
    st = base.get("pub_stock_daily")
    if st is not None and len(st):
        r["stock_min"] = float(st.stock_end.min())
        out_days = st[st.stock_end <= 0].groupby("city_id").day.min()
        r["stockout_cities"] = int(len(out_days))
        r["stockout_first_day"] = int(out_days.min()) if len(out_days) else None
        s6 = sc[(sc.sku_id == "S6")]
        after = [s6[(s6.city_id == c) & (s6.day > dd)].osa.max() for c, dd in out_days.items()]
        r["s6_osa_after_stockout_max"] = float(max(after)) if after else None
        r["s6_salvage_inr"] = round(salvage_value(w, st).get("S6", 0.0))
        r["s6_units_ad"] = int(s6.ad_units.sum())
        r["s6_units_organic"] = int(s6.organic_units.sum())
        r["s6_units_organic_adsoff"] = int(off["sku_city_daily"].query("sku_id == 'S6'").organic_units.sum())
    # opportunism probe: pause K01 everywhere after warm-up
    if w.truth.get("competitors", {}).get("opportunism"):
        p01 = run_schedule(w, _pause(["K01"]))
        cq = p01["truth_competitors"]
        on = cq[cq.agent.str.startswith("conquest_")].groupby("day").bid_level.sum()
        r["probe_pauseK01_conquest_cities_end"] = int(on.iloc[-1])
        r["probe_pauseK01_first_conquest_day"] = int(on[on > 0].index.min()) if (on > 0).any() else None
        saved = post[post.keyword_id == "K01"].spend_inr.sum()
        lost = _brand_offtake(base) - _brand_offtake(p01)
        r["probe_pauseK01_spend_saved"] = round(saved)
        r["probe_pauseK01_offtake_lost"] = round(lost)
    # reformulation / attribution-illusion probe: pause K03 everywhere after warm-up
    if w.truth.get("intent"):
        p03 = run_schedule(w, _pause(["K03"]))
        a, b = base["daily_facts"], p03["daily_facts"]
        a1, b1 = a[(a.day >= WARMUP_DAYS) & (a.keyword_id == "K01")], b[(b.day >= WARMUP_DAYS) & (b.keyword_id == "K01")]
        r["probe_pauseK03_K01_impr_change"] = round(b1.impressions.sum() / a1.impressions.sum() - 1, 4)
        r["probe_pauseK03_K01_attr_droas_change"] = round(
            (b1.ad_revenue_inr.sum() / b1.spend_inr.sum()) / (a1.ad_revenue_inr.sum() / a1.spend_inr.sum()) - 1, 4)
        r["probe_pauseK03_K01_attr_rev_change"] = round(b1.ad_revenue_inr.sum() / a1.ad_revenue_inr.sum() - 1, 4)
        r["probe_pauseK03_brand_offtake_change"] = round(_brand_offtake(p03) / _brand_offtake(base) - 1, 4)
    r["secs"] = round(time.time() - t0, 1)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11, 23])
    ap.add_argument("--scenarios", nargs="+", default=SCENARIOS)
    ap.add_argument("--out", default="../results/p2")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(s, seed) for s in a.scenarios for seed in a.seeds]
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(readout, jobs))
    df = pd.DataFrame(rows)
    md = ["# P2 readout (fixed starting set-up held after warm-up; probes bypass guardrails)", ""]
    for s in a.scenarios:
        t = df[df.scenario == s].drop(columns="scenario").set_index("seed").T.dropna(how="all")
        t.to_csv(out / f"readout_{s}.csv")
        md += [f"## {s}", "", t.to_markdown(), ""]
    (out / "readout.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
