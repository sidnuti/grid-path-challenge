"""Leaves: schema validate/clip, and the `leaf()` call-site's fail-soft behaviour under each
`FAULT_INJECT` mode. MockLLM only, matching the plan's M2 test spec.
"""

from __future__ import annotations

import pytest

from harness.leaves.run import leaf
from harness.leaves.schemas import L1Value, L3Sibling, SCHEMA_VERSION, validate_and_clip
from harness.llm.client import Usage
from harness.llm.faults import FaultInjectingClient
from harness.llm.meter import BudgetExceeded

DEFAULT_L1 = L1Value(bid_multiplier=1.0, confidence=0.0, rationale="default")


class MockLLM:
    def __init__(self, response):
        self.response = response

    def complete_json(self, system, user, schema, timeout, **kwargs):
        return dict(self.response), Usage(calls=1, tokens_in=10, tokens_out=5)


def test_schema_version_is_a_constant_not_per_instance():
    assert SCHEMA_VERSION == "1"


def test_validate_and_clip_clips_out_of_range_numeric():
    obj = validate_and_clip(L1Value, {"bid_multiplier": 1e9, "confidence": -5}, DEFAULT_L1)
    assert obj is not DEFAULT_L1
    assert obj.bid_multiplier == 1.5   # clipped to the field's max
    assert obj.confidence == 0.0       # clipped to the field's min


def test_validate_and_clip_returns_default_on_malformed():
    obj = validate_and_clip(L1Value, {"_fault": "malformed"}, DEFAULT_L1)
    assert obj is DEFAULT_L1


def test_validate_and_clip_drops_unknown_id():
    default = L3Sibling(leader_campaign_id="C-FALLBACK", confidence=0.0)
    obj = validate_and_clip(L3Sibling, {"leader_campaign_id": "C-NOT-A-REAL-CAMPAIGN"}, default,
                            known_ids={"C-S1-DEL", "C-S2-MUM"}, id_field="leader_campaign_id")
    assert obj is default


def test_validate_and_clip_keeps_known_id():
    default = L3Sibling(leader_campaign_id="C-FALLBACK", confidence=0.0)
    obj = validate_and_clip(L3Sibling, {"leader_campaign_id": "C-S1-DEL"}, default,
                            known_ids={"C-S1-DEL", "C-S2-MUM"}, id_field="leader_campaign_id")
    assert obj.leader_campaign_id == "C-S1-DEL"


def test_leaf_with_no_llm_returns_default_immediately():
    result, meta = leaf(None, "L1", "sys", "usr", L1Value, DEFAULT_L1)
    assert result is DEFAULT_L1 and meta["outcome"] == "default"


def test_leaf_happy_path_returns_validated_object():
    mock = MockLLM({"bid_multiplier": 1.1, "confidence": 0.8})
    result, meta = leaf(mock, "L1", "sys", "usr", L1Value, DEFAULT_L1)
    assert meta["outcome"] == "ok"
    assert result.bid_multiplier == 1.1


@pytest.mark.parametrize("mode", ["timeout", "exception", "budget", "malformed"])
def test_leaf_each_fault_mode_falls_back_to_default(mode):
    client = FaultInjectingClient(MockLLM({"bid_multiplier": 1.1, "confidence": 0.8}), mode)
    result, meta = leaf(client, "L1", "sys", "usr", L1Value, DEFAULT_L1)
    assert result is DEFAULT_L1
    assert meta["outcome"] == "default"


def test_leaf_out_of_range_fault_clips_rather_than_defaults():
    client = FaultInjectingClient(MockLLM({"bid_multiplier": 1.1, "confidence": 0.8}), "out_of_range")
    result, meta = leaf(client, "L1", "sys", "usr", L1Value, DEFAULT_L1)
    assert meta["outcome"] == "ok"
    assert result.bid_multiplier == 1.5    # the schema's numeric field was present, just extreme -> clipped
    assert result.confidence == 1.0


def test_leaf_malformed_response_still_records_usage_and_raw_response():
    """Regression test: a response that came back and failed *validation* (not a timeout/exception
    before any call happened) still made a real, billed call — its usage must not be discarded
    just because the content was bad. (Found alongside the meter/replay cost-undercounting bugs.)"""
    client = FaultInjectingClient(MockLLM({"bid_multiplier": 1.1, "confidence": 0.8}), "malformed")
    result, meta = leaf(client, "L1", "sys", "usr", L1Value, DEFAULT_L1)
    assert meta["outcome"] == "default"
    assert meta["usage"] is not None and meta["usage"]["calls"] == 1
    assert meta["raw_response"] == {"_fault": "malformed"}
