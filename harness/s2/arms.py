"""Named `Params` overrides System 2 chooses between. An arm is a small dict of field-name ->
value, applied to a base `Params` via `dataclasses.replace` — never a second params schema, so
every arm stays expressible in the same `harness/params/*.json` shape `PARAMS_PATH` already reads.

Deliberately not built: a *per-keyword-type* depth override ("L0 for competitor, L2 for brand"),
which the plan's one-liner for this file mentions. `Params.depth` is a single global field; adding
a per-type dimension would mean threading a `depth(keyword_type)` lookup through every depth check
in `harness/policy.py`/`llm_methods.py`, which is real plumbing, not a registry entry — flagged
here rather than faked with an arm whose name implies a capability that doesn't exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..config import Params


@dataclass
class Arm:
    name: str
    overrides: dict = field(default_factory=dict)
    note: str = ""


def materialize(arm: Arm, base: Params) -> Params:
    return replace(base, **arm.overrides)


DEFAULT_ARMS: tuple[Arm, ...] = (
    Arm("baseline_default", {}, "default.json as shipped, no override"),
    Arm("headroom_front_load", {"headroom_front_load": True}, "spend the allowance early, bank less for shocks"),
    Arm("headroom_back_load", {"headroom_front_load": False}, "spend the allowance evenly across remaining runs"),
    Arm("shock_z_2.0", {"shock_z_reach": 2.0, "shock_z_cpm": 2.0}, "more sensitive shock flagging"),
    Arm("shock_z_2.5", {"shock_z_reach": 2.5, "shock_z_cpm": 2.5}, "default sensitivity"),
    Arm("shock_z_3.0", {"shock_z_reach": 3.0, "shock_z_cpm": 3.0}, "less sensitive, fewer false positives"),
    Arm("explore_off", {"explore_enabled": False}, "default: no THIN-cell probing"),
    Arm("explore_on_small", {"explore_enabled": True, "explore_max_thin_cells": 2,
                            "explore_spend_cap_inr_day": 300.0}, "a small, capped exploration budget"),
    Arm("depth_L0", {"depth": "L0"}, "tools-only, no LLM calls regardless of provider config"),
    Arm("depth_L1", {"depth": "L1"}, "+ leaves, no review"),
    Arm("depth_L2", {"depth": "L2"}, "+ leaves + veto-only review"),
)


class ArmRegistry:
    def __init__(self, arms: tuple[Arm, ...] | None = None):
        self._arms = {a.name: a for a in (arms or DEFAULT_ARMS)}

    def __contains__(self, name: str) -> bool:
        return name in self._arms

    def names(self) -> list[str]:
        return list(self._arms)

    def get(self, name: str) -> Arm | None:
        return self._arms.get(name)

    def materialize(self, name: str, base: Params) -> Params:
        arm = self._arms.get(name)
        if arm is None:
            raise KeyError(f"no arm named {name!r}; known arms: {self.names()}")
        return materialize(arm, base)
