"""Parameter-perturbed worlds (X7.3). The private eval scenario "uses different values and shocks", so a result tuned
on dev must be checked where the *values* differ too, not only the shock schedule (P1-P6 in `harness_eval`).
Every variant starts from the dev scenario and changes ONE documented thing. The files are written to
`experiments/scenarios/` and loaded by path (`gpc.world.load_scenario` reads any path)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from gpc.world import load_scenario

OUT = Path(__file__).resolve().parents[1] / "scenarios"


def _scale_inc(spec, f):
    for k in spec["keywords"].values():
        k["incrementality"] = round(min(0.98, max(0.02, k["incrementality"] * f)), 4)


def _scale_intent(spec, f):
    for k in spec["keywords"].values():
        k["intent"] = round(k["intent"] * f, 4)


def _shuffle_appeal(spec):
    keys = sorted(spec["appeal"])
    vals = [spec["appeal"][k] for k in keys]
    vals = vals[1:] + vals[:1]                      # deterministic rotation: every SKU gets a different SKU's appeal
    spec["appeal"] = dict(zip(keys, vals))


VARIANTS = {
    "V_iota_hi": ("incrementality x1.3 (clipped to 0.98)", lambda s: _scale_inc(s, 1.3)),
    "V_iota_lo": ("incrementality x0.7", lambda s: _scale_inc(s, 0.7)),
    "V_sigma_lo": ("auction sigma 0.2 (dev 0.3)", lambda s: s.__setitem__("auction_sigma", 0.2)),
    "V_sigma_hi": ("auction sigma 0.45 (dev 0.3)", lambda s: s.__setitem__("auction_sigma", 0.45)),
    "V_appeal_rot": ("SKU appeal rotated across SKUs", _shuffle_appeal),
    "V_intent_hi": ("keyword intent x1.25", lambda s: _scale_intent(s, 1.25)),
    "V_intent_lo": ("keyword intent x0.8", lambda s: _scale_intent(s, 0.8)),
}


def write_variants() -> dict[str, Path]:
    OUT.mkdir(exist_ok=True)
    paths = {}
    for name, (desc, fn) in VARIANTS.items():
        spec = copy.deepcopy(load_scenario("dev"))
        spec["name"], spec["note"] = name, f"experiments variant of dev: {desc}"
        fn(spec)
        p = OUT / f"{name}.json"
        p.write_text(json.dumps(spec, indent=2))
        paths[name] = p
    return paths


def scenario_paths() -> dict[str, str]:
    """name -> path for every perturbed world: the 7 value variants and harness_eval's P1-P6 shock worlds."""
    here = write_variants()
    pdir = Path(__file__).resolve().parents[2] / "grid-path-challenge" / "harness_eval" / "scenarios"
    out = {n: str(p) for n, p in here.items()}
    out.update({p.stem: str(p) for p in sorted(pdir.glob("P*.json"))})
    return out
