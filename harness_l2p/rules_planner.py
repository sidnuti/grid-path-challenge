"""Deterministic intent planner: the EDA §10.4 stance table written as rules over the brief.

This is the LLM ablation for L2′. Same brief in, same intent schema out, same compiler, no model.
If the LLM planner cannot beat this, the LLM is not what makes the decisions better.

    role fund       raise_budget (medium)
    role hold       hold the campaign (no raises; capped but not efficient)
    role scale      raise_bid on its best cells: CLEARS, slot-1 share < 80%, incremental marginal ROAS of a
                    +20% bid above the portfolio floor (capped at MAX_SCALE_CELLS per run)
    role trim       cut_bid (small) on the SKU's least incremental keyword type in that campaign
    market          lead_market for the best incremental sibling where another sibling holds slot 1 and the
                    gap is large (≥ 30%), at most MAX_LEADS per run
    anomaly         a reach surge not caused by our own change: raise_bid (small) on that cell
    OSA dip         hold the campaign while 3-day availability is under 75%
"""

from __future__ import annotations

from .brief import Brief
from .intents import Intent, IntentPlan, Scope

MAX_SCALE_CELLS = 8
MAX_LEADS = 4


def rules_plan(brief: Brief) -> IntentPlan:
    intents: list[Intent] = []
    n = 0

    def add(verb, scope, size="medium", conf=0.5, refs=(), note="", **kw):
        nonlocal n
        n += 1
        intents.append(Intent(id=f"r{n}", verb=verb, scope=Scope(**scope), size=size, confidence=conf,
                              evidence_refs=list(refs), expected_effect=note, **kw))

    floor = brief.headroom.roas_floor
    roles = brief.roles
    dip = set(roles[roles.osa_3d < 0.75].campaign_id)
    for r in roles.itertuples():
        if r.campaign_id in dip:
            add("hold", {"campaign_id": r.campaign_id}, conf=0.9, refs=[r.ref], note="availability dip: no raises")
        elif r.role == "fund":
            add("raise_budget", {"campaign_id": r.campaign_id}, "medium", 0.8, [r.ref], "capped and efficient: fund")
        elif r.role == "hold":
            add("hold", {"campaign_id": r.campaign_id}, conf=0.6, refs=[r.ref], note="capped but weak: no raises")
        elif r.role == "trim":
            cells = brief.cells[brief.cells.campaign_id == r.campaign_id]
            if len(cells):
                worst = cells.groupby("keyword_type").iota.mean().idxmin()
                add("cut_bid", {"campaign_id": r.campaign_id, "keyword_type": worst}, "small", 0.4, [r.ref],
                    f"least incremental keyword type ({worst})")

    c = brief.cells
    scale_camps = set(roles[(roles.role == "scale") & ~roles.campaign_id.isin(dip)].campaign_id)
    cand = c[c.campaign_id.isin(scale_camps) & (c.verdict == "CLEARS") & (c.slot1_share < 0.8)].copy()
    cand["imroas"] = cand.mroas_up20 * cand.iota
    cand = cand[cand.imroas > floor].sort_values("imroas", ascending=False).head(MAX_SCALE_CELLS)
    for x in cand.itertuples():
        add("raise_bid", {"campaign_id": x.campaign_id, "keyword_id": x.keyword_id}, "medium", 0.6, [x.ref],
            f"incremental marginal ROAS {x.imroas:.1f} above floor")

    leads = brief.markets[brief.markets.wrong_holder & (brief.markets.gap >= 0.3)].sort_values("gap", ascending=False).head(MAX_LEADS)
    for m in leads.itertuples():
        if True:
            add("lead_market", {"sku_id": m.best_sku, "city_id": m.city_id, "keyword_id": m.keyword_id}, "medium",
                0.7, [m.ref], f"{m.best_sku} is more incremental than holder {m.holder_sku}")

    an = brief.anomalies
    for a in an[(an.direction == "surge") & ~an.own_action_confound].itertuples():
        if a.campaign_id not in dip:
            add("raise_bid", {"campaign_id": a.campaign_id, "keyword_id": a.keyword_id}, "small", 0.55, [a.ref],
                "demand surge not caused by our own change")
    intents.sort(key=lambda i: -i.confidence)                      # the schema keeps the first 25
    return IntentPlan(intents=[i.model_dump() for i in intents], notes="rules planner (EDA stance table)")
