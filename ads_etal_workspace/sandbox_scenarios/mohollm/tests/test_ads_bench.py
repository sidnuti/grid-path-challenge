"""P3 gates: decoder, guardrail-free simulator loop, black box, MoHOLLM adapter and arms, all offline ($0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "gpc_v2")]

from bench.blackbox import CODE_VERSION, BlackBox, x_key                      # noqa: E402
from bench.decode import BASE_DIMS, REGION, Encoding, decode, region_shares    # noqa: E402
from bench.design import initial_design, sobol                                 # noqa: E402
from bench.goals import measure                                                # noqa: E402
from bench.sim import WarmStart, run                                           # noqa: E402

pytestmark = pytest.mark.offline
HOLD = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.32, 0.485, 0.5, 0.5, 1.0])


@pytest.fixture(scope="module")
def sc3_obs():
    """An observation at the start of run 3 (day 42, the festive window opens) on sc3."""
    from gpc.world import build_world
    w = build_world(7, "sc3_festive")
    ws = WarmStart(w)
    seen = {}

    def pol(obs):
        seen[obs.run] = obs
        return obs.public["campaigns"], obs.public["campaign_keywords"]
    run(ws, pol, n_runs=3)
    return w, seen


# ── decoder ────────────────────────────────────────────────────────────────────
def test_stick_breaking_is_a_simplex_for_any_box_point():
    for x in sobol(2, 64, 0):
        s = region_shares({"share_north": x[0], "share_west_of_rest": x[1]})
        assert min(s.values()) >= -1e-12 and abs(sum(s.values()) - 1) < 1e-12


def test_decode_is_pure_and_respects_physical_bounds(sc3_obs):
    w, seen = sc3_obs
    obs = seen[3]
    for x in sobol(10, 8, 1):
        c1, k1 = decode(x, obs)
        c2, k2 = decode(x.copy(), obs)
        pd.testing.assert_frame_equal(c1, c2)
        pd.testing.assert_frame_equal(k1, k2)
        assert k1.bid_cpm_inr.between(200, 10_000).all() and (c1.daily_budget_inr >= 0).all()


def test_budget_split_follows_region_shares_and_totals_B(sc3_obs):
    w, seen = sc3_obs
    obs = seen[3]
    x = np.array([0.5] * 5 + [0.3, 0.6, 0.5, 0.5, 1.0])
    c, _ = decode(x, obs)
    f = obs.daily_facts
    B = f[f.day < 28].spend_inr.sum() / 28
    assert c.daily_budget_inr.sum() == pytest.approx(B, rel=1e-6)
    by_region = c.groupby(c.city_id.map(REGION)).daily_budget_inr.sum() / B
    s = region_shares({"share_north": 0.3, "share_west_of_rest": 0.6})
    for g, v in s.items():
        assert by_region[g] == pytest.approx(v, abs=1e-6)


def test_festive_lever_and_live_window(sc3_obs):
    w, seen = sc3_obs
    off = np.array([0.5] * 8 + [0.0, 1.0])
    c, k = decode(off, seen[3])                                     # festive = 0: gift-pack cells off, no S6 budget
    s6 = k.campaign_id.str.contains("S6") | (k.keyword_id == "K11")
    assert not k[s6].active.any() and c[c.sku_id == "S6"].daily_budget_inr.sum() == 0
    on = np.array([0.5] * 8 + [1.0, 1.0])
    c3, _ = decode(on, seen[3])                                     # run 3 (days 42–48) overlaps the live window
    c1, _ = decode(on, seen[1])                                     # run 1 (days 28–34) does not
    assert c3[c3.sku_id == "S6"].daily_budget_inr.sum() > 0 and c1[c1.sku_id == "S6"].daily_budget_inr.sum() == 0


def test_defend_threshold_raises_brand_bids(sc3_obs):
    w, seen = sc3_obs
    base = np.array([0.5] * 9 + [1.0])                              # never defend
    always = np.array([0.5] * 9 + [0.0])                            # defend wherever the signal is > 0
    _, kb = decode(base, seen[2])
    _, ka = decode(always, seen[2])
    r = (ka.bid_cpm_inr / kb.bid_cpm_inr)[kb.keyword_id == "K01"]
    assert (np.isclose(r, 1.5) | np.isclose(r, 1.0)).all() and np.isclose(r, 1.5).any()


def test_budget_scale_only_in_the_g1_encoding():
    assert Encoding().dims == BASE_DIMS and Encoding(budget_scale=True).dims == BASE_DIMS + ["budget_scale"]
    with pytest.raises(AssertionError):
        Encoding().as_dict(np.full(11, 0.5))


# ── simulator loop and black box ───────────────────────────────────────────────
def test_hold_matches_the_legacy_runner_and_scorer():
    """Guardrail-free bench loop with the starting set-up == gpc runner NoOp scored by score_v2 (cross-check)."""
    from gpc import score_v2
    from gpc.policy import NoOpPolicy
    from gpc.runner import simulate
    from gpc.world import build_world
    w = build_world(7, "sc1_cannibal")
    ref = score_v2.score(simulate(w, NoOpPolicy()), w)
    bb = BlackBox("sc1_cannibal", 7, cache=False)
    hold = run(bb.ws, lambda o: (o.public["campaigns"], o.public["campaign_keywords"]))
    assert measure(bb.world, hold, bb.budget_per_day())["inc_rev"] == ref["inc_rev_inr"]


def test_black_box_is_deterministic_and_forks_do_not_leak():
    a = BlackBox("sc_all", 11, cache=False)
    x1, x2 = HOLD, np.array([0.9, 0.2, 0.1, 0.8, 0.3, 0.2, 0.7, 0.1, 0.9, 0.0])
    r1 = a(x1)
    a(x2)                                                            # a different policy in between …
    a._mem.clear()
    r1b = a(x1)                                                      # … does not change x1's result
    b = BlackBox("sc_all", 11, cache=False)
    for k in ("inc_rev", "spend", "f2_s5_north_slot1", "f3_s6_sell_through", "constraints"):
        assert r1[k] == r1b[k] == b(x1)[k]


def test_cache_key_carries_code_version_and_hits_are_identical(tmp_path, monkeypatch):
    import bench.blackbox as bbm
    monkeypatch.setattr(bbm, "CACHE_DIR", tmp_path)
    assert x_key(HOLD) != x_key(HOLD + 1e-9) and CODE_VERSION in bbm.CODE_VERSION
    a = bbm.BlackBox("sc1_cannibal", 7)
    r = a(HOLD)
    b = bbm.BlackBox("sc1_cannibal", 7)                              # new process-equivalent: reads the cache files
    assert b(HOLD) == r and b.n_sims == 0


def test_decoded_policies_never_spend_outside_the_live_window():
    bb = BlackBox("sc3_festive", 7, cache=False)
    for x in sobol(10, 3, 5):
        assert bb(x)["constraints"]["C3_outside_window_spend"] == 0


# ── MoHOLLM adapter and arms ───────────────────────────────────────────────────
def test_adapter_interface_and_negation():
    from adapters.grid_market import GridMarketBenchmark
    g0 = GridMarketBenchmark("sc1_cannibal", 7, "G0")
    pts = g0.generate_initialization(5)
    assert [list(p.values()) for p in pts] == initial_design(10, 7).tolist()
    p, f = g0.evaluate_point(pts[0])
    assert list(f) == ["F1"] and f["F1"] == pytest.approx(-g0.log[-1]["inc_rev"] / 1e5, abs=1e-4)
    n = g0.bb.n_sims
    assert not g0.is_valid_candidate({**pts[0], "bid_brand": 1.2}) and not g0.is_valid_candidate({"bid_brand": 0.1})
    assert g0.is_valid_candidate(pts[1]) and g0.bb.n_sims == n          # validity check never simulates
    g1 = GridMarketBenchmark("sc_all", 7, "G1")
    _, f1 = g1.evaluate_point(g1.generate_initialization(1)[0])
    assert list(f1) == ["F1", "F2", "F3"] and all(v <= 0 for v in f1.values())


def test_configs_for_single_and_multi_objective():
    from adapters.ads_configs import make_config
    from adapters.grid_market import GridMarketBenchmark
    g0 = GridMarketBenchmark("sc1_cannibal", 7, "G0")
    c4 = make_config("A4", g0, 50)
    assert c4["optimization_method"] == "SpacePartitioning" and c4["acquisition_function"] == "FunctionValueACQ"
    assert c4["space_partitioning_settings"]["region_acquisition_strategy"] == "ScoreRegion"
    assert 5 + c4["top_k"] * c4["n_trials"] == 50 and c4["metrics_targets"] == ["min"]
    assert make_config("A5", g0)["acquisition_function"] == "RandomTopKACQ"
    assert make_config("A3", g0)["optimization_method"] == "mohollm"
    c41 = make_config("A4", GridMarketBenchmark("sc_all", 7, "G1"))
    assert c41["space_partitioning_settings"]["region_acquisition_strategy"] == "ScoreRegionRHVC"
    assert c41["acquisition_function"] == "HypervolumeImprovement"


def test_random_topk_acquisition_returns_k_distinct():
    from adapters.ads_acq import RandomTopKACQ
    np.random.seed(0)
    idx, evals, _ = RandomTopKACQ().select_candidate_point([{"F1": i} for i in range(9)], top_k=5)
    assert len(set(idx.tolist())) == 5 and evals == [{"F1": i} for i in idx]


def _r_ads(tmp_path, *args):
    env = {**os.environ, "BENCH_CACHE": str(tmp_path / "cache")}
    out = subprocess.run([sys.executable, str(ROOT / "mohollm" / "runs" / "r_ads.py"), *args, "--out", str(tmp_path)],
                         capture_output=True, text=True, env=env, timeout=900)
    assert out.returncode == 0, out.stderr[-2000:]
    return out


@pytest.mark.parametrize("arm,goal,scen", [("A4", "G0", "sc1_cannibal"), ("A4", "G1", "sc_all"),
                                            ("A3", "G0", "sc1_cannibal"), ("A5", "G0", "sc1_cannibal")])
def test_end_to_end_offline(tmp_path, arm, goal, scen):
    args = ["--arm", arm, "--scenario", scen, "--seed", "7", "--goal", goal, "--evals", "15"]
    _r_ads(tmp_path, *args, *(["--scripted"] if arm != "A5" else []))
    f = next((tmp_path / arm).glob("*.json"))
    r = json.loads(f.read_text())
    assert r["n_evals"] == 15
    X = np.array([[e["point"][k] for k in Encoding(budget_scale=goal == "G1").dims] for e in r["evaluations"]])
    assert X.min() >= 0 and X.max() <= 1
    assert X[:5].round(4).tolist() == initial_design(X.shape[1], 7).tolist()     # shared initial design
    assert all(np.isfinite(e["inc_rev"]) for e in r["evaluations"])
    if arm == "A5":
        assert r["llm_calls_scripted"] == 0 and r["llm"] is None
    else:
        assert r["llm_calls_scripted"] > 0
