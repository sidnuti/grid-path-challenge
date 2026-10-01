"""Run a policy through the warm-up and N weekly runs, against the hidden market.

    python -m gpc.runner --policy baseline --out data          # writes the provided dataset
    python -m gpc.runner --policy my_module:MyPolicy           # your policy, dev scenario

Timeline: 28 warm-up days on the starting set-up, then each run = decide on day D → guardrails →
apply → simulate days D … D+6.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .guardrails import apply_guardrails
from .market import Market
from .observation import Observation
from .policy import DeterministicTraversal, NoOpPolicy, Policy
from .world import DAYPARTS, N_RUNS, RUN_DAYS, WARMUP_DAYS, World, build_world

ROAS_TOLERANCE = 0.02


@dataclass
class SimResult:
    policy: str
    daily_facts: pd.DataFrame
    campaign_daily: pd.DataFrame
    sku_city_daily: pd.DataFrame
    runs: list[dict]
    warmup_droas: float


def apply_actions(campaigns: pd.DataFrame, ck: pd.DataFrame, actions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    campaigns, ck = campaigns.copy(), ck.copy()
    for a in actions.itertuples():
        if a.action_type in ("increase_cpm", "reduce_cpm"):
            m = (ck.campaign_id == a.campaign_id) & (ck.keyword_id == a.keyword_id)
            ck.loc[m, "bid_cpm_inr"] = float(a.new_value)
        elif a.action_type == "pause_keyword":
            m = (ck.campaign_id == a.campaign_id) & (ck.keyword_id == a.keyword_id)
            ck.loc[m, "active"] = False
        elif a.action_type in ("increase_budget", "reduce_budget"):
            campaigns.loc[campaigns.campaign_id == a.campaign_id, "daily_budget_inr"] = float(a.new_value)
        elif a.action_type == "set_dayparts":
            keep = set(str(a.new_value).split(","))
            for dp in DAYPARTS:
                campaigns.loc[campaigns.campaign_id == a.campaign_id, f"on_{dp}"] = dp in keep
    return campaigns, ck


def _days(market: Market, start: int, n: int, campaigns, ck, acc: dict):
    for d in range(start, start + n):
        o = market.simulate_day(d, campaigns, ck)
        for k, v in o.items():
            acc[k].append(v)


def simulate(world: World, policy: Policy, n_runs: int = N_RUNS, out_dir: Path | None = None,
             verbose: bool = False) -> SimResult:
    market = Market(world)
    campaigns = world.public["campaigns"].copy()
    ck = world.public["campaign_keywords"].copy()
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    _days(market, 0, WARMUP_DAYS, campaigns, ck, acc)
    f = pd.concat(acc["daily_facts"])
    warm = float(f.ad_revenue_inr.sum() / f.spend_inr.sum())
    runs = []
    for r in range(1, n_runs + 1):
        day = WARMUP_DAYS + (r - 1) * RUN_DAYS
        frames = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
        obs = Observation(run=r, day=day, public=world.public, campaigns=campaigns.copy(),
                          campaign_keywords=ck.copy(), roas_floor=warm * (1 - ROAS_TOLERANCE), warmup_droas=warm,
                          **frames)
        proposed = policy.recommend(obs)
        final, glog, gsum = apply_guardrails(obs, proposed)
        runs.append({"run": r, "day": day, "date": obs.date.isoformat(), "proposed": proposed, "final": final,
                     "guardrail_log": glog, "guardrail_summary": gsum, "trace": policy.last_trace,
                     "campaigns_before": campaigns.copy(), "campaign_keywords_before": ck.copy()})
        campaigns, ck = apply_actions(campaigns, ck, final)
        _days(market, day, RUN_DAYS, campaigns, ck, acc)
        if verbose:
            print(f"run {r} {obs.date}: proposed {len(proposed)} → shipped {len(final)}")
    frames = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    res = SimResult(policy.name, frames["daily_facts"], frames["campaign_daily"], frames["sku_city_daily"], runs, warm)
    if out_dir is not None:
        write_outputs(world, res, Path(out_dir))
    return res


def write_outputs(world: World, res: SimResult, out: Path) -> None:
    base = out / "base"
    base.mkdir(parents=True, exist_ok=True)
    for name, df in world.public.items():
        df.to_csv(base / f"{name}.csv", index=False)
    obs_dir = out / "observed"
    obs_dir.mkdir(parents=True, exist_ok=True)
    res.daily_facts.to_csv(obs_dir / "daily_facts.csv", index=False)
    res.campaign_daily.to_csv(obs_dir / "campaign_daily.csv", index=False)
    res.sku_city_daily.to_csv(obs_dir / "sku_city_daily.csv", index=False)
    for r in res.runs:
        d = out / "runs" / f"run_{r['run']:02d}"
        d.mkdir(parents=True, exist_ok=True)
        r["campaigns_before"].to_csv(d / "campaigns_before.csv", index=False)
        r["campaign_keywords_before"].to_csv(d / "campaign_keywords_before.csv", index=False)
        r["proposed"].to_csv(d / "proposed_actions.csv", index=False)
        r["final"].to_csv(d / "actions.csv", index=False)
        r["guardrail_log"].to_csv(d / "guardrail_log.csv", index=False)
        tr = r["trace"] or {}
        for k in ("grid", "verdicts", "pacing", "bid_choices", "bid_options", "sources", "demands", "transfers", "dayparts", "ledger_log"):
            if k in tr:
                tr[k].to_csv(d / f"{k}.csv", index=False)
        (d / "summary.json").write_text(json.dumps({"run": r["run"], "decision_date": r["date"],
                                                   "traversal": tr.get("notes", {}),
                                                   "guardrails": r["guardrail_summary"]}, indent=2))


def load_policy(spec: str) -> Policy:
    if spec == "baseline":
        return DeterministicTraversal()
    if spec == "no_op":
        return NoOpPolicy()
    mod, cls = spec.split(":")
    return getattr(importlib.import_module(mod), cls)()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="baseline")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scenario", default="dev")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = simulate(build_world(a.seed, a.scenario), load_policy(a.policy), out_dir=a.out, verbose=True)
    from .score import summarize
    print(json.dumps(summarize(res), indent=2))


if __name__ == "__main__":
    main()
