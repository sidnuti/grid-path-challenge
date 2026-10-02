"""World sets for the evaluation matrix (`run_matrix.py`). This module, unlike anything under
`harness/`, is allowed to read `gpc.world`/the scenario files directly — it is the offline tooling
the plan's rules test (`tests/harness/test_rules.py`) explicitly keeps `harness/` from importing,
not the harness itself. Nothing here runs during `make score`.

- **Search seeds** (7, 11, 23, 42) — the ones M1's gate and the S1-S10 scenario fixtures already
  use; building/tuning happens against these.
- **Held-out seeds** (101, 202) — never looked at while building; `run_matrix.py` reports both
  groups separately so a held-out regression isn't masked by a search-seed win.
- **Perturbed scenarios P1-P6** — generated from the dev scenario's own shock list by moving
  *which* run/city/keyword/kind each shock hits and rescaling its magnitude, never by reading or
  reusing the eval scenario (which isn't in this repo) or inventing new truth parameters out of
  nothing. **Open item, not yet answered by Gobblecube**: whether self-authored perturbed
  scenarios are an acceptable offline-validation input at all (see the plan's open items). Written
  and used here on the assumption that offline-only, harness-never-reads-them validation is fine;
  flagged again in `problem-mapped/A1-implementation.md` rather than assumed silently.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from gpc.world import load_scenario

SEARCH_SEEDS = (7, 11, 23, 42)
HELDOUT_SEEDS = (101, 202)
SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"


def _base_shocks() -> list[dict]:
    return copy.deepcopy(load_scenario("dev")["shocks"])


def _perturbed(name: str, shock_edits: list[dict]) -> dict:
    """Starts from the dev scenario, replaces its `shocks` list with `shock_edits`. Everything
    else (keyword intent/incrementality, appeal, noise, auction_sigma) stays the dev scenario's
    own — only the shock schedule is perturbed, so P1-P6 differ from dev in exactly one
    documented way each, not in every parameter at once."""
    spec = copy.deepcopy(load_scenario("dev"))
    spec["name"] = name
    spec["shocks"] = shock_edits
    return spec

# Each Pn documents, in one line, what it moves relative to dev's own shock list
# (osa: S2/HYD run 3; price: MUM K05/K06 x1.35 from run 4; demand: K03/K04 x1.15 from run 5):

PERTURBATIONS = {
    "P1_osa_different_sku_city": lambda: _perturbed("P1_osa_different_sku_city", [
        {"kind": "osa", "sku_id": "S4", "city_id": "PUN", "from_run": 2, "to_run": 2, "osa": 0.35},
        {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_run": 4, "mult": 1.35},
        {"kind": "demand", "keyword_ids": ["K03", "K04"], "from_run": 5, "mult": 1.15},
    ]),
    "P2_price_different_market_bigger": lambda: _perturbed("P2_price_different_market_bigger", [
        {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_run": 3, "to_run": 3, "osa": 0.42},
        {"kind": "price", "city_id": "DEL", "keyword_ids": ["K01", "K02"], "from_run": 3, "mult": 1.60},
        {"kind": "demand", "keyword_ids": ["K03", "K04"], "from_run": 5, "mult": 1.15},
    ]),
    "P3_demand_different_keywords_earlier": lambda: _perturbed("P3_demand_different_keywords_earlier", [
        {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_run": 3, "to_run": 3, "osa": 0.42},
        {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_run": 4, "mult": 1.35},
        {"kind": "demand", "keyword_ids": ["K07", "K08"], "from_run": 2, "mult": 1.40},
    ]),
    "P4_all_three_shifted_earlier": lambda: _perturbed("P4_all_three_shifted_earlier", [
        {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_run": 1, "to_run": 1, "osa": 0.42},
        {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_run": 2, "mult": 1.35},
        {"kind": "demand", "keyword_ids": ["K03", "K04"], "from_run": 2, "mult": 1.15},
    ]),
    "P5_severe_osa_dip": lambda: _perturbed("P5_severe_osa_dip", [
        {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_run": 3, "to_run": 4, "osa": 0.20},
        {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_run": 4, "mult": 1.35},
        {"kind": "demand", "keyword_ids": ["K03", "K04"], "from_run": 5, "mult": 1.15},
    ]),
    "P6_demand_shock_on_brand": lambda: _perturbed("P6_demand_shock_on_brand", [
        {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_run": 3, "to_run": 3, "osa": 0.42},
        {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_run": 4, "mult": 1.35},
        {"kind": "demand", "keyword_ids": ["K01", "K02"], "from_run": 5, "mult": 1.30},
    ]),
}


def write_perturbed_scenarios(out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or SCENARIO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, build in PERTURBATIONS.items():
        spec = build()
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(spec, indent=2))
        paths.append(path)
    return paths


def world_specs(include_perturbed: bool = True) -> list[tuple[str, int, str]]:
    """Returns [(world_label, seed, scenario), ...] — `scenario` is "dev" for the seed-based
    worlds, or a path under `SCENARIO_DIR` for a perturbed one (always run at the dev scenario's
    own seed 7, since P1-P6 vary the shock schedule, not the random draws)."""
    specs = [(f"search_{s}", s, "dev") for s in SEARCH_SEEDS]
    specs += [(f"heldout_{s}", s, "dev") for s in HELDOUT_SEEDS]
    if include_perturbed:
        write_perturbed_scenarios()
        specs += [(name, 7, str(SCENARIO_DIR / f"{name}.json")) for name in PERTURBATIONS]
    return specs
