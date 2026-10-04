"""Tests for the measurement layer. These are the guard rails for every experiment: if the oracle
or the switchable policy drifts from the code it models, the experiments built on them are void."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gpc.market import Market
from gpc.policy import DeterministicTraversal, NoOpPolicy
from gpc.world import WARMUP_DAYS, build_world

from experiments.lib import stats
from experiments.lib.counterfactual import ReplayPolicy, proposals_of, replay, week_totals
from experiments.lib.funnel import funnel, outcome
from experiments.lib.oracle import clean_mask, day_potential, true_incremental, week_states
from experiments.lib.runs import run_cached
from experiments.lib.switchable_policy import ARMS, Switches, SwitchablePolicy
from harness.policy import HTNToolsOnly

SEED = 7


@pytest.fixture(scope="module")
def l0():
    return run_cached("l0", HTNToolsOnly, SEED)


@pytest.fixture(scope="module")
def world():
    return build_world(SEED)


def test_switchable_all_on_equals_htn_tools_only(l0):
    sw = run_cached("sw_full", lambda: SwitchablePolicy(Switches()), SEED)
    for a, b in zip(l0.runs, sw.runs):
        pd.testing.assert_frame_equal(a["proposed"].reset_index(drop=True), b["proposed"].reset_index(drop=True))
    assert l0.sku_city_daily.offtake_inr.sum() == sw.sku_city_daily.offtake_inr.sum()


def test_switch_labels_are_distinct():
    labels = {s.label() for s in ARMS.values()}
    assert len(labels) == len(ARMS)


def test_aa_lift_is_exactly_zero(l0):
    again = run_cached("l0_again", HTNToolsOnly, SEED, use_cache=False)
    assert again.sku_city_daily.offtake_inr.sum() == l0.sku_city_daily.offtake_inr.sum()


def test_oracle_reconstructs_emitted_impressions(world, l0):
    """On auctions with no budget truncation, potential impressions must match emitted impressions
    to rounding. Checked on two warm-up days and two evaluation days."""
    m = Market(world)
    states = week_states(world, l0.runs)
    facts, cd = l0.daily_facts, l0.campaign_daily
    worst = 0.0
    n_cmp = 0
    for day in (3, 20, 30, 50):
        camp, ck = states[day]
        _, pot = day_potential(m, day, camp, ck)
        emitted = facts[facts.day == day].set_index(["campaign_id", "keyword_id", "daypart", "slot"]).impressions
        p = pot[clean_mask(world, pot, cd, day)].set_index(["campaign_id", "keyword_id", "daypart", "slot"])
        p = p[p.impressions_potential >= 1.0]
        joined = p.join(emitted, how="left")
        assert joined.impressions.notna().all(), "oracle predicts impressions the market never emitted"
        err = (joined.impressions_potential.round() - joined.impressions).abs().max()
        worst = max(worst, float(err))
        n_cmp += len(joined)
    assert n_cmp > 500
    assert worst <= 1.0, f"max impression error {worst}"


def test_true_incremental_bounds(world, l0):
    f = true_incremental(world, l0.daily_facts)
    assert (f.incr_units <= f.ad_orders + 1e-9).all()
    assert np.allclose(f.incr_units + f.cannibalised_units, f.ad_orders)


def test_funnel_identities(world, l0):
    t = funnel(world, l0.daily_facts, "total").iloc[0]
    assert t.direct_roas == pytest.approx(t.ad_revenue_inr / t.spend_inr)
    assert t.true_iroas <= t.direct_roas + 1e-9
    by_type = funnel(world, l0.daily_facts, "keyword_type")
    assert by_type.spend_inr.sum() == pytest.approx(t.spend_inr)
    by_week = funnel(world, l0.daily_facts, "week")
    assert set(by_week.week) == {1, 2, 3, 4, 5, 6}


def test_outcome_matches_score_summary(l0):
    from gpc.score import summarize
    s = summarize(l0)
    o = outcome(l0)
    assert round(o["offtake_per_day"]) == s["offtake_inr_per_day"]
    assert round(o["direct_roas"], 3) == s["direct_roas"]


def test_replay_policy_reproduces_a_run(l0):
    rp = ReplayPolicy(proposals_of(l0))
    again = replay(SEED, "dev", rp)
    assert again.sku_city_daily.offtake_inr.sum() == l0.sku_city_daily.offtake_inr.sum()


def test_stats_helpers():
    x = [0.5, 0.7, 0.9, 1.1, 0.6, 0.8]
    s = stats.summarize(x)
    assert s["ci95_lo"] < s["mean"] < s["ci95_hi"]
    assert stats.minimum_detectable_effect(0.27, 6) == pytest.approx(0.27 * 2.8 / 6 ** 0.5)
    assert stats.worlds_needed(0.27, 0.1) == 58   # ceil((2.8 * 0.27 / 0.1) ** 2) = ceil(57.2)
    assert stats.paired_lift_pct(101, 100) == pytest.approx(1.0)


def test_week_replay_is_exact(world, l0):
    """The foundation of the per-action counterfactuals: re-simulating one week from the recorded
    state with the recorded (guardrailed) actions reproduces that week's offtake exactly."""
    from experiments.lib.direct_sim import simulate_week, totals
    r = l0.runs[2]
    keep = ["campaign_id", "keyword_id", "action_type", "new_value"]
    t = totals(simulate_week(Market(world), r["day"], r["campaigns_before"], r["campaign_keywords_before"], r["final"][keep]))
    s = l0.sku_city_daily
    s = s[(s.day >= r["day"]) & (s.day < r["day"] + 7)]
    assert t["offtake_inr"] == float(s.offtake_inr.sum())


