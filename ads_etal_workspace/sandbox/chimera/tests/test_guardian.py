"""SymbolicGuardianV4 (= CSLGuardianEcom backed by policies/ecommerce_guard.csl) vs the legacy pure-Python guardian.
Property tests over random actions/states; TLA+ model check if Java + tla2tools are available."""
import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from src import csl_guardian
from src.components import SymbolicGuardianV4, _LegacySymbolicGuardianV4

pytestmark = pytest.mark.offline
UP = Path(__file__).resolve().parents[1] / "upstream"

CSL = SymbolicGuardianV4()
LEGACY = _LegacySymbolicGuardianV4()
# 10k random examples per property (plan), no deadline: the CSL/Z3 verify call is slow-ish.
S = settings(max_examples=10_000, deadline=None, suppress_health_check=list(HealthCheck), database=None)

# State: price within the simulator's own bounds, ad spend within its cap. Actions deliberately wander far outside
# the allowed region (LLMs do).
states = st.fixed_dictionaries({"price": st.floats(50.0, 150.0), "weekly_ad_spend": st.floats(0.0, 5000.0)})
actions = st.fixed_dictionaries({"price_change": st.floats(-1.5, 1.5, allow_nan=False),
                                 "ad_spend": st.floats(-2000.0, 12000.0, allow_nan=False)})


def test_csl_backend_is_actually_loaded():
    """If csl-core were missing the 'CSL' guardian silently falls back to legacy and every agreement test is vacuous."""
    assert csl_guardian.CSL_AVAILABLE and CSL._guard is not None


@S
@given(actions, states)
def test_repair_always_yields_valid_action(a, s):
    fixed, report = CSL.repair_action(a, s)
    assert report["is_valid"], (a, s, fixed, report)
    assert CSL.validate_action(fixed, s)["is_valid"]


@S
@given(actions, states)
def test_repair_is_idempotent(a, s):
    once, _ = CSL.repair_action(a, s)
    twice, _ = CSL.repair_action(once, s)
    assert twice == pytest.approx(once, rel=1e-9, abs=1e-9)


@S
@given(actions, states)
def test_repair_is_identity_on_valid_actions(a, s):
    # Scoped to actions valid under BOTH guardians: the CSL one also accepts sub-dollar rounding artefacts (see below).
    if CSL.validate_action(a, s)["is_valid"] and LEGACY.validate_action(a, s)["is_valid"]:
        fixed, _ = CSL.repair_action(a, s)
        assert fixed["ad_spend"] == pytest.approx(a["ad_spend"]) and fixed["price_change"] == pytest.approx(a["price_change"])


def test_upstream_finding_csl_rounds_before_checking_so_tiny_negative_ad_spend_passes():
    """UPSTREAM FINDING (logged in REPLICATION_REPORT.md): CSL integer-rounds ad_spend, so -0.4 rounds to 0 and is
    'valid', whereas the legacy guardian (and the stated rule 'ad spend cannot be negative') rejects it. Harmless in
    practice (< $0.50) but the CSL policy is not an exact encoding of the legacy rules."""
    s = {"price": 100.0, "weekly_ad_spend": 0.0}
    a = {"price_change": 0.0, "ad_spend": -0.4}
    assert CSL.validate_action(a, s)["is_valid"] and not LEGACY.validate_action(a, s)["is_valid"]


def test_csl_legacy_disagreement_is_boundary_only():
    """Quantify CSL-vs-legacy disagreement on 20k seeded random actions; every disagreement must be explainable by the
    CSL integer rounding (within $1 / 0.5pp / 1 cent of a limit)."""
    import numpy as np
    rng = np.random.default_rng(0)
    n, bad, near = 20_000, 0, 0
    for _ in range(n):
        s = {"price": float(rng.uniform(50, 150)), "weekly_ad_spend": float(rng.uniform(0, 5000))}
        a = {"price_change": float(rng.uniform(-0.6, 0.7)), "ad_spend": float(rng.uniform(-100, 6200))}
        if CSL.validate_action(a, s)["is_valid"] != LEGACY.validate_action(a, s)["is_valid"]:
            bad += 1
            c = LEGACY.cfg
            fp = s["price"] * (1 + a["price_change"])
            msp = c["unit_cost"] / (1 - c["min_margin"]) * (1 + c["safety_buffer_ratio"])
            edges = [abs(a["ad_spend"]) < 1.0, abs(a["ad_spend"] - c["ad_cap"]) < 1.0,
                     abs((a["ad_spend"] - s["weekly_ad_spend"]) - c["ad_increase_cap"]) < 1.0,
                     abs(a["price_change"] + c["max_dn"]) < 0.006, abs(a["price_change"] - c["max_up"]) < 0.006,
                     abs(a["price_change"]) < 0.006, abs(fp - c["max_price"]) < 0.02, abs(fp - msp) < 0.02]
            near += any(edges)
    assert near == bad, f"{bad - near} of {bad} disagreements are NOT near a rule boundary"
    assert bad / n < 0.01


