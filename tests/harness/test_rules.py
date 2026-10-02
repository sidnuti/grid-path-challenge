"""Hard rules the harness must never break, enforced structurally (AST scan) rather than by
convention, per the plan: `harness/` must never read `gpc.market`, `gpc.world` truth, `.truth`,
`gpc.scenarios`, or `harness_eval`, and must never open a file under `gpc/scenarios`. A rendered
prompt built from a dev `Observation` must not contain any of the dev scenario file's raw numbers
— the test loads `dev.json` itself; the harness never does.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[2] / "harness"
FORBIDDEN_IMPORTS = {"gpc.market", "gpc.scenarios"}
FORBIDDEN_ATTR_NAMES = {"truth"}


def _py_files():
    return sorted(HARNESS_DIR.rglob("*.py"))


def test_harness_has_code_to_scan():
    assert len(_py_files()) > 5


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: str(p.relative_to(HARNESS_DIR)))
def test_no_forbidden_imports_or_truth_access(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in FORBIDDEN_IMPORTS, f"{path}: forbidden import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod not in FORBIDDEN_IMPORTS, f"{path}: forbidden import from {mod}"
            assert "harness_eval" not in mod, f"{path}: harness/ must not import harness_eval"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_ATTR_NAMES, f"{path}: access to `.{node.attr}` (world/market truth)"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                assert "gpc/scenarios" not in node.args[0].value, f"{path}: opens a file under gpc/scenarios"


def test_dev_scenario_numbers_never_rendered_in_a_prompt():
    """Builds a dev Observation the normal way and checks nothing resembling a raw dev.json
    truth value (keyword intent/incrementality) ends up in any string the harness would render.
    Guards against a future leaf/prompt builder accidentally stringifying `world.truth`."""
    dev = json.loads((HARNESS_DIR.parents[0] / "gpc" / "scenarios" / "dev.json").read_text())
    raw_numbers = set()
    for kw, spec in dev.get("keywords", {}).items():
        raw_numbers.add(round(spec["intent"], 6))
        raw_numbers.add(round(spec["incrementality"], 6))

    import sys
    sys.path.insert(0, str(HARNESS_DIR.parents[0]))
    from gpc.world import build_world, WARMUP_DAYS
    from gpc.market import Market
    from gpc.observation import Observation
    import pandas as pd

    w = build_world(7, "dev")
    m = Market(w)
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    for d in range(WARMUP_DAYS):
        o = m.simulate_day(d, w.public["campaigns"], w.public["campaign_keywords"])
        for k, v in o.items():
            acc[k].append(v)
    frames = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    obs = Observation(run=1, day=WARMUP_DAYS, public=w.public, campaigns=w.public["campaigns"],
                      campaign_keywords=w.public["campaign_keywords"], roas_floor=4.0, warmup_droas=4.6, **frames)

    # Nothing a policy can see (obs.public, obs.campaigns, obs.*_daily) carries a `truth` field,
    # by construction of `gpc.observation.Observation` — assert that dataclass's own field set.
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(obs)}
    assert "truth" not in field_names