def test_scheduled_sim_with_no_actions_equals_no_op(world):
    from experiments.lib.direct_sim import simulate_scheduled
    from experiments.lib.runs import load_latest
    noop, _ = load_latest("no_op", SEED)
    d = simulate_scheduled(world)
    assert float(d["sku_city_daily"].offtake_inr.sum()) == float(noop.sku_city_daily.offtake_inr.sum())


def test_removing_a_week_action_changes_that_week_only(world, l0):
    """Weeks before the removed action's week are untouched (the market has no look-ahead)."""
    from experiments.lib.direct_sim import simulate_week, totals
    r = l0.runs[2]
    keep = ["campaign_id", "keyword_id", "action_type", "new_value"]
    final = r["final"].reset_index(drop=True)
    assert len(final) > 1
    m = Market(world)
    a = totals(simulate_week(m, r["day"], r["campaigns_before"], r["campaign_keywords_before"], final[keep]))
    b = totals(simulate_week(m, r["day"], r["campaigns_before"], r["campaign_keywords_before"], final.drop(index=0)[keep]))
    assert a["offtake_inr"] != b["offtake_inr"] or a["spend_inr"] != b["spend_inr"]


def test_t_ci_wider_than_bootstrap_and_signflip_exact():
    x = [0.5, 0.7, 0.9, 1.1, 0.6, 0.8]
    s = stats.summarize(x)
    assert s["ci95_hi"] - s["ci95_lo"] > s["boot_hi"] - s["boot_lo"]      # t is wider at n=6
    assert s["ci95_lo"] == pytest.approx(0.5400, abs=1e-3)               # 0.7667 - 2.571*0.2160/sqrt(6)
    assert stats.sign_flip_p([1, 1, 1, 1, 1, 1]) == pytest.approx(2 / 64)  # smallest possible at n=6
    assert stats.sign_flip_p([1, -1]) == 1.0
    assert s["mde"] == pytest.approx(stats.minimum_detectable_effect(s["sd"], 6))