VIOLATIONS = [
    ({"price_change": -0.9, "ad_spend": 0}, {"price": 100, "weekly_ad_spend": 0}, "discount", "max_discount"),
    ({"price_change": 0.9, "ad_spend": 0}, {"price": 100, "weekly_ad_spend": 0}, "increase", "max_price_increase"),
    ({"price_change": 0, "ad_spend": 6000}, {"price": 100, "weekly_ad_spend": 5000}, "exceed", "ad_absolute_cap"),
    ({"price_change": 0, "ad_spend": 3000}, {"price": 100, "weekly_ad_spend": 500}, "increase cannot exceed", "ad_weekly_increase_cap"),
    ({"price_change": -0.4, "ad_spend": 0}, {"price": 70, "weekly_ad_spend": 0}, "margin", "above_cost"),
    ({"price_change": 0.4, "ad_spend": 0}, {"price": 140, "weekly_ad_spend": 0}, "Price cannot exceed", "price_ceiling"),
]


@pytest.mark.parametrize("a,s,needle,rule", VIOLATIONS)
def test_known_violations_are_rejected_and_name_the_rule(a, s, needle, rule):
    r = CSL.validate_action(a, s)
    assert not r["is_valid"] and (needle in r["message"] or rule in r["message"])
    assert not LEGACY.validate_action(a, s)["is_valid"]


@pytest.mark.xfail(strict=True, reason="UPSTREAM BUG: CSLGuardianEcom._violation_to_message looks up the CSL violation *string* "
                   "(\"Violation 'above_cost': ...\") in a dict keyed by bare rule names, so 4 of 6 rules fall through to a "
                   "generic message. These messages are what the LLM sees from check_business_rules.")
@pytest.mark.parametrize("a,s,needle,rule", VIOLATIONS[2:])
def test_csl_messages_are_human_readable_like_legacy(a, s, needle, rule):
    assert needle in CSL.validate_action(a, s)["message"]


def test_forced_failure_price_below_cost_is_repaired_to_the_margin_floor():
    s = {"price": 60.0, "weekly_ad_spend": 0.0}
    a = {"price_change": -0.40, "ad_spend": 0.0}          # -> $36, below the $50 unit cost
    assert not CSL.validate_action(a, s)["is_valid"]
    fixed, rep = CSL.repair_action(a, s)
    new_price = s["price"] * (1 + fixed["price_change"])
    assert rep["is_valid"] and new_price >= 50.0 / (1 - 0.15)


JAVA = shutil.which("java") if "JAVA_HOME" not in __import__("os").environ else str(Path(__import__("os").environ["JAVA_HOME"]) / "bin" / "java")
JAVA_HOME_BREW = Path("/opt/homebrew/opt/openjdk/bin/java")
JAR = Path(__file__).resolve().parents[2] / "tools" / "tla2tools.jar"


def _java():
    if JAVA_HOME_BREW.exists():
        return str(JAVA_HOME_BREW)
    return None


@pytest.mark.slow
@pytest.mark.skipif(_java() is None or not JAR.exists(), reason="JDK (brew openjdk) and sandbox/tools/tla2tools.jar required")
def test_tlc_model_check(tmp_path):
    """Re-run the paper's TLA+ proof (SymbolicGuardianV4 repair invariants). Paper: 7,639,419 distinct states, no violation.
    Run in a tmp copy so TLC's state files don't touch upstream."""
    import shutil as sh
    import subprocess
    for f in ("ChimeraGuardianProof.tla", "MC.cfg"):
        sh.copy(UP / "TLA+_verification" / f, tmp_path / f)
    out = subprocess.run([_java(), "-XX:+UseParallelGC", "-cp", str(JAR), "tlc2.TLC", "-workers", "auto", "-config", "MC.cfg",
                          "ChimeraGuardianProof.tla"], cwd=tmp_path, capture_output=True, text=True, timeout=1800)
    assert "Model checking completed. No error has been found." in out.stdout, out.stdout[-800:]
