"""Step 4 — the entity ledger: traversal decisions → actions on the levers that exist.

Levers per campaign: a CPM bid per keyword, one daily budget, a daypart schedule, pausing a keyword.
Sizing follows what spend can actually absorb:

* a bid raise ships only as far as the money behind it was funded (≥ 50% funded → the step is
  scaled to the funded share; less → dropped);
* a budget raise is sized as  rupees to deploy ÷ absorption  (absorption ≈ share of days the campaign
  runs out). A campaign that never runs out gets no raise: it would change nothing;
* nothing cuts a budget above what the campaign actually spends — that removes no spend.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..observation import Observation
from ..world import DAYPARTS
from .traversal import BID_CEIL, BID_FLOOR, TraversalResult

MIN_ABSORPTION = 0.30
MAX_BUDGET_STEP = 0.50


def build_actions(obs: Observation, tr: TraversalResult, pacing: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (actions, ledger_log). `ledger_log` records every decision that did NOT become an
    action and why, so the display can show the whole path."""
    pc = pacing.set_index("campaign_id")
    camp = obs.campaigns.set_index("campaign_id")
    funded = tr.demands.set_index("demand_id").funded_inr if len(tr.demands) else pd.Series(dtype=float)
    moves_by_demand = tr.transfers.groupby("demand_id").source_id.apply(list).to_dict() if len(tr.transfers) else {}
    moves_by_source = tr.transfers.groupby("source_id").demand_id.apply(list).to_dict() if len(tr.transfers) else {}
    actions, log = [], []
    extra_budget_need: dict[str, float] = {}

    def add(**a):
        a["action_id"] = f"r{obs.run:02d}-a{len(actions)+1:03d}"
        actions.append(a)

    for b in tr.bids.itertuples():
        if b.chosen_bid == b.live_bid:
            continue
        if b.chosen_bid > b.live_bid:
            did = f"raise:{b.campaign_id}:{b.keyword_id}"
            need = b.delta_spend
            got = float(funded.get(did, 0.0))
            frac = got / need if need > 0 else 0.0
            if frac < 0.5:
                log.append({"campaign_id": b.campaign_id, "keyword_id": b.keyword_id, "decision": "bid raise",
                            "outcome": "dropped", "detail": f"only {frac:.0%} funded by the transport step"})
                continue
            new_bid = b.live_bid + (b.chosen_bid - b.live_bid) * min(frac, 1.0)
            new_bid = float(np.clip(round(new_bid / 5) * 5, BID_FLOOR, BID_CEIL))
            if new_bid <= b.live_bid:
                continue
            add(campaign_id=b.campaign_id, keyword_id=b.keyword_id, action_type="increase_cpm",
                current_value=b.live_bid, new_value=new_bid, reason=b.reason,
                move_ids=";".join(f"{s}→{did}" for s in moves_by_demand.get(did, [])))
            if pc.loc[b.campaign_id, "budget_bound"]:
                extra_budget_need[b.campaign_id] = extra_budget_need.get(b.campaign_id, 0.0) + got * min(frac, 1.0)
        else:
            sid = f"cut:{b.campaign_id}:{b.keyword_id}"
            add(campaign_id=b.campaign_id, keyword_id=b.keyword_id, action_type="reduce_cpm",
                current_value=b.live_bid, new_value=b.chosen_bid, reason=b.reason,
                move_ids=";".join(f"{sid}→{d}" for d in moves_by_source.get(sid, [])))

    # budget raises for budget-bound receivers (+ the budget behind their funded bid raises)
    budget_need: dict[str, float] = dict(extra_budget_need)
    for d in tr.demands[tr.demands.kind == "budget_bound"].itertuples() if len(tr.demands) else []:
        if d.funded_inr > 1:
            budget_need[d.campaign_id] = budget_need.get(d.campaign_id, 0.0) + d.funded_inr
        else:
            log.append({"campaign_id": d.campaign_id, "keyword_id": "", "decision": "budget raise",
                        "outcome": "dropped", "detail": "budget-bound and clearing goal, but no source passed the transfer test"})
    for cid, need in budget_need.items():
        p = pc.loc[cid]
        absorb = max(float(p.absorption), MIN_ABSORPTION)
        cur = float(camp.loc[cid, "daily_budget_inr"])
        new = min(cur + need / absorb, cur * (1 + MAX_BUDGET_STEP))
        new = round(new / 50) * 50
        if new <= cur:
            continue
        did = f"budget:{cid}"
        add(campaign_id=cid, keyword_id="", action_type="increase_budget", current_value=cur, new_value=float(new),
            reason=f"budget-bound (ran out {int(p.ran_out_days)}/7 days); deploy ₹{need:,.0f}/day ÷ absorption {absorb:.2f}",
            move_ids=";".join(f"{s}→{did}" for s in moves_by_demand.get(did, [])))

    for d in tr.dayparts.itertuples() if len(tr.dayparts) else []:
        cur = ",".join(dp for dp in DAYPARTS if camp.loc[d.campaign_id, f"on_{dp}"])
        new = ",".join(dp for dp in cur.split(",") if dp != d.daypart_off)
        add(campaign_id=d.campaign_id, keyword_id="", action_type="set_dayparts", current_value=cur, new_value=new,
            reason=f"turn off {d.daypart_off}: {d.reason}", move_ids="")

    cols = ["action_id", "campaign_id", "keyword_id", "action_type", "current_value", "new_value", "reason", "move_ids"]
    out = pd.DataFrame(actions, columns=cols)
    if len(out):
        num = pd.to_numeric(out.current_value, errors="coerce")
        new = pd.to_numeric(out.new_value, errors="coerce")
        out["change_pct"] = ((new / num - 1) * 100).round(1)
    else:
        out["change_pct"] = []
    return out, pd.DataFrame(log, columns=["campaign_id", "keyword_id", "decision", "outcome", "detail"])
