"""Sim v2 Module A gates (design/02 §10 step 1): nested-logit shelf, diversion, decomposition."""
import numpy as np
import pytest

from gpc.shelf import OUTSIDE, QueryShelf, decompose, diversion, nested_logit, organic_weight
from gpc.world import build_world


def _shelf(lam=(0.35, 0.6), beta=0.7):
    # 3 bar items (2 own, 1 competitor), 2 liquid items (1 own, 1 competitor)
    return QueryShelf("Kx", ["S1", "S3", "V1", "S2", "N2"], np.array([1, 1, 0, 1, 0], bool),
                      np.array([0, 0, 0, 1, 1]), np.array(lam, float),
                      np.log(np.array([1.0, 0.9, 1.05, 0.8, 1.1])), np.array([0.8, 0.5, 1.0, 0.3, 0.9]), beta, 0.4)


def test_organic_weight_matches_industry_curve():
    assert organic_weight(1) == 1.0 and organic_weight(None) == 0.0 and organic_weight(float("nan")) == 0.0
    for r, v in {5: 0.41, 9: 0.17, 13: 0.08}.items():
        assert abs(organic_weight(r) - v) < 0.02


def test_probabilities_sum_to_one():
    sh = _shelf()
    p, p0 = sh.probs(np.array([1.0, 0, 0, 0.4, 0]))
    assert p.min() >= 0 and abs(p.sum() + p0 - 1) < 1e-12


def test_mnl_limit_is_iia():
    """λ = 1 for every nest: raising one item's visibility leaves the odds between any two others unchanged."""
    sh = _shelf(lam=(1.0, 1.0))
    p, _ = sh.probs()
    q, _ = sh.probs(np.array([0, 0, 0, 0.7, 0]))
    others = [0, 1, 2, 4]
    r1, r2 = p[others] / p[others[0]], q[others] / q[others[0]]
    np.testing.assert_allclose(r1, r2, rtol=1e-12)


def test_small_lambda_makes_siblings_lose_more():
    """λ < 1: an ad on S1 takes proportionally more from bar items (same nest) than from liquids."""
    sh = _shelf()
    p, _ = sh.probs()
    q, _ = sh.probs(np.array([0.6, 0, 0, 0, 0]))
    rel_loss = (p - q) / p
    assert rel_loss[1] > rel_loss[3] and rel_loss[2] > rel_loss[4]


@pytest.mark.parametrize("i", range(5))
def test_diversion_closed_form_matches_finite_difference_and_sums_to_one(i):
    sh = _shelf()
    d = diversion(sh, i)
    assert abs(sum(d.values()) - 1) < 1e-9                 # every unit gained by i comes from somewhere
    eps = 1e-6
    v2 = sh.v.copy(); v2[i] += eps
    p, p0 = nested_logit(sh.w_org, sh.v, sh.nest, sh.lam, sh.beta, sh.v0)
    q, q0 = nested_logit(sh.w_org, v2, sh.nest, sh.lam, sh.beta, sh.v0)
    gain = q[i] - p[i]
    for j, item in enumerate(sh.items):
        if j != i:
            assert abs((p[j] - q[j]) / gain - d[item]) < 1e-4, item
    assert abs((p0 - q0) / gain - d[OUTSIDE]) < 1e-4


def test_decomposition_fractions_are_a_partition():
    sh = _shelf()
    out = decompose(sh, {"S1": 0.9, "S3": 0.4, "S2": 0.2})
    assert set(out) == {"S1", "S3", "S2"}
    for item, f in out.items():
        tot = f["self"] + sum(f["sibling"].values()) + f["competitor"] + f["expansion"]
        assert abs(tot - 1) < 1e-12 and 0 <= f["self"] <= 1 and item not in f["sibling"]


def test_own_ad_with_no_organic_listing_has_no_self_share():
    sh = _shelf()
    sh.w_org = sh.w_org.copy(); sh.w_org[0] = 0.0
    assert decompose(sh, {"S1": 0.5})["S1"]["self"] == pytest.approx(0.0, abs=1e-12)


def test_world_publishes_shelves_and_diversion_only_in_truth():
    w = build_world(7, "sc1_cannibal")
    assert {"shelves", "diversion"} <= set(w.truth)
    assert not {"shelves", "diversion"} & set(w.public)
    # public organic ranks (doc 02 §7.2) carry no hidden choice parameters
    assert set(w.public["shelf_ranks"].columns) == {"keyword_id", "item_id", "brand", "organic_rank"}
    assert "shelves" not in build_world(7, "dev").truth
