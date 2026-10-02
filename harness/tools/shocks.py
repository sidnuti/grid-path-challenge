"""Shock detection (E4/E5/E6): z-scores of slot-1-equivalent reach, CPM and on-shelf availability,
comparing the last `recent_days` against the `lookback_days` before that. Truncated (run-out) days
are excluded from both windows — a day the campaign ran out of budget understates reach the same
way `gpc.engine.grid` already treats truncated days as the weaker evidence source.

E5's confounding ("MUM K05/K06 reach rises then falls, but the baseline cut its own bids in that
window") can't be told apart from the data alone without knowing what the *policy itself* did —
this harness does know that, since `harness/policy.py` is the only thing proposing its own bid
changes. `flag_own_action_confound` takes the policy's own action log (a plain
`{(campaign_id, keyword_id): [day, ...]}` of days it changed that bid) and marks any shock whose
window overlaps one of those days, so a method can discount or ignore a "shock" that is really
just the harness watching its own last move land.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gpc.observation import Observation
from gpc.world import SLOT_VIEW_REL

from ..config import Params


def _slot_1_eq_daily(obs: Observation, window: int) -> pd.DataFrame:
    """Daily slot-1-equivalent impressions, spend-weighted CPM, per (campaign_id, keyword_id),
    on days that were not run-out-truncated for that campaign."""
    f = obs.window("daily_facts", window)
    cd = obs.window("campaign_daily", window)
    if not len(f):
        return pd.DataFrame(columns=["campaign_id", "keyword_id", "day", "impr_s1eq", "cpm_s1eq"])
    full_days = set(cd[~cd.ran_out][["campaign_id", "day"]].itertuples(index=False, name=None)) \
        if "ran_out" in cd.columns else set(zip(cd.campaign_id, cd.day))
    f = f.copy()
    f["is_full"] = list(zip(f.campaign_id, f.day))
    f = f[f.is_full.isin(full_days)]
    if not len(f):
        return pd.DataFrame(columns=["campaign_id", "keyword_id", "day", "impr_s1eq", "cpm_s1eq"])
    f["impr_s1eq"] = f.impressions / f.slot.map(SLOT_VIEW_REL)
    daily = f.groupby(["campaign_id", "keyword_id", "day"]).agg(
        impr_s1eq=("impr_s1eq", "sum"), spend=("spend_inr", "sum"), impr=("impressions", "sum"))
    daily["cpm_s1eq"] = daily.spend / daily.impr.replace(0, np.nan) * 1000
    return daily.reset_index()


def _zscore(recent: pd.Series, baseline: pd.Series, min_abs_diff: float = 0.0) -> float:
    if not len(baseline) or not len(recent):
        return 0.0
    diff = recent.mean() - baseline.mean()
    if baseline.std(ddof=0) < 1e-6:
        # a near-constant baseline: only call it a shock if the move is big enough to matter,
        # not any float-noise tick against a ~0 denominator
        if abs(diff) <= max(min_abs_diff, 1e-6):
            return 0.0
        return float(np.sign(diff)) * 5.0
    return float(diff / baseline.std(ddof=0))


def detect_shocks(obs: Observation, params: Params,
                  own_action_days: dict[tuple[str, str], list[int]] | None = None) -> pd.DataFrame:
    """One row per (campaign_id, keyword_id): z_reach, z_cpm, shock_reach, shock_cpm (bool),
    direction ('surge'/'drop'/'none' for reach), and `own_action_confound` (bool)."""
    own_action_days = own_action_days or {}
    window = params.shock_recent_days + params.shock_lookback_days
    daily = _slot_1_eq_daily(obs, window)
    sku_city = obs.campaigns.set_index("campaign_id")[["sku_id", "city_id"]]
    osa = obs.window("sku_city_daily", window)[["sku_id", "city_id", "day", "osa"]]

    cutoff = obs.day - params.shock_recent_days
    rows = []
    for key, g in daily.groupby(["campaign_id", "keyword_id"]):
        recent = g[g.day >= cutoff]
        baseline = g[g.day < cutoff]
        z_reach = _zscore(recent.impr_s1eq, baseline.impr_s1eq,
                         min_abs_diff=0.05 * baseline.impr_s1eq.mean() if len(baseline) else 0.0)
        z_cpm = _zscore(recent.cpm_s1eq.dropna(), baseline.cpm_s1eq.dropna(),
                       min_abs_diff=0.05 * baseline.cpm_s1eq.dropna().mean() if len(baseline) else 0.0)
        cid, kid = key
        sku, city = (sku_city.loc[cid, "sku_id"], sku_city.loc[cid, "city_id"]) if cid in sku_city.index else (None, None)
        o = osa[(osa.sku_id == sku) & (osa.city_id == city)] if sku is not None else osa.iloc[0:0]
        o_recent = o[o.day >= cutoff].osa
        o_baseline = o[o.day < cutoff].osa
        z_osa = _zscore(o_recent, o_baseline, min_abs_diff=0.05)

        days_in_window = set(range(cutoff - params.shock_lookback_days, obs.day))
        confound = bool(set(own_action_days.get(key, [])) & days_in_window)

        rows.append({
            "campaign_id": cid, "keyword_id": kid,
            "z_reach": round(z_reach, 3), "z_cpm": round(z_cpm, 3), "z_osa": round(z_osa, 3),
            "shock_reach": abs(z_reach) >= params.shock_z_reach,
            "shock_cpm": abs(z_cpm) >= params.shock_z_cpm,
            "shock_osa_drop": z_osa <= -params.shock_z_osa,
            "direction": "surge" if z_reach >= params.shock_z_reach else ("drop" if z_reach <= -params.shock_z_reach else "none"),
            "own_action_confound": confound,
        })
    cols = ["campaign_id", "keyword_id", "z_reach", "z_cpm", "z_osa", "shock_reach", "shock_cpm",
            "shock_osa_drop", "direction", "own_action_confound"]
    return pd.DataFrame(rows, columns=cols)
