"""The harness policy. `HTNToolsOnly` is the L0 (no-LLM) ablation arm — M1 of the build plan — and
the fallback target for `HTNHarness`. `HTNHarness` adds L1 (leaves) and L2 (+ review) on top of
the same L0 mechanics when `params.depth` says so and an LLM is actually configured
(`LLM_MODE` != "off"); with no LLM configured it is byte-for-byte the same policy as
`HTNToolsOnly` — not a separate code path that happens to produce the same thing, but literally
`_tools_only_recommend` under the hood (see `_harness_recommend`'s `llm is None` branch). Fail-soft
per the plan: any exception anywhere in `recommend` falls back to `gpc.policy.DeterministicTraversal`,
so a bug or an LLM failure degrades to the baseline rather than to nothing.

**Fixed 2026-10-03** (an independent review found this): raise candidates used to go through
`tools.sizing.select_raises` *before* `tools.precheck.filter_precheck` — so the headroom
allowance, already tight after the sizing fix the same day, was being spent ranking candidates
that would be blocked anyway (measured: half of one run's `m_reprice_raises` candidates were
already G3-doomed, cells already holding slot 1). A doomed candidate consuming budget could crowd
out a genuinely shippable one lower in the ranking. `filter_precheck` now runs on the raise
candidates immediately after projection, *before* `select_raises` ever sees them; the
budget-constrained sizing step only ever competes among candidates that could actually ship.
"""

from __future__ import annotations

import logging
import uuid

import pandas as pd

from gpc.observation import Observation
from gpc.policy import DeterministicTraversal, Policy

from .config import Params, load_params
from .htn.llm_methods import adjust_raise_sizes, explore_candidates, review_veto, shock_raises, sibling_tiebreak
from .htn.methods import m_base_cuts, m_budget_raises, m_reprice_raises, m_sibling_holds
from .llm import build_llm_stack, reset_run_budget
from .tools.features import diagnose
from .tools.headroom import compute_headroom
from .tools.incrementality import iota_lookup
from .tools.precheck import filter_precheck
from .tools.shocks import detect_shocks
from .tools.sizing import project_candidates, select_raises
from .trace.writer import maybe_write_trace

logger = logging.getLogger(__name__)

ACTION_COLS = ["campaign_id", "keyword_id", "action_type", "new_value", "reason"]


def _concat(frames: list[pd.DataFrame], fallback: pd.DataFrame) -> pd.DataFrame:
    non_empty = [f for f in frames if len(f)]
    if not non_empty:
        return fallback
    return pd.concat(non_empty, ignore_index=True) if len(non_empty) > 1 else non_empty[0]


def _log_actions(action_log: dict, obs: Observation, actions: pd.DataFrame) -> None:
    for a in actions.itertuples():
        if a.action_type in ("increase_cpm", "reduce_cpm"):
            action_log.setdefault((a.campaign_id, a.keyword_id), []).append(obs.day)


def _tools_only_recommend(obs: Observation, params: Params) -> tuple[pd.DataFrame, dict]:
    diag = diagnose(obs)
    iota = iota_lookup(obs)
    hold, mk = m_sibling_holds(obs, diag, params)

    reprice = m_reprice_raises(obs, diag, hold, iota)
    budget = m_budget_raises(obs, diag, params, iota)
    raises = _concat([reprice, budget], reprice)
    raises = project_candidates(obs, diag.grid, diag.pacing, raises)
    raises_ok, raises_dropped = filter_precheck(obs, diag.verdicts, diag.pacing, raises)

    headroom = compute_headroom(obs, params)
    selected = select_raises(raises_ok, headroom.allowance_inr_day, params)

    cuts = m_base_cuts(obs, diag)

    candidates = _concat([selected, cuts], selected)
    kept, dropped = filter_precheck(obs, diag.verdicts, diag.pacing, candidates)
    dropped = _concat([raises_dropped, dropped], dropped)

    actions = kept[ACTION_COLS].copy() if len(kept) else pd.DataFrame(columns=ACTION_COLS)
    trace = {"diagnostics": diag, "iota": iota, "sibling_holds": hold, "sibling_markets": mk,
             "headroom": headroom, "candidates_raised": raises, "candidates_cut": cuts,
             "precheck_dropped": dropped, "depth": "L0"}
    return actions, trace