def test_param_arms_change_only_what_they_say():
    from experiments.lib.switchable_policy import make_params
    from harness.config import load_params
    base = load_params()
    same = make_params()
    assert same == base                                   # identity override == the harness's own params
    p = make_params(frac_scale=2.0, min_allowance=1000.0, margin=0.0)
    assert p.run_allowance_frac == tuple(2 * f for f in base.run_allowance_frac)
    assert p.headroom_min_allowance_inr_day == 1000.0 and p.headroom_margin == 0.0
    assert p.allowance_frac(2) == pytest.approx(2 * base.allowance_frac(2))


def test_state_min_allowance_rules():
    from experiments.lib.switchable_policy import StateMin, state_min_allowance as f
    sm = StateMin(run1_min=1500.0, cap_frac=0.5, min_amt=3000.0)
    assert f(1, 0.0, 0.0, sm) == 1500.0                    # run 1: nothing banked, fixed run-1 minimum
    assert f(2, 0.0, 0.0, sm) == 300.0                     # thin margin: only the harness base minimum
    assert f(2, 2000.0, 0.0, sm) == 1000.0                 # capped at cap_frac x banked headroom
    assert f(3, 100000.0, 0.0, sm) == 3000.0               # roomy: up to min_amt
    assert f(3, 100000.0, 5000.0, sm) == 5000.0            # the schedule's own slice still wins when larger
    assert f(2, -5.0, 0.0, sm) == 300.0                    # defensive: negative headroom
    # monotone in banked headroom
    vals = [f(4, h, 0.0, sm) for h in (0, 500, 1000, 2000, 4000, 8000, 20000)]
    assert vals == sorted(vals)


def test_state_arm_with_no_override_equals_gate_off_min_zero_base():
    """With cap_frac=0 and run1_min=300 the state arm must reduce to the harness's own 300 minimum, i.e. L0."""
    from experiments.lib.switchable_policy import StateMin, state_min_allowance as f
    sm = StateMin(run1_min=300.0, cap_frac=0.0, min_amt=3000.0)
    for run, h, s in [(1, 0.0, 0.0), (2, 5000.0, 120.0), (4, 50000.0, 900.0)]:
        assert f(run, h, s, sm) == max(s, 300.0)


def test_state_arm_with_cap_zero_reproduces_l0_end_to_end(l0):
    """Integration check of the wiring (min_allowance zeroed, StateMin substituted): cap_frac=0 and run1_min=300
    must give exactly the harness's L0 proposals and outcome."""
    from experiments.lib.switchable_policy import StateMin, make_params
    sm = StateMin(run1_min=300.0, cap_frac=0.0, min_amt=3000.0)
    r = run_cached("sm_identity_test", lambda: SwitchablePolicy(Switches(), make_params(min_allowance=0.0), sm), SEED)
    for a, b in zip(l0.runs, r.runs):
        pd.testing.assert_frame_equal(a["proposed"].reset_index(drop=True), b["proposed"].reset_index(drop=True))
    assert l0.sku_city_daily.offtake_inr.sum() == r.sku_city_daily.offtake_inr.sum()


# ── scripted LLM: parse the REAL prompt templates (a regex drifting from a prompt edit must fail here) ──
def _scripted(mode, world=None):
    from experiments.lib.scripted_llm import ScriptedLLM
    w = world or build_world(SEED)
    llm = ScriptedLLM(w, mode)
    llm.attach_start_bids(w)
    return llm, w


def _ctx_cell(w):
    from experiments.lib.oracle import cell_truth
    ct = cell_truth(w)
    best, worst = ct.sort_values("true_value_per_impr").iloc[-1], ct.sort_values("true_value_per_impr").iloc[0]
    return best, worst


