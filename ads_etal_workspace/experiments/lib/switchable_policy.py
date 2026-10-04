"""An L0 policy with an on/off switch per module, built from the harness's own functions (never a
reimplementation of their logic). It mirrors the *pipeline order* of `harness.policy._tools_only_recommend`,
which another session changes from time to time; the equivalence test below is the drift alarm. With every switch on it must equal `harness.policy.HTNToolsOnly`
action for action; `tests/test_lib.py` asserts that, so an ablation here is a real ablation of the
shipped pipeline and not of a lookalike."""

from __future__ import annotations

from dataclasses import dataclass, fields

import pandas as pd

from gpc.observation import Observation
from gpc.policy import Policy

from harness.config import Params, load_params
from harness.htn.methods import m_base_cuts, m_budget_raises, m_reprice_raises, m_sibling_holds
from harness.tools.features import diagnose
from harness.tools.headroom import compute_headroom
from harness.tools.incrementality import iota_lookup
from harness.tools.precheck import filter_precheck
from harness.tools.sizing import project_candidates, select_raises

ACTION_COLS = ["campaign_id", "keyword_id", "action_type", "new_value", "reason"]


@dataclass(frozen=True)
class Switches:
    reprice: bool = True          # M_Reprice bid raises
    budget: bool = True           # M_Budget budget raises
    cuts: bool = True             # M_Base ladder-paced cuts
    sibling_holds: bool = True    # hold non-leader followers in contested markets
    headroom_gate: bool = True    # False = allowance is unlimited (raises are never gated)
    precheck: bool = True         # drop candidates G0/G3/G4/G5/G7 would block
    generic_cuts: bool = True     # False = M_Base cuts skip generic keywords (X3.3/X3.1: generic spend still earns ~0.9 offtake per INR)

    def label(self) -> str:
        off = [f.name for f in fields(self) if not getattr(self, f.name)]
        return "full" if not off else "-" + "-".join(off)


def _concat(frames, fallback):
    non_empty = [f for f in frames if len(f)]
    if not non_empty:
        return fallback
    return pd.concat(non_empty, ignore_index=True) if len(non_empty) > 1 else non_empty[0]


@dataclass(frozen=True)
class StateMin:
    """State-dependent minimum allowance (NEXT_STEPS 1b). Run 1 has nothing banked, so it gets a fixed
    `run1_min`. From run 2 the minimum is `min(min_amt, cap_frac * headroom_inr_day)`: it can only be as
    large as a fraction of the headroom actually banked, so a thin-margin world (little banked) gets
    little extra spend while a roomy one gets up to `min_amt`. `base_min` is the harness's own 300."""
    run1_min: float = 300.0
    cap_frac: float = 0.5
    min_amt: float = 3000.0
    base_min: float = 300.0


def state_min_allowance(run: int, headroom_day: float, sched_allowance: float, sm: StateMin) -> float:
    """Allowance = max(the schedule's slice of banked headroom, the state-dependent minimum)."""
    floor_eff = sm.run1_min if run <= 1 else min(sm.min_amt, sm.cap_frac * max(headroom_day, 0.0))
    return max(sched_allowance, sm.base_min, floor_eff)


def recommend(obs: Observation, params: Params, sw: Switches, sm: StateMin | None = None) -> tuple[pd.DataFrame, dict]:
    diag = diagnose(obs)
    iota = iota_lookup(obs)
    hold, mk = m_sibling_holds(obs, diag, params)
    if not sw.sibling_holds:
        hold = set()

    reprice = m_reprice_raises(obs, diag, hold, iota)
    budget = m_budget_raises(obs, diag, params, iota)
    if not sw.reprice:
        reprice = reprice.iloc[0:0]
    if not sw.budget:
        budget = budget.iloc[0:0]
    raises = project_candidates(obs, diag.grid, diag.pacing, _concat([reprice, budget], reprice))
    # mirrors harness.policy._tools_only_recommend (as of the 2026-10-03 sizing rewrite): precheck
    # the raises *before* sizing so allowance is never spent on a raise a guardrail would block
    if sw.precheck:
        raises_ok, raises_dropped = filter_precheck(obs, diag.verdicts, diag.pacing, raises)
    else:
        raises_ok, raises_dropped = raises, raises.iloc[0:0]

    headroom = compute_headroom(obs, params)
    allowance = headroom.allowance_inr_day if sw.headroom_gate else 1e12
    if sm is not None and sw.headroom_gate:
        # params.headroom_min_allowance_inr_day is 0 for these arms, so headroom.allowance_inr_day is the
        # pure schedule slice; the state-dependent minimum replaces the harness's fixed one
        allowance = state_min_allowance(obs.run, headroom.headroom_inr_day, headroom.allowance_inr_day, sm)
    selected = select_raises(raises_ok, allowance, params)

    cuts = m_base_cuts(obs, diag)
    if not sw.cuts:
        cuts = cuts.iloc[0:0]
    elif not sw.generic_cuts and len(cuts):
        kt = obs.public["keywords"].set_index("keyword_id").keyword_type
        cuts = cuts[cuts.keyword_id.map(kt) != "generic"]

    candidates = _concat([selected, cuts], selected)
    if sw.precheck:
        kept, dropped = filter_precheck(obs, diag.verdicts, diag.pacing, candidates)
        dropped = _concat([raises_dropped, dropped], dropped)
    else:
        kept, dropped = candidates, candidates.iloc[0:0]
    actions = kept[ACTION_COLS].copy() if len(kept) else pd.DataFrame(columns=ACTION_COLS)
    trace = {"diagnostics": diag, "headroom": headroom, "candidates_raised": raises, "candidates_cut": cuts,
             "precheck_dropped": dropped, "sibling_holds": hold, "selected": selected}
    return actions, trace


