import pandas as pd
import pytest

from gpc.guardrails import BID_CEIL, BID_FLOOR, BID_STEP, apply_guardrails
from harness_l2p.compiler import MAX_CELLS_PER_INTENT, compile_plan
from harness_l2p.intents import IntentPlan
from harness_l2p.policy import _l0_candidates
from harness_l2p.rules_planner import rules_plan


def _plan(*intents):
    return IntentPlan.model_validate({"intents": list(intents)})


def _compile(ctx, plan, mode="native", l0=None):
    return compile_plan(ctx["obs"], ctx["diag"], ctx["brief"], ctx["iota"], plan, mode, l0)


def test_each_verb_maps_to_its_lever(ctx):
    r = _compile(ctx, _plan(
        {"id": "b", "verb": "cut_bid", "scope": {"sku_id": "S3", "city_id": "DEL", "keyword_type": "generic"}, "size": "small"},
        {"id": "c", "verb": "pause", "scope": {"campaign_id": "C-S5-MUM", "keyword_id": "K03"}},
        {"id": "e", "verb": "cut_budget", "scope": {"campaign_id": "C-S5-MUM"}},
        {"id": "f", "verb": "set_dayparts", "scope": {"campaign_id": "C-S5-PUN"}, "dayparts": ["morning", "evening"]}))
    got = dict(zip(r.actions.reason.str.split(":").str[1], r.actions.action_type))
    assert got["b"] == "reduce_cpm" and got["c"] == "pause_keyword" and got["e"] == "reduce_budget" and got["f"] == "set_dayparts"
    assert r.actions.reason.str.startswith("L2P:").all()


def test_values_stay_inside_guardrail_limits(ctx):
    live = ctx["obs"].campaign_keywords.set_index(["campaign_id", "keyword_id"]).bid_cpm_inr
    r = _compile(ctx, _plan({"id": "x", "verb": "cut_bid", "scope": {"sku_id": "S1", "city_id": "MUM"}, "size": "large"}))
    for a in r.actions.itertuples():
        lv = live[(a.campaign_id, a.keyword_id)]
        assert BID_FLOOR <= a.new_value <= BID_CEIL
        assert lv * (1 - BID_STEP) - 5 <= a.new_value < lv
    final, log, _ = apply_guardrails(ctx["obs"], r.actions)
    assert not log[log.outcome == "clamped"].rule.isin(["G1_BID_BOUNDS"]).any()


def test_compiled_actions_are_never_blocked_by_g0_to_g7(ctx):
    l0 = _l0_candidates(ctx["obs"], ctx["diag"], ctx["iota"], ctx["params"])
    for mode in ("augment", "native"):
        r = _compile(ctx, rules_plan(ctx["brief"]), mode, l0 if mode == "augment" else None)
        _, log, _ = apply_guardrails(ctx["obs"], r.actions)
        assert not (log.outcome == "blocked").any(), log[log.outcome == "blocked"]


def test_conflicts_resolve_to_one_action_per_lever(ctx):
    r = _compile(ctx, _plan(
        {"id": "hi", "verb": "cut_bid", "scope": {"campaign_id": "C-S3-DEL", "keyword_id": "K03"}, "confidence": 0.9},
        {"id": "lo", "verb": "pause", "scope": {"campaign_id": "C-S3-DEL", "keyword_id": "K03"}, "confidence": 0.1}))
    assert len(r.actions) == 1 and r.actions.reason.iloc[0].startswith("L2P:hi")


def test_bad_scopes_are_rejected_with_a_reason(ctx):
    r = _compile(ctx, _plan({"id": "wide", "verb": "raise_bid", "scope": {"sub_category": "Soap"}},
                            {"id": "ghost", "verb": "raise_bid", "scope": {"sku_id": "S9"}}))
    reasons = {x["intent_id"]: x["reason"] for x in r.rejected}
    assert f"> {MAX_CELLS_PER_INTENT}" in reasons["wide"] and "unknown sku" in reasons["ghost"]
    assert r.actions.empty


def test_native_empty_plan_ships_nothing(ctx):
    assert _compile(ctx, IntentPlan(intents=[])).actions.empty


def test_campaign_hold_blocks_only_its_budget_raise(ctx):
    l0 = _l0_candidates(ctx["obs"], ctx["diag"], ctx["iota"], ctx["params"])
    bud = l0["raises"][l0["raises"].action_type == "increase_budget"] if len(l0["raises"]) else l0["raises"]
    if not len(bud):
        pytest.skip("no L0 budget raise on this observation")
    target = bud.campaign_id.iloc[0]
    r = _compile(ctx, _plan({"id": "h", "verb": "hold", "scope": {"campaign_id": target}}), "augment", l0)
    mine = r.actions[r.actions.campaign_id == target]
    assert not (mine.action_type == "increase_budget").any() and r.l0_held >= 1


def test_cell_hold_blocks_l0_bid_moves_on_those_cells(ctx):
    l0 = _l0_candidates(ctx["obs"], ctx["diag"], ctx["iota"], ctx["params"])
    cells = pd.concat([l0["raises"], l0["cuts"]])
    cells = cells[cells.keyword_id.fillna("") != ""]
    if not len(cells):
        pytest.skip("no L0 bid candidates")
    c, k = cells.campaign_id.iloc[0], cells.keyword_id.iloc[0]
    r = _compile(ctx, _plan({"id": "h", "verb": "hold", "scope": {"campaign_id": c, "keyword_id": k}}), "augment", l0)
    assert not ((r.actions.campaign_id == c) & (r.actions.keyword_id == k)).any()


def test_protected_cells_and_fund_campaigns_refuse_intent_cuts(ctx):
    c = ctx["brief"].cells
    prot = c[(c.protected != "") & (c.bid >= 260)]          # room to cut above the ₹200 floor
    if not len(prot):
        pytest.skip("nothing protected on this observation")
    x = prot.iloc[0]
    r = _compile(ctx, _plan({"id": "p", "verb": "cut_bid", "scope": {"campaign_id": x.campaign_id, "keyword_id": x.keyword_id}}))
    assert r.actions.empty and any("protected" in j["reason"] for j in r.rejected)
    fund = ctx["brief"].roles[ctx["brief"].roles.role == "fund"]
    if len(fund):
        r2 = _compile(ctx, _plan({"id": "f", "verb": "cut_budget", "scope": {"campaign_id": fund.campaign_id.iloc[0]}}))
        assert r2.actions.empty and "fund campaign" in r2.rejected[0]["reason"]


def test_share_curve_prices_raises_the_grid_calls_zero(ctx):
    from harness_l2p.compiler import _Ctx, _share_curve
    x = _Ctx(ctx["obs"], ctx["diag"], ctx["brief"], ctx["iota"])
    c = ctx["brief"].cells
    part = c[(c.slot1_share > 0.1) & (c.slot1_share < 0.7)]
    if not len(part):
        pytest.skip("no partly-held cell")
    row = part.iloc[0]
    df = pd.DataFrame([{"campaign_id": row.campaign_id, "keyword_id": row.keyword_id, "action_type": "increase_cpm",
                        "new_value": x.live[(row.campaign_id, row.keyword_id)] * 1.2, "reason": "t", "source": "intent",
                        "pred_delta_spend": 0.0, "pred_delta_rev": 0.0}])
    out = _share_curve(df, x)
    assert out.priced_by.iloc[0] == "share_curve" and out.pred_delta_spend.iloc[0] > 0 and out.pred_delta_rev.iloc[0] > 0
