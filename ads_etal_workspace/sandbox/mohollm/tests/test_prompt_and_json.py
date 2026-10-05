"""utils/prompt_builder.py + prompt_templates/base/{partitioning,vanilla}; llm.to_json robustness."""
from pathlib import Path

import pytest

from mohollm.llm.llm import LLMInterface
from mohollm.space_partitioning.utils import Region
from mohollm.statistics.statistics import Statistics
from mohollm.utils.prompt_builder import PromptBuilder

pytestmark = pytest.mark.offline
SNAP = Path(__file__).parent / "snapshots"


def builder(template):
    pb = PromptBuilder(template_dir=template)
    st = Statistics()
    st.observed_configs = [{"x0": 0.1, "x1": 0.9}, {"x0": 0.5, "x1": 0.5}, {"x0": 0.8, "x1": 0.2}]
    st.observed_fvals = [{"F1": 1.5, "F2": 2.25}, {"F1": 0.75, "F2": 0.5}, {"F1": 2.0, "F2": 3.125}]
    st.max_context_configs = 110
    from mohollm.statistics.context_limit_strategy.lastN import LastN
    st.context_limit_strategy = LastN()
    pb.statistics = st
    pb.feature_names, pb.metrics_names, pb.metrics_targets = ["x0", "x1"], ["F1", "F2"], ["min", "min"]
    pb.prompt = {"description": "Minimise two toy objectives.", "instruction": ""}
    pb.parameter_constraints = {"x0": [0.0, 1.0], "x1": [0.0, 1.0]}
    pb.shuffle_icl_columns = pb.shuffle_icl_rows = False
    pb.initialize_templates()
    return pb, st


REGION = Region(volume=0.25, normalized_volume=0.25, center={"x0": 0.1, "x1": 0.9}, center_fval={"F1": 1.5, "F2": 2.25},
                boundaries={"x0": [0.0, 0.5], "x1": [0.5, 1.0]},
                points=[{"x0": 0.1, "x1": 0.9}], points_fvals=[{"F1": 1.5, "F2": 2.25}], points_indices=[0],
                range_parameter_keys=["x0", "x1"], integer_parameter_keys=[], float_parameter_keys=["x0", "x1"])


def partition_prompt():
    pb, _ = builder("./prompt_templates/base/partitioning/candidate_sampler.txt")
    return pb.build_prompt(target_number_of_candidates=5, region_constraints=str(REGION),
                           region_icl_examples=(REGION.points, REGION.points_fvals))


def test_partitioning_prompt_contains_box_bounds_and_icl_examples():
    p = partition_prompt()
    assert "x0: range(float([0.0, 0.5]))" in p and "x1: range(float([0.5, 1.0]))" in p      # box bounds, rendered
    assert p.count("allowable ranges") == 1
    assert "Configuration: " in p and "0.1" in p and "0.9" in p                               # ICL example from the box
    assert "F1: 1.5, F2: 2.25" in p                                                           # its function values
    assert "F1 (lower is better), F2 (lower is better)" in p
    assert "Generate 5 new configurations" in p
    assert "$region_constraints" not in p and "$Region_ICL_examples" not in p                 # nothing left unsubstituted
    assert '{"x0": $x0, "x1": $x1}' in p                                                      # response-format template


def test_partitioning_prompt_only_shows_points_of_the_box():
    pb, st = builder("./prompt_templates/base/partitioning/candidate_sampler.txt")
    p = pb.build_prompt(target_number_of_candidates=3, region_constraints=str(REGION),
                        region_icl_examples=(REGION.points, REGION.points_fvals))
    assert "0.5" in p and "F1: 0.75" not in p and "F1: 2.0" not in p       # points outside the box are not leaked


def test_vanilla_prompt_uses_global_history():
    pb, st = builder("./prompt_templates/base/vanilla/candidate_sampler.txt")
    p = pb.build_prompt(target_number_of_candidates=4)
    for f in st.observed_fvals:
        assert f"F1: {f['F1']}, F2: {f['F2']}" in p                         # all observations appear
    assert "$ICL_examples" not in p


def test_partitioning_prompt_snapshot():
    got = partition_prompt()
    snap = SNAP / "partitioning_candidate_sampler.txt"
    if not snap.exists():                                                    # first run records; later runs compare
        SNAP.mkdir(exist_ok=True)
        snap.write_text(got)
    assert got == snap.read_text()


def test_shuffle_rows_flag_is_respected():
    pb, _ = builder("./prompt_templates/base/vanilla/candidate_sampler.txt")
    pb.shuffle_icl_rows = True
    import random
    random.seed(1)
    shuffled = pb._build_icl_examples()
    pb.shuffle_icl_rows = False
    plain = pb._build_icl_examples()
    assert sorted(shuffled.split("\n")) == sorted(plain.split("\n")) and shuffled != plain


# ---- to_json -----------------------------------------------------------------------------------------------------------
class Dummy(LLMInterface):
    def prompt(self, prompt, max_number_of_tokens=100, **kw):
        return ""


@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here it is:\n```json\n[{"x0": 0.1}, {"x0": 0.2}]\n```\nHope that helps.', [{"x0": 0.1}, {"x0": 0.2}]),
    ("```json\n{'a': 1, 'b': 'c'}\n```", {"a": 1, "b": "c"}),              # single quotes are normalised
    ('<think>let me think {not json}</think>{"a": 2}', {"a": 2}),
    ('<think>\nmulti\nline\n</think>\n```json\n{"a": 3}\n```', {"a": 3}),
    ('  \n {"a": 4}  \n', {"a": 4}),
])
def test_to_json_accepts(text, expected):
    assert Dummy().to_json(text) == expected


@pytest.mark.parametrize("text", ["", "no json here", '{"a": ', '```json\n{bad}\n```', 'Result: {"a": 1} trailing'])
def test_to_json_rejects_unparseable_text(text):
    with pytest.raises(Exception):
        Dummy().to_json(text)


def test_finding_to_json_does_not_extract_json_from_surrounding_prose():
    """FINDING: unlike Chimera's regex extractor, MoHOLLM only parses a ```json fence or the whole string; a reply with
    prose around bare JSON raises. Reasoning models that add commentary will therefore fail the sampler call (the optimiser
    catches per-region exceptions and drops that region's proposals)."""
    with pytest.raises(Exception):
        Dummy().to_json('Here you go: {"a": 1}')