def test_scripted_llm_modes_on_real_prompts():
    from harness.htn.llm_methods import PROMPT_VERSIONS
    from harness.leaves.render import render
    for mode, want in (("always_yes", 1.5), ("always_no", 0.5)):
        llm, w = _scripted(mode)
        best, _ = _ctx_cell(w)
        sys_, user = render("L1_value", PROMPT_VERSIONS["L1_value"], {
            "campaign_id": best.campaign_id, "keyword_id": best.keyword_id, "keyword_type": "generic", "tier": "B",
            "verdict": "CLEARS", "orders_28d": 9, "live_bid": 200.0, "proposed_bid": 220.0, "step_pct": 10,
            "droas_shrunk": 5.0, "goal_droas": 4.0})
        out, _u = llm.complete_json(sys_, user, {}, 1, leaf="L1_value")
        assert out["bid_multiplier"] == want
    # oracle: the cell with the highest true value per impression is extended at a cheap CPM, the lowest is dampened
    llm, w = _scripted("oracle")
    best, worst = _ctx_cell(w)
    def l1(c, cpm):
        s, u = render("L1_value", PROMPT_VERSIONS["L1_value"], {"campaign_id": c.campaign_id, "keyword_id": c.keyword_id,
                      "keyword_type": "generic", "tier": "B", "verdict": "CLEARS", "orders_28d": 9, "live_bid": cpm,
                      "proposed_bid": cpm, "step_pct": 10, "droas_shrunk": 5.0, "goal_droas": 4.0})
        return llm.complete_json(s, u, {}, 1, leaf="L1_value")[0]["bid_multiplier"]
    cheap = best.true_value_per_impr * 1000 / 2.0          # a CPM at which iROAS proxy = 2 (> 1)
    dear = worst.true_value_per_impr * 1000 / 0.5          # proxy = 0.5 (< 1)
    assert l1(best, cheap) == 1.5 and l1(worst, dear) == 0.5


def test_scripted_llm_l2_l3_l4_l6_parse():
    from harness.htn.llm_methods import PROMPT_VERSIONS
    from harness.leaves.render import render
    w = build_world(SEED)
    llm, _ = _scripted("oracle", w)
    # L2: injected demand shock on K03/K04 from day 56 -> active at day 60 on K03, not at day 10, not on K05
    def l2(kw, day):
        llm.day = day
        s, u = render("L2_shock", PROMPT_VERSIONS["L2_shock"], {"campaign_id": "C-S1-DEL", "keyword_id": kw, "z_reach": 3.1,
                      "z_cpm": 0.2, "z_osa": 0.0, "shock_reach": True, "shock_cpm": False, "shock_osa_drop": False,
                      "own_action_confound": False, "direction": "surge"})
        return llm.complete_json(s, u, {}, 1, leaf="L2_shock")[0]["is_shock"]
    assert l2("K03", 60) is True and l2("K03", 10) is False and l2("K05", 60) is False
    # L3: oracle picks the campaign with the highest true value per impression, not necessarily the mechanical top
    from experiments.lib.oracle import cell_truth
    ct = cell_truth(w)
    g = ct.groupby(["city_id", "keyword_id"]).filter(lambda x: len(x) >= 2)
    (city, kw), grp = next(iter(g.groupby(["city_id", "keyword_id"])))
    grp = grp.sort_values("true_value_per_impr")
    table = "\n".join(f"- {r.campaign_id}, {r.sku_id}, {i + 1:.4f}, 0.50" for i, r in enumerate(grp.itertuples()))  # mechanical top = LAST
    s, u = render("L3_sibling", PROMPT_VERSIONS["L3_sibling"], {"city_id": city, "keyword_id": kw, "candidates_table": table})
    pick_oracle = llm.complete_json(s, u, {}, 1, leaf="L3_sibling")[0]["leader_campaign_id"]
    assert pick_oracle == grp.campaign_id.iloc[-1]                    # highest true value
    for mode, want_top in (("always_no", True), ("always_yes", False)):
        l, _ = _scripted(mode, w)
        pick = l.complete_json(s, u, {}, 1, leaf="L3_sibling")[0]["leader_campaign_id"]
        assert (pick == grp.campaign_id.iloc[-1]) is want_top         # always_no keeps the mechanical top; yes flips it
    # L4 / L6 parse and respond in the right direction
    best, worst = _ctx_cell(w)
    ly, _ = _scripted("always_yes", w)
    s, u = render("L4_explore", PROMPT_VERSIONS["L4_explore"], {"campaign_id": best.campaign_id, "keyword_id": best.keyword_id,
                  "keyword_type": "generic", "orders_28d": 2, "spend_14d": 100.0, "live_bid": 200.0, "relevance": 0.9,
                  "n_already_exploring": 0, "max_thin_cells": 5})
    assert ly.complete_json(s, u, {}, 1, leaf="L4_explore")[0] == {"explore": True, "max_spend_inr_day": 1000.0}
    table = f"- {best.campaign_id}/{best.keyword_id} increase_cpm: INR 800/day, M_Reprice"
    s, u = render("L6_review", PROMPT_VERSIONS["L6_review"], {"run": 3, "allowance_used": 800, "allowance_total": 2000,
                  "review_threshold": 500, "large_actions_table": table})
    assert ly.complete_json(s, u, {}, 1, leaf="L6_review")[0]["veto"] is True
    ln, _ = _scripted("always_no", w)
    assert ln.complete_json(s, u, {}, 1, leaf="L6_review")[0]["veto"] is False


