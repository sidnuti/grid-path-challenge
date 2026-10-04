"""X8 detail: what the real-LLM arms did, world by world and run by run.

    PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_detail      (from grid-path-challenge/)

Writes experiments/results/x8_detail.md + .json. Uses whatever LLM worlds are cached so far.
"""

from __future__ import annotations

import collections
import json
import re

import numpy as np
import pandas as pd

from experiments.lib import stats
from experiments.lib.funnel import floor_status, outcome
from experiments.lib.report import md_table, save
from experiments.lib.runs import CACHE, load_latest
from experiments.x8_l2prime.x8_run import true_usd

ARMS = ["l2p_aug_llm", "l2p_nat_llm", "l2pv2_aug_llm", "l2pv2_nat_llm", "l12_llm"]


def cached_worlds():
    out = collections.defaultdict(list)
    for p in CACHE.glob("*.pkl"):
        m = re.match(r"((?:l2p_(?:aug|nat)|l2pv2_(?:aug|nat)|l12)_llm)_r(\d)__(\d+)__(\w+)__", p.name)
        if m:
            out[m.group(1)].append((int(m.group(2)), int(m.group(3)), m.group(4)))
    return {k: sorted(set(v)) for k, v in out.items()}


def leaf_stats(res):
    c = collections.Counter()
    reasons = collections.Counter()
    tin = tout = wall = 0
    for r in res.runs:
        for m in (r["trace"] or {}).get("leaf_calls", []) or []:
            c[(m.get("leaf"), m.get("outcome"))] += 1
            if m.get("outcome") == "default":
                reasons[re.sub(r":.*", "", str(m.get("reason", "validation failed")))[:40]] += 1
            u = m.get("usage") or {}
            tin += u.get("tokens_in", 0); tout += u.get("tokens_out", 0)
            wall += m.get("wall_clock_s", 0) or 0
    return c, reasons, tin, tout, wall


def l2p_run_rows(res):
    rows = []
    for r in res.runs:
        t = r["trace"] or {}
        plan = t.get("plan") or {}
        comp = t.get("compile") or {}
        fin = r["final"]
        verbs = collections.Counter(i["verb"] for i in plan.get("intents", []))
        types = collections.Counter(fin.action_type) if len(fin) else collections.Counter()
        rej = collections.Counter(re.sub(r"\(.*|C-S\d.*|\d+", "", x["reason"]).strip()[:45] for x in comp.get("rejected", []))
        fc = t.get("first_compile") or {}
        rows.append({"run": r["run"], "shipped_from": t.get("shipped_from"), "fallback": t.get("fallback_reason"),
                     "intents": len(plan.get("intents", [])), "first_plan_intents": fc.get("n_intents"),
                     "repair_intents": fc.get("n_repair_intents"), "rejected": len(comp.get("rejected", [])),
                     "from_intents": comp.get("n_from_intents", 0), "l0_overridden": comp.get("l0_overridden", 0),
                     "l0_held": comp.get("l0_held", 0), "allowance_used": comp.get("allowance_used"),
                     "allowance_total": comp.get("allowance_total"), "shipped": len(fin),
                     "verbs": dict(verbs), "actions": dict(types), "top_rejections": dict(rej.most_common(3)),
                     "notes": (plan.get("notes") or "")[:220], "stance": plan.get("stance", [])})
    return rows


def spend_mix(res, l0, world_kt):
    """Eval-window spend change vs L0 by keyword type and by SKU (₹/day), and allowance use."""
    from gpc.world import WARMUP_DAYS
    out = {}
    for name, r in (("arm", res), ("l0", l0)):
        f = r.daily_facts[r.daily_facts.day >= WARMUP_DAYS]
        days = f.day.nunique()
        out[name] = (f.assign(kt=f.keyword_id.map(world_kt)).groupby("kt").spend_inr.sum() / days,
                     f.groupby("sku_id").spend_inr.sum() / days)
    by_type = (out["arm"][0] - out["l0"][0]).round(0).to_dict()
    by_sku = (out["arm"][1] - out["l0"][1]).round(0).to_dict()
    return by_type, by_sku


