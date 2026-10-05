"""Sim v2 gate: with every v2 flag off, the simulator reproduces the frozen legacy output byte for byte."""
import json
from pathlib import Path

import pytest

from scripts.make_goldens import GOLD, digest, run_one


@pytest.mark.slow
@pytest.mark.parametrize("seed,pol", [(7, "no_op"), (42, "traversal")])
def test_legacy_goldens(seed, pol):
    manifest = json.loads((GOLD / "manifest.json").read_text())
    for name, df in run_one(seed, pol).items():
        assert digest(df) == manifest[f"s{seed}_{pol}_{name}"], name