def _harness_recommend(obs: Observation, params: Params, llm, action_log: dict,
                       replicate: int = 0) -> tuple[pd.DataFrame, dict]:
    if llm is None or params.depth == "L0":
        return _tools_only_recommend(obs, params)

    leaf_calls: list = []
    diag = diagnose(obs)
    iota = iota_lookup(obs)
    hold, mk = m_sibling_holds(obs, diag, params)
    mk = sibling_tiebreak(obs, mk, llm, replicate=replicate, metas=leaf_calls)
    from .tools.siblings import followers_to_hold
    hold = followers_to_hold(mk, params.sibling_leader_min_slot1_share)

    reprice = m_reprice_raises(obs, diag, hold, iota)
    reprice = adjust_raise_sizes(obs, diag, reprice, llm, replicate=replicate, metas=leaf_calls)
    budget = m_budget_raises(obs, diag, params, iota)

    shocks = detect_shocks(obs, params, own_action_days=action_log)
    shock_raise = shock_raises(obs, diag, shocks, llm, iota, replicate=replicate, metas=leaf_calls)

    raises = _concat([reprice, budget, shock_raise], reprice)
    raises = project_candidates(obs, diag.grid, diag.pacing, raises)
    raises_ok, raises_dropped = filter_precheck(obs, diag.verdicts, diag.pacing, raises)

    headroom = compute_headroom(obs, params)
    selected = select_raises(raises_ok, headroom.allowance_inr_day, params)
    selected = review_veto(obs, headroom, selected, params, llm, replicate=replicate, metas=leaf_calls)

    explore = explore_candidates(obs, diag, params, llm, replicate=replicate, metas=leaf_calls)
    cuts = m_base_cuts(obs, diag)

    candidates = _concat([selected, explore, cuts], selected)
    kept, dropped = filter_precheck(obs, diag.verdicts, diag.pacing, candidates)
    dropped = _concat([raises_dropped, dropped], dropped)

    actions = kept[ACTION_COLS].copy() if len(kept) else pd.DataFrame(columns=ACTION_COLS)
    trace = {"diagnostics": diag, "iota": iota, "sibling_holds": hold, "sibling_markets": mk,
             "headroom": headroom, "shocks": shocks, "candidates_raised": raises,
             "candidates_explore": explore, "candidates_cut": cuts, "precheck_dropped": dropped,
             "depth": params.depth, "leaf_calls": leaf_calls}
    return actions, trace


class HTNToolsOnly(Policy):
    """L0: tools only, no LLM, no network. The ablation arm and the fail-soft floor."""
    name = "htn_tools_only"

    def __init__(self, params: Params | None = None):
        self.params = params or load_params()
        self._simulation_id = uuid.uuid4().hex[:12]

    def recommend(self, obs: Observation) -> pd.DataFrame:
        try:
            actions, trace = _tools_only_recommend(obs, self.params)
            self.last_trace = trace
            maybe_write_trace(self.name, self._simulation_id, obs, self.params, None, actions, trace)
            return actions
        except Exception:
            logger.exception("HTNToolsOnly failed on run %s; falling back to DeterministicTraversal", obs.run)
            fallback = DeterministicTraversal()
            actions = fallback.recommend(obs)
            self.last_trace = {"fallback_reason": "exception", "baseline_trace": fallback.last_trace}
            maybe_write_trace(self.name, self._simulation_id, obs, self.params, None, actions, self.last_trace)
            return actions


class HTNHarness(Policy):
    """Full harness. With no LLM configured (`LLM_MODE=off`, the default) or `params.depth ==
    "L0"`, behaves exactly like `HTNToolsOnly`. With `params.depth in ("L1", "L2")` and an LLM
    configured (`harness/llm/build_llm_stack`), adds leaf-aided sibling tie-breaks, shock-surge
    raises, tier-B raise-size dampening, capped THIN-cell exploration, and (L2 only) a veto-only
    review pass over large raises — see `harness/htn/llm_methods.py`. Keeps its own
    `(campaign_id, keyword_id) -> [day, ...]` log of bid/budget changes it has made, across runs
    in the same `simulate()` call, so `tools/shocks.py` can tell a real market shock apart from
    the harness watching its own last move land (E5)."""
    name = "htn_harness"

    def __init__(self, params: Params | None = None, llm=None, replicate: int = 0):
        self.params = params or load_params()
        self._llm_override = llm
        self._llm_initialized = llm is not None
        self._action_log: dict[tuple[str, str], list[int]] = {}
        self.replicate = replicate
        self._simulation_id = uuid.uuid4().hex[:12]

    def _llm(self):
        if not self._llm_initialized:
            self._llm_override, self._mode = build_llm_stack(self.params)
            self._llm_initialized = True
        return self._llm_override

    def recommend(self, obs: Observation) -> pd.DataFrame:
        try:
            llm = self._llm()
            reset_run_budget(llm)
            actions, trace = _harness_recommend(obs, self.params, llm, self._action_log, self.replicate)
            self.last_trace = trace
            _log_actions(self._action_log, obs, actions)
            maybe_write_trace(self.name, self._simulation_id, obs, self.params, llm, actions, trace)
            return actions
        except Exception:
            logger.exception("HTNHarness failed on run %s; falling back to DeterministicTraversal", obs.run)
            fallback = DeterministicTraversal()
            actions = fallback.recommend(obs)
            self.last_trace = {"fallback_reason": "exception", "baseline_trace": fallback.last_trace}
            maybe_write_trace(self.name, self._simulation_id, obs, self.params, None, actions, self.last_trace)
            return actions
