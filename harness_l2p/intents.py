"""The L2′ output contract: an `IntentPlan` the LLM (or the rules planner) proposes and the L0
compiler (`compiler.py`) turns into actions. An intent says *what* to do and *where* (a verb on a
scope: SKU x city, keyword, keyword type, sub-category, market); it never carries a raw rupee
value. Sizes are coarse tiers (small / medium / large) or a target ad slot, and the compiler picks
the concrete value from the engine's own bid grid and the guardrail limits.

Validation follows `harness.leaves.schemas`: a malformed plan becomes the empty plan (the caller's
default), a malformed *intent* is dropped on its own, numbers are clipped, the list is capped.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from harness.leaves.schemas import LeafSchema

SCHEMA_VERSION = "l2p-1"
MAX_INTENTS = 25

VERBS = ("raise_bid", "cut_bid", "pause", "raise_budget", "cut_budget", "set_dayparts",
         "lead_market", "yield_market", "hold")
SIZES = ("small", "medium", "large")
SLOTS = (1, 5, 9, 13)
DAYPARTS = ("night", "morning", "afternoon", "evening")
STANCES = ("defend_min", "lead", "scale", "hold", "trim", "conquest", "explore")


class Scope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    campaign_id: Optional[str] = None
    sku_id: Optional[str] = None
    city_id: Optional[str] = None
    keyword_id: Optional[str] = None
    keyword_type: Optional[str] = None
    sub_category: Optional[str] = None

    def is_empty(self) -> bool:
        return not any(getattr(self, f) for f in type(self).model_fields)


class Intent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    verb: str
    scope: Scope
    size: str = "medium"
    target_slot: Optional[int] = None
    dayparts: list[str] = []
    evidence_refs: list[str] = []
    confidence: float = 0.5
    expected_effect: str = ""

    @field_validator("size", mode="before")
    @classmethod
    def _size(cls, v):
        return v if v in SIZES else "medium"

    @field_validator("target_slot", mode="before")
    @classmethod
    def _slot(cls, v):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if v in SLOTS else None

    @field_validator("dayparts", mode="before")
    @classmethod
    def _dps(cls, v):
        return [d for d in (v or []) if d in DAYPARTS]

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class StanceRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub_category: str
    keyword_type: str
    sku_role: str = "any"
    stance: str

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, v):
        if v not in STANCES:
            raise ValueError(f"unknown stance {v!r}")
        return v


class IntentPlan(LeafSchema):
    intents: list[Intent]
    stance: list[StanceRow] = []
    notes: str = ""

    @field_validator("intents", mode="before")
    @classmethod
    def _intents(cls, v):
        """Drop intents with an unknown verb or a missing id/scope instead of failing the whole
        plan; cap the count."""
        if not isinstance(v, list):
            raise ValueError("intents must be a list")
        keep = []
        for i, it in enumerate(v):
            if not isinstance(it, dict) or it.get("verb") not in VERBS or not isinstance(it.get("scope"), dict):
                continue
            it = dict(it)
            it.setdefault("id", f"i{i + 1}")
            it["id"] = str(it["id"])[:24]
            keep.append(it)
        return keep[:MAX_INTENTS]

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, v):
        out = []
        for row in v or []:
            try:
                out.append(StanceRow.model_validate(row))
            except Exception:  # noqa: BLE001 - a bad stance row is dropped, never fatal
                continue
        return out


EMPTY_PLAN = IntentPlan(intents=[], notes="empty plan (default)")