def test_scripted_llm_unlisted_leaf_raises_so_leaf_defaults():
    from experiments.lib.scripted_llm import ScriptedLLM
    w = build_world(SEED)
    llm = ScriptedLLM(w, "always_yes", leaves=("L3_sibling",))
    with pytest.raises(RuntimeError):
        llm.complete_json("s", "u", {}, 1, leaf="L1_value")


def test_floor_status_matches_official_scorer(l0):
    from experiments.lib.funnel import floor_status
    from gpc.score import summarize
    f, s = floor_status(l0), summarize(l0)
    assert f["met"] == s["roas_constraint_met"]
    assert f["margin"] == pytest.approx(s["direct_roas"] - s["roas_floor"])
    assert f["floor_safe_offtake_per_day"] == (s["offtake_inr_per_day"] if f["met"] else 0.0)


def test_recorder_does_not_change_actions_and_records_shocks(l0):
    from experiments.lib.recorder import RecorderPolicy
    r = run_cached("l0rec", RecorderPolicy, SEED)
    for a, b in zip(l0.runs, r.runs):
        pd.testing.assert_frame_equal(a["proposed"].reset_index(drop=True), b["proposed"].reset_index(drop=True))
        assert "shocks" in b["trace"] and "z_reach" in b["trace"]["shocks"].columns
    assert l0.sku_city_daily.offtake_inr.sum() == r.sku_city_daily.offtake_inr.sum()


def test_x1_sections_have_sane_invariants():
    """Smoke test over the cached dev runs: shapes and bounds that must hold whatever the findings are."""
    from experiments.x1_modules import x1_run
    f_cell, f_all = x1_run.x1_1()
    assert set(f_all.stratum) == {"ran_out", "not_run_out"} and (f_all.real_spend >= 0).all() and (f_all.pred_spend > 0).all()
    d, s = x1_run.x1_3()
    assert s.leader_correct.between(0, 1).all() and (d.value_ratio_chosen_vs_best.dropna() <= 1 + 1e-9).all()
    h_run, h_end = x1_run.x1_4()
    assert (h_run.allowance_inr_day >= 300 - 1e-9).all() and (h_run.headroom_inr_day >= 0).all()
    # end slack is consistent with the official floor: slack > 0  <=>  margin over the floor > 0
    assert ((h_end.end_slack_inr_total > 0) == (h_end.end_margin > 0)).all()
    i_type, _ = x1_run.x1_2()
    assert i_type.mae_vs_eff.between(0, 1).all()


