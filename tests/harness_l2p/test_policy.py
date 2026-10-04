from harness.llm.client import Usage
from harness.policy import _tools_only_recommend
from harness_l2p.intents import IntentPlan
from harness_l2p.policy import L2PHarness


class FailingLLM:
    def complete_json(self, *a, **k):
        raise TimeoutError("injected")


class FixedLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, *a, **k):
        return self.payload, Usage(calls=1, tokens_in=10, tokens_out=10)


def _same(a, b):
    cols = ["campaign_id", "keyword_id", "action_type", "new_value"]
    return a[cols].reset_index(drop=True).equals(b[cols].reset_index(drop=True))


def test_failing_llm_ships_exactly_l0_in_both_modes(observations):
    obs = observations[1]
    for merge in ("augment", "native"):
        pol = L2PHarness(planner="llm", merge=merge, llm=FailingLLM())
        acts = pol.recommend(obs)
        l0, _ = _tools_only_recommend(obs, pol.params)
        assert _same(acts, l0), merge
        assert pol.last_trace["fallback_reason"] == "planner_default"


def test_malformed_llm_output_is_the_empty_plan(observations):
    obs = observations[1]
    pol = L2PHarness(planner="llm", merge="native", llm=FixedLLM({"_fault": "malformed"}))
    acts = pol.recommend(obs)
    l0, _ = _tools_only_recommend(obs, pol.params)
    assert _same(acts, l0)        # a validation failure is a planner default → L0


def test_native_legitimate_empty_plan_ships_nothing(observations):
    pol = L2PHarness(planner=lambda b: IntentPlan(intents=[]), merge="native")
    assert pol.recommend(observations[1]).empty


def test_augment_empty_plan_is_exactly_l0(observations):
    obs = observations[1]
    pol = L2PHarness(planner=lambda b: IntentPlan(intents=[]), merge="augment")
    l0, _ = _tools_only_recommend(obs, pol.params)
    assert _same(pol.recommend(obs), l0)


def test_exception_inside_falls_back_to_l0(observations):
    obs = observations[1]
    def boom(brief):
        raise RuntimeError("planner bug")
    pol = L2PHarness(planner=boom, merge="native")
    l0, _ = _tools_only_recommend(obs, pol.params)
    assert _same(pol.recommend(obs), l0)
    assert pol.last_trace["fallback_to"] == "l0"


def test_llm_plan_compiles_and_repairs(observations):
    payload = {"intents": [{"id": "a", "verb": "cut_bid", "scope": {"campaign_id": "C-S3-DEL", "keyword_id": "K03"}},
                           {"id": "z", "verb": "raise_bid", "scope": {"sku_id": "S9"}}]}
    pol = L2PHarness(planner="llm", merge="native", llm=FixedLLM(payload))
    acts = pol.recommend(observations[1])
    assert (acts.reason.str.startswith("L2P:a")).any()
    assert len(pol.last_trace["leaf_calls"]) == 2            # plan + one repair (the S9 intent was rejected)
