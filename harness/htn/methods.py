"""Tools-only (L0) methods. Each returns a candidate-actions DataFrame (campaign_id, keyword_id,
action_type, new_value, reason) — not yet sized, pre-checked or guardrailed; `harness/policy.py`
assembles these, prices the raises against the headroom allowance (`tools.sizing`), drops
anything `tools.precheck` would flag, and lets `gpc.guardrails` have the final, authoritative say.

SG2 M_Reprice     raise a bid on a CLEARS, non-held cell toward the engine's own chosen option
                  (`gpc.engine.traversal.choose_bids`), the lever E9's unused headroom should fund.
SG3 M_Sibling     the sibling fix (handoff correction): never raise a follower a sibling already
                  holds slot 1 on; the follower's bid buys nothing there, and G3 would block the
                  raise anyway once the follower *becomes* the one holding slot 1 at 80%+. This
                  method only computes the hold-set; M_Reprice consults it.
SG4 M_Budget      raise the budget of a campaign that ran out >= RUNOUT_MIN_DAYS of the last 7 and
                  whose cells clear goal on spend-weighted ROAS (E3's 6 chronically-starved
                  campaigns) — the same gate G5/G7 enforce, computed here first so sizing doesn't
                  waste allowance on a raise that would be blocked anyway.
M_Base            everything that misses goal, competitor keywords included: defer to the engine's
                  own ladder-paced cut (`choose_bids`) — that logic is already tested in
                  `tests/test_sandbox.py` and is not where the identified gaps are.

**Removed 2026-10-02, not just renamed**: an earlier `M_CompetitorCut` special-cased competitor
MISSES cells to cut straight to the best-dROAS option, skipping the patience ladder entirely, on
the claim that competitor keywords have "~0 incrementality" (E1) so a fast cut costs ~0 offtake.
That claim inverted what E1 actually says: β ≈ 0 for competitor keywords means ι ≈ 1 — competitor
keywords are the **most** incremental lever in the portfolio (brand ι ≈ 0.12-0.20 is the low end;
customers searching a competitor's brand name were not about to buy Aurel organically). Cutting
that spend fast is the expensive move, not the cheap one. The handoff note's "faster competitor
cuts" lever was reading a different number — competitor's poor *direct* ROAS (goal_droas ≈ 1.6
vs. brand's 9.0, per `gpc.world._plan`'s `goal_base`) — not incrementality; direct ROAS and
incrementality are different axes and a low dROAS keyword can still be highly incremental. Caught
by an independent review session reading `harness_eval/probes.py`'s own E1 output, not by a test
in this repo — the existing tests checked that the (wrong) special-case behaved consistently with
itself, which a wrong premise will happily do. Competitor MISSES cells now take the same
ladder-paced path as everything else; `iota`-weighted sizing on the *raise* side
(`m_reprice_raises`/`tools/sizing.py`) already correctly favours competitor keywords when they
clear goal, since that path reads the real `iota_lookup` value rather than a hand-written claim.
"""

from __future__ import annotations

import pandas as pd

from gpc.observation import Observation

from ..config import Params
from ..tools.features import Diagnostics
from ..tools.siblings import followers_to_hold, markets


def m_sibling_holds(obs: Observation, diag: Diagnostics, params: Params) -> tuple[set, pd.DataFrame]:
    mk = markets(obs, diag.grid)
    return followers_to_hold(mk, params.sibling_leader_min_slot1_share), mk


def m_reprice_raises(obs: Observation, diag: Diagnostics, hold: set, iota: dict) -> pd.DataFrame:
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    camp = obs.campaigns.set_index("campaign_id")
    v = diag.verdicts.set_index(["campaign_id", "keyword_id"])
    rows = []
    for b in diag.bids.itertuples():
        key = (b.campaign_id, b.keyword_id)
        if key in hold or b.verdict != "CLEARS" or b.chosen_bid <= b.live_bid:
            continue
        sku = camp.loc[b.campaign_id, "sku_id"]
        t = kt.get(b.keyword_id, "generic")
        io = iota.get((sku, t), 0.5)
        rows.append({"campaign_id": b.campaign_id, "keyword_id": b.keyword_id, "action_type": "increase_cpm",
                     "current_value": b.live_bid, "new_value": b.chosen_bid, "iota": io,
                     "reason": f"M_Reprice: {b.reason}"})
    return pd.DataFrame(rows, columns=["campaign_id", "keyword_id", "action_type", "current_value", "new_value",
                                       "iota", "reason"])


def m_budget_raises(obs: Observation, diag: Diagnostics, params: Params, iota: dict) -> pd.DataFrame:
    camp = obs.campaigns.set_index("campaign_id")
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    rows = []
    for p in diag.pacing.itertuples():
        if int(p.ran_out_days) < params.budget_runout_min_days:
            continue
        cv = diag.verdicts[diag.verdicts.campaign_id == p.campaign_id]
        sw = cv.spend_7d_avg.sum()
        if sw <= 0:
            continue
        w = cv.spend_7d_avg / sw
        if float((cv.droas_shrunk.fillna(0) * w).sum()) < 0.9 * float((cv.goal_droas * w).sum()):
            continue
        sku = camp.loc[p.campaign_id, "sku_id"]
        io = float((w * cv.keyword_id.map(lambda k: iota.get((sku, kt.get(k, "generic")), 0.5))).sum())
        cur = float(p.daily_budget_inr)
        rows.append({"campaign_id": p.campaign_id, "keyword_id": "", "action_type": "increase_budget",
                     "current_value": cur, "new_value": cur * 1.5, "iota": io,
                     "reason": f"M_Budget: ran out {int(p.ran_out_days)}/7 days, clears goal on spend-weighted ROAS"})
    return pd.DataFrame(rows, columns=["campaign_id", "keyword_id", "action_type", "current_value", "new_value",
                                       "iota", "reason"])


def m_base_cuts(obs: Observation, diag: Diagnostics) -> pd.DataFrame:
    """Every MISSES cell's cut, ladder-paced by the engine's own `choose_bids` — competitor
    keywords included (see the module docstring for why they no longer get a special fast-cut
    path)."""
    rows = []
    for b in diag.bids.itertuples():
        if b.verdict != "MISSES" or b.chosen_bid >= b.live_bid:
            continue
        rows.append({"campaign_id": b.campaign_id, "keyword_id": b.keyword_id, "action_type": "reduce_cpm",
                     "current_value": b.live_bid, "new_value": b.chosen_bid, "reason": f"M_Base: {b.reason}"})
    return pd.DataFrame(rows, columns=["campaign_id", "keyword_id", "action_type", "current_value", "new_value",
                                       "reason"])
