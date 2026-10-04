from harness.leaves.schemas import validate_and_clip
from harness_l2p.intents import EMPTY_PLAN, MAX_INTENTS, IntentPlan


def test_unknown_verbs_and_bad_items_are_dropped_not_fatal():
    p = IntentPlan.model_validate({"intents": [
        {"id": "a", "verb": "raise_bid", "scope": {"sku_id": "S1"}},
        {"id": "b", "verb": "teleport", "scope": {"sku_id": "S1"}},
        {"id": "c", "verb": "pause"},
        "not a dict"]})
    assert [i.id for i in p.intents] == ["a"]


def test_cap_clip_and_defaults():
    p = IntentPlan.model_validate({"intents": [{"verb": "cut_bid", "scope": {"sku_id": "S1"}, "confidence": 7,
                                                "size": "huge", "target_slot": 3, "dayparts": ["night", "dawn"]}] * 40})
    assert len(p.intents) == MAX_INTENTS
    i = p.intents[0]
    assert (i.confidence, i.size, i.target_slot, i.dayparts) == (1.0, "medium", None, ["night"])
    assert i.id == "i1"


def test_malformed_plan_becomes_the_empty_default():
    assert validate_and_clip(IntentPlan, {"_fault": "malformed"}, EMPTY_PLAN) is EMPTY_PLAN
    assert validate_and_clip(IntentPlan, {"intents": "nope"}, EMPTY_PLAN) is EMPTY_PLAN


def test_bad_stance_rows_dropped():
    p = IntentPlan.model_validate({"intents": [], "stance": [
        {"sub_category": "Soap", "keyword_type": "brand", "stance": "defend_min"},
        {"sub_category": "Soap", "keyword_type": "brand", "stance": "yolo"}]})
    assert len(p.stance) == 1
