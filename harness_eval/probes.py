"""E1-E10 probes against `data/` — the baseline's own provided trajectory (`make data`'s output),
read back from CSV, never from `gpc.market`/`gpc.world` truth or the dev scenario file. This is
the same evidence table the plan and the problem-mapped reports cite; this script re-derives it
from the shipped data rather than asking anyone to trust the earlier hand-written numbers.

Two evidence items (E2 sibling/grid-dependent reads) use `data/runs/run_01/{campaigns,
campaign_keywords}_before.csv` — the live bid/budget snapshot right after warm-up, before the
baseline's first decision — since `data/base/*.csv` is `world.public` at *build* time (the
very first starting setup) and the fully-final post-run-6 state isn't separately serialized by
`gpc.runner.write_outputs`. Noted inline, not silently assumed, since it changes what "current
bid" means for the grid/siblings computations those probes run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gpc.engine.grid import build_grid
from gpc.observation import Observation
from gpc.world import N_RUNS, RUN_DAYS, WARMUP_DAYS

from harness.config import load_params
from harness.tools.incrementality import fit_type_incrementality
from harness.tools.shocks import detect_shocks
from harness.tools.siblings import contested_markets, markets

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_csv(path: Path) -> pd.DataFrame:
    # keep_default_na=False: an empty cell (e.g. ran_out_daypart == "") must stay "" on read-back,
    # not become NaN -- gpc.engine.grid compares it to "" directly (`r == ""`).
    return pd.read_csv(path, keep_default_na=False)


def _load_public() -> dict[str, pd.DataFrame]:
    base = DATA_DIR / "base"
    return {p.stem: _read_csv(p) for p in base.glob("*.csv")}


def _load_observed() -> dict[str, pd.DataFrame]:
    obs = DATA_DIR / "observed"
    return {p.stem: _read_csv(p) for p in obs.glob("*.csv")}


def _obs_at(day: int, public: dict, observed: dict, campaigns: pd.DataFrame,
           campaign_keywords: pd.DataFrame) -> Observation:
    f = observed["daily_facts"]
    warm = f[f.day < WARMUP_DAYS]
    warmup_droas = float(warm.ad_revenue_inr.sum() / warm.spend_inr.sum()) if len(warm) else 1.0
    return Observation(run=1, day=day, public=public, campaigns=campaigns, campaign_keywords=campaign_keywords,
                      daily_facts=observed["daily_facts"][observed["daily_facts"].day < day],
                      campaign_daily=observed["campaign_daily"][observed["campaign_daily"].day < day],
                      sku_city_daily=observed["sku_city_daily"][observed["sku_city_daily"].day < day],
                      roas_floor=warmup_droas * 0.98, warmup_droas=warmup_droas)


def probe_e1_incrementality(public, observed) -> dict:
    full_day = observed["daily_facts"].day.max() + 1
    camp, ck = public["campaigns"], public["campaign_keywords"]
    obs = _obs_at(full_day, public, observed, camp, ck)
    df = fit_type_incrementality(obs, window=full_day)
    ordered = df.set_index("keyword_type").loc[["brand", "generic", "competition"]].iota
    return {"iota_by_type": df.to_dict("records"),
            "ordering_holds": bool(ordered.iloc[0] < ordered.iloc[1] < ordered.iloc[2])}


def probe_e2_siblings(public) -> dict:
    run01 = DATA_DIR / "runs" / "run_01"
    camp = _read_csv(run01 / "campaigns_before.csv")
    ck = _read_csv(run01 / "campaign_keywords_before.csv")
    observed = _load_observed()
    obs = _obs_at(WARMUP_DAYS, public, observed, camp, ck)
    grid = build_grid(obs)
    mk = markets(obs, grid)
    cm = contested_markets(mk)
    return {"n_cells": int(len(mk)), "n_contested_cells": int(mk.is_contested.sum()),
            "n_markets": int(mk.groupby(["city_id", "keyword_id"]).ngroups), "n_contested_markets": int(len(cm)),
            "wrong_leader_markets": int(cm.wrong_leader.sum()) if len(cm) else 0}


def probe_e3_runouts(observed) -> dict:
    cd = observed["campaign_daily"]
    warm = cd[cd.day < WARMUP_DAYS]
    per_camp = warm.groupby("campaign_id").ran_out.sum()
    chronic = per_camp[per_camp >= WARMUP_DAYS].index.tolist()
    return {"warmup_days": WARMUP_DAYS, "campaigns_ran_out_every_warmup_day": chronic,
            "n_chronic": len(chronic)}


def probe_e4_e5_shock_recall(public, observed) -> dict:
    """Runs `tools/shocks.detect_shocks` at each run's decision day and reports which (campaign,
    keyword)/(sku, city) cells got flagged — a recall check against the scenario's own injected
    shocks (dev.json: S2/HYD OSA dip at run 3, MUM K05/K06 price shock from run 4, K03/K04 demand
    shock from run 5), without assuming those shocks are what a *different* eval scenario will
    use."""
    params = load_params()
    camp = public["campaigns"]
    ck = public["campaign_keywords"]
    results = []
    for r in range(1, N_RUNS + 1):
        day = WARMUP_DAYS + (r - 1) * RUN_DAYS
        obs = _obs_at(day, public, observed, camp, ck)
        shocks = detect_shocks(obs, params)
        flagged = shocks[shocks.shock_reach | shocks.shock_cpm | shocks.shock_osa_drop]
        results.append({"run": r, "day": day, "n_flagged": int(len(flagged)),
                        "flagged_cells": flagged[["campaign_id", "keyword_id", "direction", "shock_cpm",
                                                  "shock_osa_drop"]].to_dict("records")})
    return {"per_run": results}


def probe_e9_headroom(observed) -> dict:
    f = observed["daily_facts"]
    warm = f[f.day < WARMUP_DAYS]
    post = f[f.day >= WARMUP_DAYS]
    warm_droas = float(warm.ad_revenue_inr.sum() / warm.spend_inr.sum())
    post_droas = float(post.ad_revenue_inr.sum() / post.spend_inr.sum())
    floor = warm_droas * 0.98
    return {"warmup_droas": round(warm_droas, 4), "post_warmup_droas": round(post_droas, 4),
            "roas_floor": round(floor, 4), "headroom_vs_floor": round(post_droas - floor, 4),
            "warmup_spend_per_day": round(warm.spend_inr.sum() / warm.day.nunique(), 2),
            "post_warmup_spend_per_day": round(post.spend_inr.sum() / post.day.nunique(), 2)}


def probe_e10_blocked_share() -> dict:
    total_proposed = total_blocked = total_rows = 0
    per_run = []
    for r in range(1, N_RUNS + 1):
        run_dir = DATA_DIR / "runs" / f"run_{r:02d}"
        proposed = pd.read_csv(run_dir / "proposed_actions.csv")
        log = pd.read_csv(run_dir / "guardrail_log.csv")
        blocked = (log.outcome == "blocked").sum()
        per_run.append({"run": r, "proposed": len(proposed), "blocked_rows": int(blocked)})
        total_proposed += len(proposed)
        total_blocked += blocked
    return {"per_run": per_run, "total_proposed": total_proposed, "total_blocked_rows": int(total_blocked),
            "blocked_share_of_proposed": round(total_blocked / total_proposed, 4) if total_proposed else 0.0}


def run_all() -> dict:
    public = _load_public()
    observed = _load_observed()
    return {
        "E1_incrementality": probe_e1_incrementality(public, observed),
        "E2_siblings": probe_e2_siblings(public),
        "E3_runouts": probe_e3_runouts(observed),
        "E4_E5_shock_recall": probe_e4_e5_shock_recall(public, observed),
        "E9_headroom": probe_e9_headroom(observed),
        "E10_blocked_share": probe_e10_blocked_share(),
    }


def main() -> None:
    if not (DATA_DIR / "base").exists():
        raise SystemExit(f"{DATA_DIR} has no base/ — run `make data` first to generate it")
    results = run_all()
    print(json.dumps(results, indent=2, default=str))
    out = Path(__file__).resolve().parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "probes.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out}/probes.json")


if __name__ == "__main__":
    main()
