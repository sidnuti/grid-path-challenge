"""L1/L2-depth methods: the ones that call a leaf (`harness/leaves/run.py`). Each is a thin layer
on top of an L0 mechanical read — a leaf here narrows or vetoes an existing mechanical candidate,
it never invents a new lever. Nothing here changes behaviour when `llm` is `None`
(`LLM_MODE=off`/`LLM_PROVIDER=none`): every function here degrades to its L0 input unchanged,
since `leaf()` itself returns the caller's default in that case. That is what keeps
`HTNHarness(llm=None)` identical to `HTNToolsOnly` (M1's gate), and what the fail-soft S9 scenario
tests.

SG3 sibling tie-break (L3)   only called on a near-tie (top two leader_score within 10%) — the
                             mechanical score should decide a clear case on its own.
SG5 M_Shock (L2)             a cell flagged `shock_reach` (surge) and not `own_action_confound`
                             that *isn't* already a mechanical raise (MISSES/THIN under the stale
                             verdict a surge would invalidate) gets a confirm-and-raise path,
                             instead of waiting a run for the verdict to catch up (E4's "shock
                             detection lead time").
SG2 bid-size trust (L1)      dampens/extends a tier-B CLEARS raise's size; tier-A raises (strong
                             evidence) and tier-C (held entirely, mechanically) never reach this.
SG6 M_Explore (L4)           up to `params.explore_max_thin_cells` THIN cells get a capped,
                             leaf-gated small probe — the only way a THIN cell is ever touched.
L6 review                    L2-depth only: a veto-only pass over this run's large raises.

**Fixed 2026-10-03** (an independent review, reading the actual prompt text sent to the model,
caught this — not a test, since nothing here asserted on prompt *content*): `adjust_raise_sizes`
(L1) was rendering `{keyword_type}`, `{goal_droas}` and `{orders_28d}` as hardcoded blanks/zeros
(`""`, `""`, and a `.get("orders_28d", 0)` on an object — `diag.bids` — that never had that
column, so it was always the `0` default) even though all three are cheaply available from data
already in scope (`obs.public["keywords"]`, `diag.verdicts`). The prompt also asked for
`{z_reach}`/`{own_action_confound}`, hardcoded to `0.0`/`False`, because real shock data was never
threaded into this call at all — removed from the prompt rather than faked, since L1 genuinely
doesn't have that context here (shock attribution is L2's job). The real fields are now looked
up properly; the fake ones are gone. Because the prompt text changed, `L1_value.v1.md` became
`L1_value.v2.md` (a real cache recorded against v1's wording must not be silently served under an
unchanged version tag — see `harness/llm/replay.py`'s cache-key fix the same day, same principle).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from gpc.observation import Observation

from ..config import Params
from ..leaves.render import render
from ..leaves.run import leaf
from ..leaves.schemas import L1Value, L2Shock, L3Sibling, L4Explore, L6Review
from ..tools.features import Diagnostics

# Per-leaf prompt version -- bump only the leaf whose prompt text actually changed, not a single
# shared constant, so editing one leaf's wording doesn't invalidate every other leaf's cache too.
PROMPT_VERSIONS = {"L1_value": "2", "L2_shock": "1", "L3_sibling": "1", "L4_explore": "1", "L6_review": "1"}


def sibling_tiebreak(obs: Observation, mk: pd.DataFrame, llm, replicate: int = 0,
                     metas: Optional[list] = None) -> pd.DataFrame:
    """Re-checks each contested market's leader; on a near-tie (top two leader_score within 10%
    of each other) asks L3Sibling, else keeps the mechanical pick untouched."""
    if not len(mk) or llm is None:
        return mk
    mk = mk.copy()
    for (city, kid), g in mk[mk.is_contested].groupby(["city_id", "keyword_id"]):
        top2 = g.sort_values("leader_score", ascending=False).head(2)
        if len(top2) < 2 or top2.leader_score.iloc[0] <= 0:
            continue
        if (top2.leader_score.iloc[0] - top2.leader_score.iloc[1]) / top2.leader_score.iloc[0] >= 0.10:
            continue  # not a near-tie; trust the mechanical score
        default = L3Sibling(leader_campaign_id=str(top2.campaign_id.iloc[0]), confidence=0.0)
        table = "\n".join(f"- {r.campaign_id}, {r.sku_id}, {r.leader_score:.4f}, {r.slot1_share_7d:.2f}"
                          for r in g.itertuples())
        system, user = render("L3_sibling", PROMPT_VERSIONS["L3_sibling"],
                              {"city_id": city, "keyword_id": kid, "candidates_table": table})
        result, meta = leaf(llm, "L3_sibling", system, user, L3Sibling, default,
                           known_ids=set(g.campaign_id), id_field="leader_campaign_id", replicate=replicate)
        if metas is not None:
            metas.append(meta)
        mk.loc[g.index, "is_leader"] = mk.loc[g.index, "campaign_id"] == result.leader_campaign_id
    return mk


def shock_raises(obs: Observation, diag: Diagnostics, shocks: pd.DataFrame, llm, iota: dict,
                 replicate: int = 0, metas: Optional[list] = None) -> pd.DataFrame:
    """Cells with a mechanical surge flag, confirmed by L2Shock, that are not already a CLEARS
    raise (M_Reprice already handles those) — a confirmed surge should not wait for next run's
    verdict to catch up."""
    cols = ["campaign_id", "keyword_id", "action_type", "current_value", "new_value", "iota", "reason"]
    if not len(shocks):
        return pd.DataFrame(columns=cols)
    bids = diag.bids.set_index(["campaign_id", "keyword_id"])
    camp = obs.campaigns.set_index("campaign_id")
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    rows = []
    for s in shocks[(shocks.shock_reach) & (shocks.direction == "surge") & (~shocks.own_action_confound)].itertuples():
        key = (s.campaign_id, s.keyword_id)
        if key not in bids.index:
            continue
        b = bids.loc[key]
        if b.verdict == "CLEARS" and b.chosen_bid > b.live_bid:
            continue  # M_Reprice already raises this cell
        opts = diag.options[(diag.options.campaign_id == s.campaign_id) & (diag.options.keyword_id == s.keyword_id)
                            & (diag.options.bid > b.live_bid) & (diag.options.pred_droas.notna())]
        if not len(opts):
            continue
        target = float(opts.sort_values("pred_droas", ascending=False).bid.iloc[0])
        if target <= b.live_bid:
            continue
        default = L2Shock(is_shock=False, magnitude=0.0)
        system, user = render("L2_shock", PROMPT_VERSIONS["L2_shock"], {
            "campaign_id": s.campaign_id, "keyword_id": s.keyword_id, "z_reach": s.z_reach, "z_cpm": s.z_cpm,
            "z_osa": s.z_osa, "shock_reach": s.shock_reach, "shock_cpm": s.shock_cpm,
            "shock_osa_drop": s.shock_osa_drop, "own_action_confound": s.own_action_confound,
            "direction": s.direction})
        result, meta = leaf(llm, "L2_shock", system, user, L2Shock, default, replicate=replicate)
        if metas is not None:
            metas.append(meta)
        if result.is_shock and result.direction != "drop" and result.confidence >= 0.5:
            sku = camp.loc[s.campaign_id, "sku_id"]
            io = iota.get((sku, kt.get(s.keyword_id, "generic")), 0.5)
            rows.append({"campaign_id": s.campaign_id, "keyword_id": s.keyword_id, "action_type": "increase_cpm",
                        "current_value": b.live_bid, "new_value": target, "iota": io,
                        "reason": f"M_Shock: confirmed surge (z_reach={s.z_reach}), raising ahead of next verdict"})
    return pd.DataFrame(rows, columns=cols)


def adjust_raise_sizes(obs: Observation, diag: Diagnostics, raises: pd.DataFrame, llm,
                       replicate: int = 0, metas: Optional[list] = None) -> pd.DataFrame:
    """Dampens/extends tier-B CLEARS raises via L1Value. Tier-A raises pass through untouched
    (strong evidence, no need to second-guess); the sizing/precheck steps downstream see the
    adjusted new_value either way."""
    if not len(raises) or llm is None:
        return raises
    bids = diag.bids.set_index(["campaign_id", "keyword_id"])
    verdicts = diag.verdicts.set_index(["campaign_id", "keyword_id"])
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    out = raises.copy()
    for idx, r in raises.iterrows():
        if r.action_type != "increase_cpm":
            continue
        key = (r.campaign_id, r.keyword_id)
        if key not in bids.index:
            continue
        b = bids.loc[key]
        g = diag.grid[(diag.grid.campaign_id == r.campaign_id) & (diag.grid.keyword_id == r.keyword_id)]
        tier = g.tier.iloc[0] if len(g) else "C"
        if tier != "B":
            continue
        v = verdicts.loc[key] if key in verdicts.index else None
        orders_28d = float(v.orders_28d) if v is not None else 0.0
        goal_droas = float(v.goal_droas) if v is not None else 0.0
        default = L1Value(bid_multiplier=1.0, confidence=0.0)
        system, user = render("L1_value", PROMPT_VERSIONS["L1_value"], {
            "campaign_id": r.campaign_id, "keyword_id": r.keyword_id, "keyword_type": kt.get(r.keyword_id, ""),
            "tier": tier, "verdict": b.verdict, "orders_28d": orders_28d,
            "live_bid": b.live_bid, "proposed_bid": r.new_value, "step_pct": int(b.step_pct),
            "droas_shrunk": g.droas.mean() if len(g) else 0.0, "goal_droas": goal_droas})
        result, meta = leaf(llm, "L1_value", system, user, L1Value, default, replicate=replicate)
        if metas is not None:
            metas.append(meta)
        new_raise = r.current_value + (r.new_value - r.current_value) * result.bid_multiplier
        out.loc[idx, "new_value"] = max(new_raise, r.current_value)
    return out


def explore_candidates(obs: Observation, diag: Diagnostics, params: Params, llm, replicate: int = 0,
                       metas: Optional[list] = None) -> pd.DataFrame:
    """**Fixed 2026-10-03** (an independent review caught this): `n_explored` — the loop's only
    break condition — used to increment only on an *accepted* explore, so `params.
    explore_max_thin_cells` capped how many cells could be shipped, not how many THIN cells (up
    to all 22-27 of them, per E8) got an LLM call made about them. A run where the model rejected
    every cell made one call per THIN cell with no cap at all. `n_attempted` now increments on
    every call regardless of outcome and is what the loop actually breaks on — `max_thin_cells` is
    a cap on LLM calls, which is the number this harness's own cost budget cares about."""
    cols = ["campaign_id", "keyword_id", "action_type", "current_value", "new_value", "reason"]
    if not params.explore_enabled or llm is None or params.explore_max_thin_cells <= 0:
        return pd.DataFrame(columns=cols)
    camp = obs.campaigns.set_index("campaign_id")
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    rel = obs.public["keyword_sku"].set_index(["sku_id", "keyword_id"]).relevance
    verdicts = diag.verdicts.set_index(["campaign_id", "keyword_id"])
    f14 = obs.window("daily_facts", 14)
    thin = diag.bids[diag.bids.verdict == "THIN"]
    rows, n_attempted = [], 0
    for b in thin.itertuples():
        if n_attempted >= params.explore_max_thin_cells:
            break
        n_attempted += 1
        sku = camp.loc[b.campaign_id, "sku_id"]
        key = (b.campaign_id, b.keyword_id)
        orders_28d = float(verdicts.loc[key, "orders_28d"]) if key in verdicts.index else 0.0
        spend_14d = float(f14[(f14.campaign_id == b.campaign_id) & (f14.keyword_id == b.keyword_id)]
                         .spend_inr.sum())
        default = L4Explore(explore=False)
        system, user = render("L4_explore", PROMPT_VERSIONS["L4_explore"], {
            "campaign_id": b.campaign_id, "keyword_id": b.keyword_id, "keyword_type": kt.get(b.keyword_id, ""),
            "orders_28d": orders_28d, "spend_14d": spend_14d, "live_bid": b.live_bid,
            "relevance": rel.get((sku, b.keyword_id), 0.0), "n_already_exploring": n_attempted - 1,
            "max_thin_cells": params.explore_max_thin_cells})
        result, meta = leaf(llm, "L4_explore", system, user, L4Explore, default, replicate=replicate)
        if metas is not None:
            metas.append(meta)
        if not result.explore:
            continue
        cap = min(result.max_spend_inr_day, params.explore_spend_cap_inr_day)
        opts = diag.options[(diag.options.campaign_id == b.campaign_id) & (diag.options.keyword_id == b.keyword_id)
                            & (diag.options.bid > b.live_bid) & (diag.options.pred_spend <= cap)]
        if not len(opts) or cap <= 0:
            continue
        target = float(opts.sort_values("bid").bid.iloc[-1])
        rows.append({"campaign_id": b.campaign_id, "keyword_id": b.keyword_id, "action_type": "increase_cpm",
                    "current_value": b.live_bid, "new_value": target,
                    "reason": f"M_Explore: capped probe of a THIN cell (<= INR {cap:.0f}/day)"})
    return pd.DataFrame(rows, columns=cols)


