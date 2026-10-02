"""Evaluation matrix: arms x worlds x replicates, `gpc.runner.simulate` under common random
numbers (`gpc.market`'s own per-day RNG keyed on the world's seed, unchanged by the policy — see
`tests/test_sandbox.py::test_common_random_numbers`), so a policy's lift over baseline on the same
world is a paired comparison, not two independent runs.

Cost-free arms (`no_op`, `baseline`, `tools_only`) always run. The LLM-aided arms (`full`, and a
leave-one-out ablation per leaf) only run if `LLM_MODE` is not `"off"` — this script never flips
that switch itself; it reads whatever `harness/llm/build_llm_stack` would build from the current
`.env`/environment, so running it costs real money only when you've already decided to spend some
(`LLM_MODE=record` or `live`) by setting the env var, not as a side effect of running `make
harness-eval`. `LLM_MODE=replay` runs the LLM arms for free against an already-recorded cache.

    PYTHONPATH=. python -m harness_eval.run_matrix                  # cost-free arms, all worlds
    LLM_MODE=record PYTHONPATH=. python -m harness_eval.run_matrix --worlds search_7  # one paid run
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from gpc.policy import DeterministicTraversal, NoOpPolicy
from gpc.runner import simulate
from gpc.score import summarize
from gpc.world import build_world

from harness.config import load_params
from harness.llm import build_llm_stack
from harness.llm.meter import usage_of
from harness.policy import HTNHarness, HTNToolsOnly

from .worlds import world_specs

OUT_DIR = Path(__file__).resolve().parent / "out"
LOO_LEAVES = ("L1_value", "L2_shock", "L3_sibling", "L4_explore", "L6_review")


class LeafAblationLLM:
    """Wraps a real LLM client and makes calls for one named leaf fail — `leaf()` absorbs that
    into the leaf's default, i.e. "as if that leaf didn't exist" for this run, without touching
    `harness/htn/llm_methods.py` itself."""

    def __init__(self, inner, excluded_leaf: str):
        self.inner = inner
        self.excluded_leaf = excluded_leaf

    def complete_json(self, system, user, schema, timeout, **kwargs):
        if kwargs.get("leaf") == self.excluded_leaf:
            raise RuntimeError(f"ablated for this arm: {self.excluded_leaf}")
        return self.inner.complete_json(system, user, schema, timeout, **kwargs)


def build_arms(params, llm_enabled: bool, replicate: int = 0) -> dict:
    arms = {
        "no_op": lambda: NoOpPolicy(),
        "baseline": lambda: DeterministicTraversal(),
        "tools_only": lambda: HTNToolsOnly(params),
    }
    if not llm_enabled:
        return arms

    def make_full():
        llm, _ = build_llm_stack(params)
        return HTNHarness(params, llm=llm, replicate=replicate)

    arms["full"] = make_full

    def make_loo(leaf_name):
        def _build():
            llm, _ = build_llm_stack(params)
            return HTNHarness(params, llm=LeafAblationLLM(llm, leaf_name), replicate=replicate)
        return _build

    for leaf_name in LOO_LEAVES:
        arms[f"loo_{leaf_name}"] = make_loo(leaf_name)
    return arms


def run_one(arm_name: str, build_policy, label: str, seed: int, scenario: str) -> dict:
    policy = build_policy()
    res = simulate(build_world(seed, scenario), policy, verbose=False)
    summary = summarize(res)
    fallbacks = sum(1 for r in res.runs if "fallback_reason" in (r["trace"] or {}))
    proposed = sum(len(r["proposed"]) for r in res.runs)
    shipped = sum(len(r["final"]) for r in res.runs)
    usage = usage_of(getattr(policy, "_llm_override", None))
    return {"arm": arm_name, "world": label, "seed": seed, "offtake_inr_per_day": summary["offtake_inr_per_day"],
            "direct_roas": summary["direct_roas"], "roas_floor": summary["roas_floor"],
            "roas_constraint_met": summary["roas_constraint_met"], "actions_proposed": proposed,
            "actions_shipped": shipped, "blocked_share": round(1 - shipped / proposed, 3) if proposed else 0.0,
            "fallback_count": fallbacks, **usage}


def run_matrix(world_names: list[str] | None = None, n_replicates: int = 1,
               include_perturbed: bool = True) -> pd.DataFrame:
    params = load_params()
    _, mode = build_llm_stack(params)
    llm_enabled = mode != "off"
    specs = world_specs(include_perturbed=include_perturbed)
    if world_names:
        specs = [s for s in specs if s[0] in world_names]

    cost_free = ("no_op", "baseline", "tools_only")
    rows = []
    for label, seed, scenario in specs:
        arms = build_arms(params, llm_enabled, replicate=0)
        for arm_name in cost_free:
            row = run_one(arm_name, arms[arm_name], label, seed, scenario)
            row["replicate"] = 0
            rows.append(row)
        for arm_name in arms:
            if arm_name in cost_free:
                continue
            for replicate in range(n_replicates):
                arms_r = build_arms(params, llm_enabled, replicate)
                row = run_one(arm_name, arms_r[arm_name], label, seed, scenario)
                row["replicate"] = replicate
                rows.append(row)
    df = pd.DataFrame(rows)
    base = df[df.arm == "baseline"].set_index("world").offtake_inr_per_day
    df["offtake_vs_baseline_pct"] = df.apply(
        lambda r: round((r.offtake_inr_per_day / base.get(r.world, r.offtake_inr_per_day) - 1) * 100, 3), axis=1)
    return df


def _to_markdown(df: pd.DataFrame) -> str:
    """A minimal `DataFrame.to_markdown()` substitute — avoids adding `tabulate` as a dependency
    just for this one report."""
    cols = [df.index.name or ""] + list(df.columns)
    rows = [[str(idx)] + [str(v) for v in row] for idx, row in zip(df.index, df.values)]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    def fmt_row(vals):
        return "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"
    lines = [fmt_row(cols), fmt_row(["-" * w for w in widths])]
    lines += [fmt_row(r) for r in rows]
    return "\n".join(lines)


def write_report(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "matrix.csv", index=False)

    groups = {"search": [w for w in df.world.unique() if w.startswith("search_")],
             "heldout": [w for w in df.world.unique() if w.startswith("heldout_")],
             "perturbed": [w for w in df.world.unique() if w.startswith("P")]}
    lines = ["# Evaluation matrix report", ""]
    for group, worlds in groups.items():
        if not worlds:
            continue
        lines.append(f"## {group}")
        sub = df[df.world.isin(worlds)]
        agg = sub.groupby("arm").agg(
            mean_lift_pct=("offtake_vs_baseline_pct", "mean"),
            p_lift_negative=("offtake_vs_baseline_pct", lambda s: round((s < 0).mean(), 3)),
            floor_met_share=("roas_constraint_met", "mean"),
            mean_blocked_share=("blocked_share", "mean"),
            mean_fallbacks=("fallback_count", "mean"),
            total_cost_usd=("cost_usd", "sum"),
            total_calls=("calls", "sum"),
        ).round(4)
        lines.append(_to_markdown(agg))
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worlds", nargs="*", default=None)
    ap.add_argument("--replicates", type=int, default=1)
    ap.add_argument("--no-perturbed", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()
    _, mode = build_llm_stack(load_params())
    print(f"LLM_MODE={mode!r} -> LLM arms {'ENABLED' if mode != 'off' else 'disabled (cost-free arms only)'}")
    df = run_matrix(a.worlds, a.replicates, include_perturbed=not a.no_perturbed)
    write_report(df, Path(a.out))
    print(f"wrote {a.out}/matrix.csv and {a.out}/report.md ({len(df)} rows)")


if __name__ == "__main__":
    main()
