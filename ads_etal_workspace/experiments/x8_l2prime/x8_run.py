"""X8 · L2′: does an expressive LLM arm (intents compiled by L0) beat L0 and L0 + L1/L2?

    run     simulate arms on a world set into the shared cache; LLM arms check a spend ledger first
    report  paired comparison vs l0 and baseline, behaviour of the intent plans, cost

    cd grid-path-challenge
    PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run run --arms l0 baseline l2p_aug_rules --worlds dev6 --jobs 6
    PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run report --worlds dev6

LLM arms (`*_llm_r<k>`, `l12_llm_r<k>`) run with LLM_MODE=record against `LLM_MODEL` (default
qwen/qwen3.7-flash via OpenRouter, reasoning on), a per-run cap of $0.25 and a ledger-wide cap (`--cap`, $10). With
N parallel workers the ledger can overshoot by at most N simulations' cost.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "experiments" / "results" / "x8_spend.jsonl"
LLM_DEFAULTS = {"LLM_MODE": "record", "LLM_PROVIDER": "openrouter", "LLM_MODEL": "qwen/qwen3.7-flash",
                "L2P_MODEL": "qwen/qwen3.7-flash", "L2P_REASONING": "on",
                "LLM_CACHE_DIR": str(ROOT / "grid-path-challenge" / "llm_cache")}


def worlds(name: str) -> list[tuple[int, str]]:
    from experiments.lib.scenarios import scenario_paths
    if name == "dev6":
        return [(s, "dev") for s in (7, 11, 23, 42, 101, 202)]
    if name == "pert3":
        sp = scenario_paths()
        return [(303, sp["P4_all_three_shifted_earlier"]), (303, sp["V_iota_lo"]), (304, sp["P6_demand_shock_on_brand"])]
    if name == "fresh6":
        return [(s, "dev") for s in range(3001, 3007)]
    raise KeyError(name)


def is_llm(arm: str) -> bool:
    return "_llm" in arm


def spent() -> float:
    """Ledger total, repriced from tokens (older lines may carry the harness Meter's fallback price)."""
    if not LEDGER.exists():
        return 0.0
    tot = 0.0
    for l in LEDGER.read_text().splitlines():
        if l.strip():
            d = json.loads(l)
            tot += true_usd(d.get("tokens_in", 0), d.get("tokens_out", 0)) if "tokens_in" in d else d["usd"]
    return tot


def true_usd(tokens_in: float, tokens_out: float, model: str | None = None) -> float:
    """Reprice from tokens: the harness Meter (used by the L1/L2 arm) has no row for qwen3.7-flash and
    falls back to $3/$15 per million tokens, ~100x the list price."""
    from harness_l2p.llm import price_of
    p = price_of(model or os.environ.get("LLM_MODEL", LLM_DEFAULTS["LLM_MODEL"]))
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1e6


def usage_of_result(res) -> dict:
    u = collections.Counter()
    for r in res.runs:
        for m in (r["trace"] or {}).get("leaf_calls", []) or []:
            us = m.get("usage") or {}
            u["calls"] += us.get("calls", 0)
            u["tokens_in"] += us.get("tokens_in", 0)
            u["tokens_out"] += us.get("tokens_out", 0)
            u["usd"] += us.get("cost_usd", 0.0)
            u["wall_s"] += m.get("wall_clock_s", 0.0) or 0.0
    u["metered_usd"] = u.get("usd", 0.0)
    u["usd"] = true_usd(u.get("tokens_in", 0), u.get("tokens_out", 0))
    return dict(u)


def _factory(arm, seed, scenario):
    from experiments.lib.arms import factory, l2p_factory
    if arm.startswith(("l2p_", "l2pv2_", "l12_")):
        return l2p_factory(arm, seed, scenario)
    return factory(arm)


def _one(args):
    arm, seed, scenario, cap = args
    from experiments.lib.runs import CACHE, code_hash, run_cached
    if is_llm(arm):
        for k, v in LLM_DEFAULTS.items():
            os.environ.setdefault(k, v)
        key = CACHE / f"{arm}__{seed}__{Path(scenario).stem}__{code_hash()}.pkl"
        if not key.exists() and spent() >= cap:
            return arm, seed, Path(scenario).stem, "skipped: spend cap reached", 0.0
    t0 = time.time()
    cached = (CACHE / f"{arm}__{seed}__{Path(scenario).stem}__{code_hash()}.pkl").exists()
    res = run_cached(arm, _factory(arm, seed, scenario), seed, scenario)
    usd = 0.0
    if is_llm(arm) and not cached:
        u = usage_of_result(res)
        usd = u.get("usd", 0.0)
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as fh:
            fh.write(json.dumps({"arm": arm, "seed": seed, "scenario": Path(scenario).stem, **u, "usd": usd}) + "\n")
    return arm, seed, Path(scenario).stem, f"{time.time() - t0:.0f}s", round(usd, 4)


def cmd_run(a):
    jobs = [(arm, s, sc, a.cap) for s, sc in worlds(a.worlds) for arm in a.arms]
    print(f"{len(jobs)} simulations, {a.jobs} workers, ledger ${spent():.3f} / cap ${a.cap}", flush=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(_one, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            print(f"[{i}/{len(jobs)}] {f.result()}", flush=True)
    print(f"ledger now ${spent():.3f}")


# ── report ───────────────────────────────────────────────────────────────────────────────────────────
def _behaviour(res) -> dict:
    n_runs = len(res.runs)
    prop = sum(len(r["proposed"]) for r in res.runs)
    ship = sum(len(r["final"]) for r in res.runs)
    types = collections.Counter(t for r in res.runs if len(r["final"]) for t in r["final"].action_type)
    intents = rejects = from_int = fallbacks = 0
    verbs = collections.Counter()
    for r in res.runs:
        t = r["trace"] or {}
        if t.get("fallback_reason"):
            fallbacks += 1
        plan = t.get("plan") or {}
        intents += len(plan.get("intents", []))
        verbs.update(i["verb"] for i in plan.get("intents", []))
        c = t.get("compile") or {}
        rejects += len(c.get("rejected", []))
        from_int += c.get("n_from_intents", 0)
    return {"proposed_per_run": prop / n_runs, "shipped_per_run": ship / n_runs,
            "blocked_share": 1 - ship / prop if prop else 0.0, "intents_per_run": intents / n_runs,
            "rejects_per_run": rejects / n_runs, "from_intents_per_run": from_int / n_runs, "fallback_runs": fallbacks,
            "pause": types.get("pause_keyword", 0), "budget_cut": types.get("reduce_budget", 0),
            "budget_raise": types.get("increase_budget", 0), "dayparts": types.get("set_dayparts", 0),
            "verbs": dict(verbs)}


def cmd_report(a):
    from gpc.world import build_world
    from experiments.lib import stats
    from experiments.lib.funnel import floor_status, funnel, outcome
    from experiments.lib.report import md_table, save
    from experiments.lib.runs import load_latest

    W = worlds(a.worlds)
    hashes: set[str] = set()
    base = {}
    for ref in ("l0", "baseline"):
        for s, sc in W:
            r, h = load_latest(ref, s, sc)
            hashes.add(h)
            base[(ref, s, sc)] = r
    rows, beh_rows = [], []
    for arm in a.arms:
        lifts = {"l0": [], "baseline": []}
        fl, margins, iroas_d, beh, us = [], [], [], [], collections.Counter()
        first_sets = []
        for s, sc in W:
            try:
                r, h = load_latest(arm, s, sc)
            except FileNotFoundError:
                continue
            hashes.add(h)
            o = outcome(r)["offtake_inr"]
            for ref in lifts:
                lifts[ref].append(stats.paired_lift_pct(o, outcome(base[(ref, s, sc)])["offtake_inr"]))
            f = floor_status(r)
            fl.append(f["met"])
            margins.append(f["margin"])
            w = build_world(s, sc)
            ti = float(funnel(w, r.daily_facts).true_iroas.iloc[0])
            ti0 = float(funnel(w, base[("l0", s, sc)].daily_facts).true_iroas.iloc[0])
            iroas_d.append(ti - ti0)
            beh.append(_behaviour(r))
            us.update(usage_of_result(r))
            fin = r.runs[0]["final"]
            first_sets.append(set(zip(fin.campaign_id, fin.keyword_id.fillna(""), fin.action_type)) if len(fin) else set())
        if not fl:
            continue
        n = len(fl)
        sl0, sb = stats.summarize(lifts["l0"]), stats.summarize(lifts["baseline"])
        rows.append({"arm": arm, "worlds": n, "vs_l0_pct": sl0["mean"], "ci_l0": f"{sl0['ci95_lo']:.3f} … {sl0['ci95_hi']:.3f}" if n > 1 else "",
                     "p_l0": sl0.get("p_signflip"), "worse/better": f"{sum(x < 0 for x in lifts['l0'])}/{sum(x > 0 for x in lifts['l0'])}",
                     "vs_baseline_pct": sb["mean"], "floor_met": f"{sum(fl)}/{n}", "min_margin": min(margins),
                     "true_iroas_vs_l0": float(np.mean(iroas_d)),
                     "usd_per_run": us.get("usd", 0.0) / (6 * n), "tokens_per_run": (us.get("tokens_in", 0) + us.get("tokens_out", 0)) / (6 * n),
                     "calls_per_run": us.get("calls", 0) / (6 * n)})
        bm = pd.DataFrame(beh)
        beh_rows.append({"arm": arm, **{k: bm[k].mean() for k in bm.columns if k != "verbs"},
                         "verbs": dict(sum((collections.Counter(v) for v in bm.verbs), collections.Counter()))})
    res = pd.DataFrame(rows)
    bdf = pd.DataFrame(beh_rows)
    md = [f"# X8 · L2′ on {a.worlds} ({len(W)} worlds)\n",
          "Paired offtake lift (eval window) vs the cached `l0` and `baseline` arms in the same world. t-CI, exact sign-flip p. "
          "`true_iroas_vs_l0` = change in realised incremental revenue per rupee (offline, from hidden truth). "
          "Costs are per weekly run.\n", md_table(res), "\n## Behaviour (per world, mean)\n",
          md_table(bdf.drop(columns=["verbs"])), "\n## Intent verbs (total)\n",
          "\n".join(f"- `{r.arm}`: {r.verbs}" for r in bdf.itertuples()),
          f"\n\nLedger spend so far: ${spent():.3f}"]
    save(f"x8_l2prime_{a.worlds}", {"results": rows, "behaviour": beh_rows}, "\n".join(md), hashes)
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arms", nargs="+", required=True)
    r.add_argument("--worlds", default="dev6")
    r.add_argument("--jobs", type=int, default=6)
    r.add_argument("--cap", type=float, default=10.0)
    p = sub.add_parser("report")
    p.add_argument("--arms", nargs="+", required=True)
    p.add_argument("--worlds", default="dev6")
    a = ap.parse_args()
    {"run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