class SwitchablePolicy(Policy):
    def __init__(self, switches: Switches | None = None, params: Params | None = None, state_min: StateMin | None = None):
        self.sw = switches or Switches()
        self.sm = state_min
        self.params = params or load_params()
        self.name = f"switchable_{self.sw.label()}"
        self.last_trace: dict = {}

    def recommend(self, obs: Observation) -> pd.DataFrame:
        actions, self.last_trace = recommend(obs, self.params, self.sw, self.sm)
        return actions


ARMS: dict[str, Switches] = {
    "full": Switches(),
    "reprice_only": Switches(budget=False, cuts=False),
    "budget_only": Switches(reprice=False, cuts=False),
    "cuts_only": Switches(reprice=False, budget=False),
    "no_sibling_holds": Switches(sibling_holds=False),
    "no_headroom_gate": Switches(headroom_gate=False),
    "no_precheck": Switches(precheck=False),
    "no_budget": Switches(budget=False),
    "no_cuts": Switches(cuts=False),
    "no_reprice": Switches(reprice=False),
    "no_gate_no_cuts": Switches(headroom_gate=False, cuts=False),
    "no_generic_cuts": Switches(generic_cuts=False),
}


# Gate-sweep arms: full L0 (cuts kept) with the headroom gate's own parameters changed. Nothing in
# harness/ is edited; `Params` is the harness's own configuration object. `frac_scale` multiplies
# run_allowance_frac (the share of banked headroom each run may spend; the last run already spends
# all of it), so >1 deliberately spends more than has been banked.
PARAM_ARMS: dict[str, dict] = {
    "gate_x1.5": {"frac_scale": 1.5},
    "gate_x2": {"frac_scale": 2.0},
    "gate_x3": {"frac_scale": 3.0},
    "gate_min1000": {"min_allowance": 1000.0},
    "gate_min2000": {"min_allowance": 2000.0},
    "gate_min3000": {"min_allowance": 3000.0},
    "gate_min5000": {"min_allowance": 5000.0},
    "gate_margin0": {"margin": 0.0},
    "gate_x2_min1000": {"frac_scale": 2.0, "min_allowance": 1000.0},
}


def make_params(frac_scale: float = 1.0, min_allowance: float | None = None, margin: float | None = None) -> Params:
    from dataclasses import replace
    p = load_params()
    kw = {"run_allowance_frac": tuple(f * frac_scale for f in p.run_allowance_frac)}
    if min_allowance is not None:
        kw["headroom_min_allowance_inr_day"] = min_allowance
    if margin is not None:
        kw["headroom_margin"] = margin
    return replace(p, **kw)


# 1b arms: full L0 with a state-dependent minimum allowance (harness minimum zeroed, replaced by StateMin)
STATE_ARMS: dict[str, StateMin] = {
    f"sm_r{int(r1)}_c{c}": StateMin(run1_min=r1, cap_frac=c, min_amt=3000.0)
    for r1 in (300.0, 1500.0) for c in (0.25, 0.5, 1.0)
}
# round 2 (the first grid was still rising at its upper edge)
STATE_ARMS.update({f"sm_r{int(r1)}_c{c}": StateMin(run1_min=r1, cap_frac=c, min_amt=3000.0)
                   for r1 in (1500.0, 3000.0) for c in (2.0, 4.0)})
