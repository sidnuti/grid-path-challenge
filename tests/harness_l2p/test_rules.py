"""harness_l2p obeys the same hard rules as harness/: observation only."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "harness_l2p"
FORBIDDEN_MODULES = ("gpc.market", "gpc.scenarios", "harness_eval", "experiments")


@pytest.mark.parametrize("path", sorted(PKG.rglob("*.py")), ids=lambda p: p.name)
def test_no_forbidden_imports_or_truth(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith(FORBIDDEN_MODULES), f"{path.name}: import {a.name}"
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(FORBIDDEN_MODULES), f"{path.name}: from {node.module}"
        elif isinstance(node, ast.Attribute):
            assert node.attr != "truth", f"{path.name}: .truth access"


def test_brief_has_no_scenario_numbers(ctx):
    import json
    dev = json.loads((PKG.parent / "gpc" / "scenarios" / "dev.json").read_text())
    text = ctx["brief"].text
    for spec in dev.get("keywords", {}).values():
        for k in ("intent", "incrementality"):
            assert f"{spec[k]:.6f}" not in text