def main():
    have = cached_worlds()
    world_rows, run_rows, leaf_rows = [], [], []
    hashes = set()
    intents_by = collections.defaultdict(collections.Counter)
    for arm in ARMS:
        for rep, seed, sc in have.get(arm, []):
            name = f"{arm}_r{rep}"
            res, h = load_latest(name, seed, sc)
            l0, h0 = load_latest("l0", seed, sc)
            base, hb = load_latest("baseline", seed, sc)
            hashes |= {h, h0, hb}
            o, o0, ob = outcome(res), outcome(l0), outcome(base)
            f, f0 = floor_status(res), floor_status(l0)
            c, reasons, tin, tout, wall = leaf_stats(res)
            calls = sum(c.values())
            defaults = sum(v for (lf, oc), v in c.items() if oc == "default")
            world_rows.append({"arm": arm, "rep": rep, "seed": seed,
                               "vs_l0_pct": stats.paired_lift_pct(o["offtake_inr"], o0["offtake_inr"]),
                               "vs_baseline_pct": stats.paired_lift_pct(o["offtake_inr"], ob["offtake_inr"]),
                               "droas": f["droas"], "floor_met": f["met"], "margin": f["margin"], "l0_margin": f0["margin"],
                               "spend_vs_l0_pct": stats.paired_lift_pct(o["spend_inr"], o0["spend_inr"]),
                               "ad_units_vs_l0_pct": stats.paired_lift_pct(o["ad_units"], o0["ad_units"]),
                               "organic_vs_l0_pct": stats.paired_lift_pct(o["organic_units"], o0["organic_units"]),
                               "llm_calls": calls, "defaults": defaults, "tokens_in": tin, "tokens_out": tout,
                               "usd": true_usd(tin, tout), "llm_wall_s": wall,
                               "shipped": sum(len(r["final"]) for r in res.runs),
                               "fallback_runs": sum(1 for r in res.runs if (r["trace"] or {}).get("fallback_reason"))})
            leaf_rows.append({"arm": arm, "rep": rep, "seed": seed,
                              **{f"{lf}:{oc}": v for (lf, oc), v in sorted(c.items(), key=lambda x: str(x))},
                              "default_reasons": dict(reasons)})
            if arm.startswith(("l2p_", "l2pv2_")):
                for row in l2p_run_rows(res):
                    run_rows.append({"arm": arm, "rep": rep, "seed": seed, **row})
                    intents_by[arm].update(row["verbs"])
    W = pd.DataFrame(world_rows)
    from gpc.world import build_world
    mix_rows = []
    for row in world_rows:
        if not row["arm"].startswith(("l2p_", "l2pv2_")):
            continue
        kt = build_world(row["seed"]).public["keywords"].set_index("keyword_id").keyword_type
        res, _ = load_latest(f"{row['arm']}_r{row['rep']}", row["seed"], "dev")
        l0, _ = load_latest("l0", row["seed"], "dev")
        bt, bs = spend_mix(res, l0, kt)
        mix_rows.append({"arm": row["arm"], "seed": row["seed"], **{f"Δ₹/d {k}": v for k, v in bt.items()}, **{f"Δ₹/d {k}": v for k, v in bs.items()}})
    ci_rows = []
    for arm, g in W[W.rep == 0].groupby("arm"):
        sm = stats.summarize(list(g.vs_l0_pct))
        ci_rows.append({"arm": arm, "worlds": sm["n"], "mean_vs_l0": sm["mean"], "ci95": f"{sm['ci95_lo']:.2f} … {sm['ci95_hi']:.2f}" if sm["n"] > 1 else "",
                        "p_signflip": sm.get("p_signflip"), "better": int((g.vs_l0_pct > 0).sum()),
                        "mean_spend_vs_l0": g.spend_vs_l0_pct.mean(), "mean_margin": g.margin.mean(), "mean_l0_margin": g.l0_margin.mean()})
    md = ["# X8 detail: what the real-LLM arms did (cached worlds so far)\n",
          "Model qwen/qwen3.7-flash via OpenRouter, reasoning on. Paired vs `l0` and `baseline` in the same world. "
          "$ repriced from tokens at list price ($0.03 / $0.13 per M).\n"]
    if len(W):
        g = W.groupby("arm").agg(worlds=("seed", "size"), vs_l0_mean=("vs_l0_pct", "mean"), vs_l0_min=("vs_l0_pct", "min"),
                                 vs_l0_max=("vs_l0_pct", "max"), better=("vs_l0_pct", lambda x: int((x > 0).sum())),
                                 floor_met=("floor_met", "sum"), min_margin=("margin", "min"),
                                 usd_per_world=("usd", "mean"), llm_min_per_world=("llm_wall_s", lambda x: x.mean() / 60),
                                 calls_per_world=("llm_calls", "mean"), default_share=("defaults", "sum"))
        g["default_share"] = W.groupby("arm").defaults.sum() / W.groupby("arm").llm_calls.sum().replace(0, np.nan)
        md += ["## Replicate 0, paired over worlds (t-CI, exact sign-flip p)\n", md_table(pd.DataFrame(ci_rows)),
               "\n## Where L2′ moved spend vs L0 (eval window, ₹/day)\n", md_table(pd.DataFrame(mix_rows).fillna(0)),
               "\n## Summary by arm (all replicates)\n", md_table(g.reset_index()), "\n## Per world\n",
               md_table(W.drop(columns=["tokens_in", "tokens_out"])), "\n## LLM calls by leaf and outcome\n",
               md_table(pd.DataFrame(leaf_rows).fillna(0))]
    if run_rows:
        R = pd.DataFrame(run_rows)
        md += ["\n## L2′ run by run\n", md_table(R.drop(columns=["notes", "stance", "verbs", "actions", "top_rejections"])),
               "\n## L2′ intent verbs (total)\n", "\n".join(f"- `{a}`: {dict(c)}" for a, c in intents_by.items()),
               "\n## L2′ plan notes and top rejections, per run\n",
               "\n".join(f"- `{r['arm']}` r{r['rep']} seed {r['seed']} run {r['run']}: {r['notes']}  \n  rejections: {r['top_rejections']}  \n  actions: {r['actions']}"
                         for r in run_rows)]
    save("x8_detail", {"worlds": world_rows, "runs": run_rows, "leaves": leaf_rows, "ci": ci_rows, "mix": mix_rows}, "\n".join(md), hashes)
    print("\n".join(md)[:12000])


if __name__ == "__main__":
    main()