def test_perturbed_scenarios_change_exactly_one_thing():
    from experiments.lib.scenarios import VARIANTS, scenario_paths
    from gpc.world import load_scenario
    paths = scenario_paths()
    dev = load_scenario("dev")
    assert set(VARIANTS) <= set(paths) and any(n.startswith("P1") for n in paths) and len(paths) == 7 + 6
    v = load_scenario(paths["V_iota_hi"])
    assert all(v["keywords"][k]["incrementality"] == pytest.approx(min(0.98, dev["keywords"][k]["incrementality"] * 1.3), abs=1e-3) for k in dev["keywords"])
    assert v["shocks"] == dev["shocks"] and v["auction_sigma"] == dev["auction_sigma"] and v["appeal"] == dev["appeal"]
    assert load_scenario(paths["V_sigma_hi"])["auction_sigma"] == 0.45
    rot = load_scenario(paths["V_appeal_rot"])["appeal"]
    assert sorted(rot.values()) == sorted(dev["appeal"].values()) and rot != dev["appeal"]
    assert load_scenario("dev") == dev                       # the dev file itself is untouched
    w = build_world(SEED, paths["V_sigma_lo"])               # and a perturbed world actually builds, with the new value
    assert w.truth["auction_sigma"] == 0.2


def test_bid_dose_step_zero_is_the_unmodified_week_and_bids_move_spend(l0, world):
    """X3.1 plumbing: step 0 equals a no-action week for the cell; a +50% bid cannot lower the cell's slot-1 share
    or its spend, and a -50% bid cannot raise them (monotone auction)."""
    from experiments.x3_market import x3_1_bid_dose as x
    cells = x.pick_cells(l0, 0, world, per_type=1)
    assert len(cells) == 3 and set(cells.ktype) == {"brand", "competition", "generic"}
    row = cells.iloc[0].to_dict()
    row["live_bid"] = row["live_bid"]
    import experiments.x3_market.x3_1_bid_dose as mod
    old = mod.STEPS
    mod.STEPS = (-50, 0, 50)
    try:
        out = pd.DataFrame(mod.one_cell((SEED, 0, row)))
    finally:
        mod.STEPS = old
    lo, mid, hi = (out[out.step == s].iloc[0] for s in (-50, 0, 50))
    r0 = l0.runs[0]
    from experiments.lib.direct_sim import simulate_week
    from gpc.market import Market
    fr = simulate_week(Market(world), r0["day"], r0["campaigns_before"], r0["campaign_keywords_before"])
    f = fr["daily_facts"]
    c = f[(f.campaign_id == row["campaign_id"]) & (f.keyword_id == row["keyword_id"])]
    assert mid.spend == pytest.approx(c.spend_inr.sum())
    assert lo.spend <= mid.spend + 1e-6 <= hi.spend + 2e-6
    assert hi.slot1_share + 1e-9 >= mid.slot1_share >= lo.slot1_share - 1e-9


def test_no_generic_cuts_removes_only_generic_cuts():
    """The switch must drop exactly the cuts whose keyword is generic and leave the others (and all raises) alone."""
    from experiments.lib.switchable_policy import recommend
    from harness.config import load_params
    from gpc.runner import simulate
    # run-1 observation of the dev world via a recording policy
    seen = {}
    class Rec(SwitchablePolicy):
        def recommend(self, obs):
            seen.setdefault("obs", obs)
            return super().recommend(obs)
    from gpc.policy import NoOpPolicy
    class First(NoOpPolicy):
        def recommend(self, obs):
            if obs.run == 4:                 # a later run, when the ladder has had time to propose cuts
                seen["obs"] = obs
            return super().recommend(obs)
    simulate(build_world(SEED), First(), verbose=False)
    obs = seen["obs"]
    full, _ = recommend(obs, load_params(), Switches())
    ng, _ = recommend(obs, load_params(), Switches(generic_cuts=False))
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    is_cut = lambda a: a.action_type == "reduce_cpm"
    assert (ng[is_cut(ng)].keyword_id.map(kt) != "generic").all()
    keep = full[is_cut(full) & (full.keyword_id.map(kt) != "generic")]
    assert len(ng[is_cut(ng)]) == len(keep) and len(ng[~is_cut(ng)]) == len(full[~is_cut(full)])
    assert len(full[is_cut(full)]) > len(keep) > 0       # non-vacuous: generic cuts exist, and non-generic ones survive
