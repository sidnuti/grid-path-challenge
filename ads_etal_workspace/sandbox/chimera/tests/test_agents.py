"""Agent layer of preprint/three_agent_comparative_benchmark.py with a scripted chat model (no network):
tool-call loop, invalid-hypothesis handling, JSON parsing, and a forced failure repaired by the guardian."""
import json

import pytest
from langchain_core.messages import ToolMessage

from adapters.scripted_llm import ScriptedChatModel, say, tool_call

pytestmark = pytest.mark.offline


@pytest.fixture
def bench(monkeypatch):
    import preprint.three_agent_comparative_benchmark as b
    return b


def install_script(monkeypatch, bench, turns):
    llm = ScriptedChatModel(turns=turns, seen=[])
    monkeypatch.setattr(bench, "ChatOpenAI", lambda *a, **k: llm)
    return llm


def final(pc, ad, **extra):
    return say(json.dumps({"commentary": "scripted", "action": {"price_change": pc, "ad_spend": ad},
                           "predicted_profit_change": 0.0, **extra}))


STATE = {"week": 1, "price": 100.0, "weekly_ad_spend": 500.0, "brand_trust": 0.7, "sales_volume": 0, "profit": 0.0, "season_phase": 0}


# ---- JSON extraction -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ('{"action": {"price_change": -0.1, "ad_spend": 300}}', (-0.1, 300.0)),
    ('Here you go:\n```json\n{"commentary": "x", "action": {"price_change": "0.05", "ad_spend": "700"}}\n```', (0.05, 700.0)),
    ('{"action": {"price_change": null, "ad_spend": 200}}', (0.0, 200.0)),
    ('{"action": {"price_change": "abc", "ad_spend": 200}}', (0.0, 200.0)),
    ('{"action": "none"}', (0.0, 0.0)),
    ("I think we should lower prices.", (0.0, 0.0)),
    ("{not json}", (0.0, 0.0)),
    ("", (0.0, 0.0)),
])
def test_get_decision_from_response(bench, text, expected):
    a = bench.get_decision_from_response({"output": text})
    assert (a["price_change"], a["ad_spend"]) == expected


# ---- agent tool loops ------------------------------------------------------------------------------------------
def test_llm_only_agent_runs_and_parses(monkeypatch, bench):
    llm = install_script(monkeypatch, bench, [final(-0.08, 400)])
    agent = bench.create_llm_only_agent("decrease", "unused")
    out = agent.invoke({"input": "state..."})
    assert bench.get_decision_from_response(out) == {"price_change": -0.08, "ad_spend": 400.0}
    assert llm.cursor == 1


def test_symbolic_agent_tool_loop_and_invalid_hypothesis_regeneration(monkeypatch, bench):
    sp = bench.StateProvider()
    sp.update(STATE)

    def after_invalid(messages):             # the invalid verdict must have been fed back before we 'regenerate'
        tm = [m for m in messages if isinstance(m, ToolMessage)]
        assert tm and json.loads(tm[-1].content)["is_valid"] is False
        return tool_call("check_business_rules", price_change=-0.1, ad_spend=300.0)

    def before_final(messages):
        tm = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tm) == 2 and json.loads(tm[-1].content)["is_valid"] is True
        return final(-0.1, 300.0)

    install_script(monkeypatch, bench, [tool_call("check_business_rules", price_change=-0.9, ad_spend=0.0), after_invalid, before_final])
    agent = bench.create_llm_symbolic_agent("decrease", "unused", sp)
    out = agent.invoke({"input": "state..."})
    assert bench.get_decision_from_response(out) == {"price_change": -0.1, "ad_spend": 300.0}


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    from src.components import CausalEngineV6
    return CausalEngineV6(data_path=str(tmp_path_factory.mktemp("a") / "d.pkl"), force_regenerate=True)


def test_full_chimera_agent_calls_both_tools(monkeypatch, bench, engine):
    sp = bench.StateProvider()
    sp.update(STATE)
    seen = {}

    def check(messages):
        seen["causal"] = json.loads([m for m in messages if isinstance(m, ToolMessage)][-1].content)
        return final(0.02, 600.0)

    install_script(monkeypatch, bench, [
        tool_call("check_business_rules", price_change=0.02, ad_spend=600.0),
        tool_call("estimate_profit_impact", price_change=0.02, ad_spend=600.0), check])
    agent = bench.create_full_chimera_agent("increase", "unused", sp, engine)
    out = agent.invoke({"input": "state..."})
    assert "estimated_long_term_value" in seen["causal"]
    assert seen["causal"]["estimated_long_term_value"] == pytest.approx(
        engine.estimate_causal_effect({"price_change": 0.02, "ad_spend": 600.0}, STATE)["estimated_long_term_value"])
    assert bench.get_decision_from_response(out)["ad_spend"] == 600.0


def test_exhausted_script_surfaces_as_error_not_silent_noop(monkeypatch, bench):
    install_script(monkeypatch, bench, [])
    agent = bench.create_llm_only_agent("decrease", "unused")
    with pytest.raises(Exception):
        agent.invoke({"input": "x"})


# ---- forced failure through the full 52-week runner (shortened) -------------------------------------------------
def run(monkeypatch, bench, agent_type, engine, weeks=4, pc=-0.4, ad=0.0):
    monkeypatch.setattr(bench, "NUM_WEEKS", weeks)
    install_script(monkeypatch, bench, [final(pc, ad)] * weeks)   # same bad answer every week; tool use is tested above
    monkeypatch.setattr(bench, "CausalEngineV6", lambda **k: engine)
    return bench.run_agent_scenario(agent_type, "decrease", "scripted goal")


def test_forced_failure_llm_only_is_not_repaired(monkeypatch, bench, engine):
    df = run(monkeypatch, bench, "llm_only", engine)
    assert df.price.iloc[-1] == 50.0                       # -40%/week hits the simulator's own price floor (cost)
    assert (df.price < 59.4).any()                         # i.e. below the guardian's 15%-margin floor


@pytest.mark.parametrize("agent_type", ["llm_symbolic", "full_chimera"])
def test_forced_failure_is_repaired_by_guardian(monkeypatch, bench, engine, agent_type):
    df = run(monkeypatch, bench, agent_type, engine)
    min_safe = 50.0 / 0.85 * 1.01
    assert (df.price >= min_safe - 1e-9).all()
    assert df.price.iloc[0] == pytest.approx(60.0)         # week 1: -40% from $100 is allowed
