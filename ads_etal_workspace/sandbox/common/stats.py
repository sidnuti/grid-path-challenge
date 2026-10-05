"""Thin re-export of `experiments/lib/stats.py` (paired t-CI, sign-flip, bootstrap). Loaded by path so
the sandbox envs (Python 3.11) don't need the GPC package on sys.path."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "experiments" / "lib" / "stats.py"
_spec = importlib.util.spec_from_file_location("_gpc_stats", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

paired_lift_pct = _mod.paired_lift_pct
bootstrap_ci = _mod.bootstrap_ci
t_ci = _mod.t_ci
sign_flip_p = _mod.sign_flip_p
summarize = _mod.summarize
minimum_detectable_effect = _mod.minimum_detectable_effect
worlds_needed = _mod.worlds_needed
