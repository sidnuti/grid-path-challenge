"""Pre-checks: predict which of a candidate's guardrail outcomes (G0/G3/G4/G5/G7) would block it,
*before* it is proposed — so the harness does not spend LLM/compute effort sizing a move the
guardrail layer would reject anyway, and so `actions_proposed` stays close to `actions_shipped`
(E10: the baseline's own 15%+ block rate is a target to beat, not to match).

Mirrors `gpc.guardrails` using its own exported constants (`TOP_SLOT_SHARE`, `OSA_MIN`,
`RUNOUT_MIN_DAYS`) so the two never drift apart silently; `tests/harness/test_tools.py::
test_precheck_matches_guardrails` property-tests this against `apply_guardrails` directly on
randomized action sets, which is the test that actually guarantees it, not this docstring.
"""

from __future__ import annotations

import pandas as pd

from gpc.guardrails import OSA_MIN, RUNOUT_MIN_DAYS, TOP_SLOT_SHARE
from gpc.observation import Observation


def precheck(obs: Observation, verdicts: pd.DataFrame, pacing: pd.DataFrame, action: dict) -> tuple[bool, str]:
    """Returns (would_pass, reason). `action` needs campaign_id, keyword_id ('' if none),
    action_type, new_value."""
    at, cid, kid = action["action_type"], action["campaign_id"], action.get("keyword_id", "")
    camp = obs.campaigns.set_index("campaign_id")
    if cid not in camp.index:
        return False, "G0: unknown campaign"
    sku, city = camp.loc[cid, "sku_id"], camp.loc[cid, "city_id"]

    if at == "increase_cpm":
        f7 = obs.window("daily_facts", 7)
        key = (f7.campaign_id == cid) & (f7.keyword_id == kid)
        i = float(f7.loc[key, "impressions"].sum())
        s1 = float(f7.loc[key & (f7.slot == 1), "impressions"].sum())
        if i > 0 and s1 / i >= TOP_SLOT_SHARE:
            return False, "G3: already at slot 1 on >= 80% of impressions"
        v = verdicts.set_index(["campaign_id", "keyword_id"])
        if (cid, kid) in v.index and v.loc[(cid, kid), "verdict"] == "MISSES":
            return False, "G7: cell misses goal"

    if at in ("increase_cpm", "increase_budget"):
        osa3 = obs.window("sku_city_daily", 3).groupby(["sku_id", "city_id"]).osa.mean()
        if float(osa3.get((sku, city), 1.0)) < OSA_MIN:
            return False, "G4: availability under 60% over 3 days"

    if at == "increase_budget":
        p = pacing.set_index("campaign_id")
        if cid not in p.index or int(p.loc[cid, "ran_out_days"]) < RUNOUT_MIN_DAYS:
            return False, "G5: ran out on fewer than 2 of the last 7 days"
        v = verdicts[verdicts.campaign_id == cid]
        sw = v.spend_7d_avg.sum()
        if sw > 0:
            w = v.spend_7d_avg / sw
            if float((v.droas_shrunk.fillna(0) * w).sum()) < 0.9 * float((v.goal_droas * w).sum()):
                return False, "G7: campaign's spend-weighted ROAS under 90% of goal"

    return True, ""


def filter_precheck(obs: Observation, verdicts: pd.DataFrame, pacing: pd.DataFrame,
                    candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Splits candidates into (kept, dropped-with-reason)."""
    if not len(candidates):
        return candidates, candidates.assign(precheck_reason=[])
    ok, reasons = [], []
    for a in candidates.to_dict("records"):
        passed, reason = precheck(obs, verdicts, pacing, a)
        ok.append(passed)
        reasons.append(reason)
    candidates = candidates.assign(_ok=ok, _reason=reasons)
    kept = candidates[candidates._ok].drop(columns=["_ok", "_reason"])
    dropped = candidates[~candidates._ok].rename(columns={"_reason": "precheck_reason"}).drop(columns=["_ok"])
    return kept, dropped
