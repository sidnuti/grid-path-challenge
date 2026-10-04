"""`L2PHarness`: L0 tools + the L2′ expressive arm, with L1/L2 leaves always off.

    planner  "llm"   the LLM writes the intent plan (planner.py)
             "rules" the deterministic stance-table planner (rules_planner.py): the LLM ablation
             a callable(brief) -> IntentPlan: scripted planners for bounds (offline experiments)
    merge    "augment" intents are added to L0's own candidates and override them on the same lever
             "native"  intents only: L0 is reduced to compiler + safety (LLM-native exploration)

Fail-soft, in layers:
    planner error (leaf default with a reason)  → this run ships exactly L0's actions
    a legitimate empty plan                     → augment: exactly L0; native: no actions
    any exception anywhere                      → L0's actions; if L0 itself raises, DeterministicTraversal
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace

import pandas as pd

from gpc.observation import Observation
from gpc.policy import DeterministicTraversal, Policy

from harness.config import Params, load_params
from harness.htn.methods import m_base_cuts, m_budget_raises, m_reprice_raises, m_sibling_holds
from harness.llm import reset_run_budget
from harness.llm.meter import run_usage_of
from harness.policy import ACTION_COLS, _log_actions, _tools_only_recommend
from harness.tools.features import diagnose
from harness.tools.incrementality import iota_lookup
from harness.tools.precheck import filter_precheck
from harness.tools.sizing import project_candidates

from .brief import build_brief
from .compiler import compile_plan
from .intents import IntentPlan
from .llm import build_l2p_stack
from .planner import plan_with_llm, repair_feedback
from .rules_planner import rules_plan

logger = logging.getLogger(__name__)


def _l0_candidates(obs: Observation, diag, iota: dict, params: Params) -> dict:
    """L0's raise candidates (projected, prechecked, not yet sized) and its cuts, built with the
    same functions `harness.policy._tools_only_recommend` uses, so augment mode competes them
    against intents instead of shipping a pre-sized set."""
    hold, _ = m_sibling_holds(obs, diag, params)
    reprice = m_reprice_raises(obs, diag, hold, iota)
    budget = m_budget_raises(obs, diag, params, iota)
    parts = [d for d in (reprice, budget) if len(d)]
    raises = pd.concat(parts, ignore_index=True) if parts else reprice
    raises = project_candidates(obs, diag.grid, diag.pacing, raises)
    raises_ok, _ = filter_precheck(obs, diag.verdicts, diag.pacing, raises)
    cuts = m_base_cuts(obs, diag)
    cuts_ok, _ = filter_precheck(obs, diag.verdicts, diag.pacing, cuts)
    return {"raises": raises_ok.drop(columns=["current_value"], errors="ignore"),
            "cuts": cuts_ok.drop(columns=["current_value"], errors="ignore")}


class L2PHarness(Policy):
    def __init__(self, params: Params | None = None, planner="llm", merge: str = "augment", llm=None,
                 replicate: int = 0, repair: bool = True, name: str | None = None):
        assert merge in ("augment", "native")
        self.params = replace(params or load_params(), depth="L0")      # L1/L2 leaves are never used here
        self.planner, self.merge, self.repair, self.replicate = planner, merge, repair, replicate
        self._llm, self._llm_ready = llm, llm is not None
        self._action_log: dict = {}
        self._last_run: dict = {}                     # previous run's allowance use, shown in the next brief
        self._sim = uuid.uuid4().hex[:12]
        p = planner if isinstance(planner, str) else getattr(planner, "label", "scripted")
        self.name = name or f"l2p_{merge}_{p}"

    def _client(self):
        if not self._llm_ready:
            self._llm, _ = build_l2p_stack(self.params)
            self._llm_ready = True
        return self._llm

    def _plan(self, brief, feedback: str = "", leaf_name: str = "L2P_plan") -> tuple[IntentPlan, dict]:
        if self.planner == "rules":
            return rules_plan(brief), {"leaf": "rules", "outcome": "ok"}
        if callable(self.planner):
            return self.planner(brief), {"leaf": "scripted", "outcome": "ok"}
        return plan_with_llm(self._client(), brief, feedback, self.replicate, leaf_name)

    def recommend(self, obs: Observation) -> pd.DataFrame:
        try:
            actions, trace = self._recommend(obs)
        except Exception as e:  # noqa: BLE001 - fail soft to L0, then to the baseline
            logger.exception("L2PHarness failed on run %s; falling back to L0", obs.run)
            try:
                actions, l0t = _tools_only_recommend(obs, self.params)
                trace = {"fallback_reason": f"exception: {type(e).__name__}", "fallback_to": "l0"}
            except Exception:  # noqa: BLE001
                fb = DeterministicTraversal()
                actions = fb.recommend(obs)
                trace = {"fallback_reason": "exception", "fallback_to": "baseline"}
        _log_actions(self._action_log, obs, actions)
        self.last_trace = trace
        return actions

    def _recommend(self, obs: Observation) -> tuple[pd.DataFrame, dict]:
        if self.planner == "llm":
            reset_run_budget(self._client())
        diag = diagnose(obs)
        iota = iota_lookup(obs)
        brief = build_brief(obs, diag, iota, self.params, own_action_days=self._action_log, last_run=self._last_run)
        plan, meta = self._plan(brief)
        metas = [meta]
        trace = {"depth": "L2P", "merge": self.merge, "brief_digest": brief.digest, "brief_chars": len(brief.text),
                 "simulation_id": self._sim, "leaf_calls": metas}
        planner_failed = meta.get("outcome") == "default"   # call error, timeout, budget, or output that failed validation
        if planner_failed or (not plan.intents and self.merge == "augment"):
            actions, _ = _tools_only_recommend(obs, self.params)
            trace.update({"fallback_reason": "planner_default" if planner_failed else None, "plan": plan.model_dump(),
                          "compile": None, "shipped_from": "l0", "usage": run_usage_of(self._llm)})
            return actions, trace
        l0 = _l0_candidates(obs, diag, iota, self.params) if self.merge == "augment" else None
        res = compile_plan(obs, diag, brief, iota, plan, self.merge, l0)
        if self.repair and self.planner == "llm" and res.rejected:
            plan2, meta2 = self._plan(brief, repair_feedback(res.rejected), leaf_name="L2P_repair")
            metas.append(meta2)
            if meta2.get("outcome") == "ok" and plan2.intents:
                # keep what compiled from the first plan, add the repaired intents, recompile the union
                worked = {r["id"] for r in res.report if r["kept"] or r["held"]}
                merged = [i for i in plan.intents if i.id in worked] + \
                         [i.model_copy(update={"id": f"R{i.id}"[:24]}) for i in plan2.intents]
                plan_u = IntentPlan(intents=[i.model_dump() for i in merged], stance=plan.stance or plan2.stance,
                                    notes=plan2.notes or plan.notes)
                res2 = compile_plan(obs, diag, brief, iota, plan_u, self.merge, l0)
                trace["first_compile"] = {"rejected": res.rejected[:30], "n_actions": len(res.actions),
                                          "n_from_intents": int(res.actions.reason.str.startswith("L2P:").sum()) if len(res.actions) else 0,
                                          "allowance_used": res.allowance_used,
                                          "n_intents": len(plan.intents), "n_repair_intents": len(plan2.intents)}
                plan, res = plan_u, res2
        self._last_run = {"allowance_used": res.allowance_used, "allowance_total": res.allowance_total}
        actions = res.actions[ACTION_COLS] if len(res.actions) else pd.DataFrame(columns=ACTION_COLS)
        trace.update({"plan": plan.model_dump(), "shipped_from": "compiler",
                      "compile": {"report": res.report, "rejected": res.rejected[:40], "l0_overridden": res.l0_overridden,
                                  "l0_held": res.l0_held, "allowance_used": res.allowance_used,
                                  "allowance_total": res.allowance_total,
                                  "n_from_intents": int(actions.reason.str.startswith("L2P:").sum()) if len(actions) else 0},
                      "headroom": brief.portfolio, "usage": run_usage_of(self._llm)})
        return actions, trace
