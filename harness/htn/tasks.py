"""A minimal HTN scaffold: fixed depth (<=3), one occurrence per method per run.

This fixes the ProcLLM paper's task-expansion loop (Approach A report, D5): a `Method` here is a
plain function over `(obs, diagnostics, state)` that returns zero or more `Task` leaves. There is
no re-expansion — `run_methods` calls each registered method at most once per run (tracked by
`decomposed`), so there is no way for a method to re-queue itself. Depth is enforced structurally,
not by a counter: T1 diagnose -> T2 methods -> T3 sizing/verify is the whole tree (see
`harness/policy.py`), and no method here is allowed to call another method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass
class Task:
    """One candidate action a method proposes, before precheck/sizing/guardrails."""
    campaign_id: str
    keyword_id: str
    action_type: str
    new_value: float | str
    reason: str
    method: str
    precondition_note: str = ""


@dataclass
class Method:
    name: str
    sg: str                                    # which gap this addresses (SG2/SG3/SG4/...)
    precondition: Callable[..., bool]
    run: Callable[..., list[Task]]
    decomposed: bool = False                   # set True after one call this run; `run_methods` enforces it


@dataclass
class MethodRegistry:
    methods: list[Method] = field(default_factory=list)

    def register(self, method: Method) -> None:
        self.methods.append(method)

    def run_methods(self, *args, **kwargs) -> list[Task]:
        tasks: list[Task] = []
        for m in self.methods:
            if m.decomposed:
                continue
            m.decomposed = True
            if not m.precondition(*args, **kwargs):
                continue
            tasks.extend(m.run(*args, **kwargs))
        return tasks


def tasks_to_frame(tasks: list[Task]) -> pd.DataFrame:
    if not tasks:
        return pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason", "method"])
    return pd.DataFrame([{"campaign_id": t.campaign_id, "keyword_id": t.keyword_id, "action_type": t.action_type,
                          "new_value": t.new_value, "reason": t.reason, "method": t.method} for t in tasks])