def review_veto(obs: Observation, headroom, raises: pd.DataFrame, params: Params, llm,
                replicate: int = 0, metas: Optional[list] = None) -> pd.DataFrame:
    """L2-depth only. Drops every raise above `llm_review_threshold_inr` of projected delta_spend
    if L6Review vetoes; leaves everything else (including all cuts) untouched regardless.

    `llm_review_threshold_inr` default **lowered 2026-10-03** (2000 -> 500 inr/day): with the
    headroom allowance fix the same day (`tools/headroom.py`'s minimum floor is 300 inr/day, and
    even a generous late-run allowance is typically a few thousand, not tens of thousands), a
    2000 inr/day single-candidate threshold meant this review almost never had anything to look
    at — an independent review flagged "review veto never triggers" as a real gap. 500 is still a
    judgment call, not a derived number — the honest target is "large relative to what this run's
    sizing actually produces", which varies by run and world; a threshold expressed as a fraction
    of the run's own allowance (rather than an absolute rupee figure) would track that better and
    is flagged as a cleaner fix than another hand-picked constant, not yet built."""
    if params.depth != "L2" or llm is None or not len(raises) or "pred_delta_spend" not in raises.columns:
        return raises
    large = raises[raises.pred_delta_spend >= params.llm_review_threshold_inr]
    if not len(large):
        return raises
    table = "\n".join(f"- {r.campaign_id}/{r.keyword_id} {r.action_type}: INR {r.pred_delta_spend:.0f}/day, {r.reason}"
                      for r in large.itertuples())
    default = L6Review(veto=False)
    system, user = render("L6_review", PROMPT_VERSIONS["L6_review"], {
        "run": obs.run, "allowance_used": round(large.pred_delta_spend.sum(), 2),
        "allowance_total": headroom.allowance_inr_day, "review_threshold": params.llm_review_threshold_inr,
        "large_actions_table": table})
    result, meta = leaf(llm, "L6_review", system, user, L6Review, default, replicate=replicate)
    if metas is not None:
        metas.append(meta)
    if result.veto:
        return raises.drop(large.index)
    return raises
