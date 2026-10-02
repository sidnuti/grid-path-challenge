"""Pydantic v2 output contracts for leaves L1-L6. Each has >=1 required field with no default, so
a response missing that field (e.g. `FAULT_INJECT=malformed`'s `{"_fault": "malformed"}`) raises
`ValidationError` and `validate_and_clip` returns the leaf's default rather than a half-filled
object. Numeric fields that *are* present get clipped into range via a `mode="before"` validator
instead of raising — `FAULT_INJECT=out_of_range` should produce a clipped value, not a default.

L1 Value       a per-cell bid judgment, narrower than the grid's own ROAS arithmetic (e.g. "this
               keyword's demand looks like it's shifting, weight the recent window more").
L2 Shock       shock attribution: is this a demand shock, a price shock, or the policy's own prior
               action showing up in the data (E5's confounding).
L3 Sibling     which sibling should lead a contested market when the mechanical leader_score
               (tools/siblings.py) is a near-tie.
L4 Explore     whether to spend a small amount probing a THIN cell this run, and how much.
L5 Ledger      a falsifiable hypothesis about one action's effect, for `memory/ledger.py` to
               check against next run's realised numbers.
L6 Review      veto-only: look at the sized action set and the portfolio headroom used, and
               object if something looks wrong. Never *adds* an action.

None of these are wired into `harness/htn/methods.py` yet (M3) — this module is the contract
future methods will validate against, built and tested (`tests/harness/test_leaves.py`) ahead of
that wiring so the LLM plumbing (M2) can be proven correct independent of it.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

SCHEMA_VERSION = "1"


class LeafSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _clip(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {v!r}")
    return max(lo, min(hi, f))


class L1Value(LeafSchema):
    bid_multiplier: float          # required — a 0 or missing value should fall back to the default
    confidence: float
    rationale: str = ""

    @field_validator("bid_multiplier", mode="before")
    @classmethod
    def _clip_mult(cls, v):
        return _clip(v, 0.5, 1.5)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clip_conf(cls, v):
        return _clip(v, 0.0, 1.0)


class L2Shock(LeafSchema):
    is_shock: bool
    magnitude: float
    direction: str = "none"        # "surge" | "drop" | "none" — not enum-enforced, methods treat unknowns as "none"
    confidence: float = 0.5
    rationale: str = ""

    @field_validator("magnitude", mode="before")
    @classmethod
    def _clip_mag(cls, v):
        return _clip(v, 0.0, 10.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clip_conf(cls, v):
        return _clip(v, 0.0, 1.0)


class L3Sibling(LeafSchema):
    leader_campaign_id: str
    confidence: float = 0.5
    rationale: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _clip_conf(cls, v):
        return _clip(v, 0.0, 1.0)


class L4Explore(LeafSchema):
    explore: bool
    max_spend_inr_day: float = 0.0
    rationale: str = ""

    @field_validator("max_spend_inr_day", mode="before")
    @classmethod
    def _clip_spend(cls, v):
        return _clip(v, 0.0, 5000.0)


class L5Ledger(LeafSchema):
    predicted_lift_pct: float
    claim: str = ""
    confidence: float = 0.5

    @field_validator("predicted_lift_pct", mode="before")
    @classmethod
    def _clip_lift(cls, v):
        return _clip(v, -100.0, 500.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clip_conf(cls, v):
        return _clip(v, 0.0, 1.0)


class L6Review(LeafSchema):
    veto: bool
    reason: str = ""


def validate_and_clip(schema_cls: type[LeafSchema], data: dict, default, known_ids: Optional[set] = None,
                      id_field: Optional[str] = None):
    """Returns a validated+clipped instance of `schema_cls`, or `default` on any validation
    failure or an id-field value outside `known_ids`."""
    try:
        obj = schema_cls.model_validate(data)
    except ValidationError:
        return default
    if known_ids is not None and id_field is not None:
        if getattr(obj, id_field, None) not in known_ids:
            return default
    return obj
