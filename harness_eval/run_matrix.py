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

**Bug fixed 2026-10-03**: the LLM arms used to build `HTNHarness` with `params.depth` left at
`harness/params/default.json`'s own default, `"L0"` — which makes `_harness_recommend` skip
straight to the tools-only path regardless of whether an LLM is configured, so `full`/`loo_*`
silently made zero LLM calls (and billed $0) no matter what `LLM_MODE` said. `--depth` now
defaults to `"L1"` and is applied to the LLM arms specifically (`tools_only`/`baseline`/`no_op`
are untouched by it, since depth is meaningless to them).

**Two evaluation gaps closed the same day** (an independent review flagged both): the report only
ever compared an arm to `baseline`, never to `no_op` — "is the harness beating doing-nothing" is
a different, also-useful question from "is it beating the deterministic baseline", and the
`no_op` arm was already being run, just not used for a second comparison. Now `offtake_vs_noop_pct`
sits alongside `offtake_vs_baseline_pct` in the raw CSV, and the aggregated report adds a rough
95% CI on the mean lift (`_ci95_str`, a normal approximation — `n` per group is a handful of
worlds, not a large sample, so treat it as indicative, not rigorous) plus the no-op comparison.
Perturbed-world near-duplication (P1-P6 differ from dev by one shock-schedule change each, per
`worlds.py`) is **not** addressed here — that's a question about what `worlds.py` generates, not
how this script reports on it; flagged, not fixed, in `problem-mapped/A1-implementation.md`.

    PYTHONPATH=. python -m harness_eval.run_matrix                  # cost-free arms, all worlds
    LLM_MODE=record PYTHONPATH=. python -m harness_eval.run_matrix --worlds search_7  # one paid run
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
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


def build_arms(params, llm_enabled: bool, replicate: int = 0, llm_depth: str = "L1") -> dict:
    """`params` (unmodified) backs the cost-free arms. The LLM arms use `replace(params,
    depth=llm_depth)` — passing `params` itself would leave them at `params.depth`, which is
    `"L0"` in `harness/params/default.json` and makes `_harness_recommend` skip the LLM entirely
    regardless of `llm_enabled` (the bug fixed above)."""
    arms = {
        "no_op": lambda: NoOpPolicy(),
        "baseline": lambda: DeterministicTraversal(),
        "tools_only": lambda: HTNToolsOnly(params),
    }
    if not llm_enabled:
        return arms

    llm_params = replace(params, depth=llm_depth)

    def make_full():
        llm, _ = build_llm_stack(llm_params)
        return HTNHarness(llm_params, llm=llm, replicate=replicate)

    arms["full"] = make_full

    def make_loo(leaf_name):
        def _build():
            llm, _ = build_llm_stack(llm_params)
            return HTNHarness(llm_params, llm=LeafAblationLLM(llm, leaf_name), replicate=replicate)
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
               include_perturbed: bool = True, llm_depth: str = "L1",
               llm_arm_names: list[str] | None = None) -> pd.DataFrame:
    """`llm_arm_names`, if given, restricts the LLM arms actually run to this subset of
    `{"full", "loo_L1_value", "loo_L2_shock", "loo_L3_sibling", "loo_L4_explore", "loo_L6_review"}`
    — useful for keeping a real-money run small (e.g. `["full"]` skips all 5 LOO arms)."""
    params = load_params()
    _, mode = build_llm_stack(params)
    llm_enabled = mode != "off"
    specs = world_specs(include_perturbed=include_perturbed)
    if world_names:
        specs = [s for s in specs if s[0] in world_names]

    cost_free = ("no_op", "baseline", "tools_only")
    rows = []
    for label, seed, scenario in specs:
        arms = build_arms(params, llm_enabled, replicate=0, llm_depth=llm_depth)
        for arm_name in cost_free:
            row = run_one(arm_name, arms[arm_name], label, seed, scenario)
            row["replicate"] = 0
            rows.append(row)
        for arm_name in arms:
            if arm_name in cost_free:
                continue
            if llm_arm_names is not None and arm_name not in llm_arm_names:
                continue
            for replicate in range(n_replicates):
                arms_r = build_arms(params, llm_enabled, replicate, llm_depth=llm_depth)
                row = run_one(arm_name, arms_r[arm_name], label, seed, scenario)
                row["replicate"] = replicate
                rows.append(row)
    df = pd.DataFrame(rows)
    base = df[df.arm == "baseline"].set_index("world").offtake_inr_per_day
    noop = df[df.arm == "no_op"].set_index("world").offtake_inr_per_day
    df["offtake_vs_baseline_pct"] = df.apply(
        lambda r: round((r.offtake_inr_per_day / base.get(r.world, r.offtake_inr_per_day) - 1) * 100, 3), axis=1)
    df["offtake_vs_noop_pct"] = df.apply(
        lambda r: round((r.offtake_inr_per_day / noop.get(r.world, r.offtake_inr_per_day) - 1) * 100, 3), axis=1)
    return df


def _ci95_str(s: pd.Series) -> str:
    """A normal-approximation 95% CI on the mean (`mean +/- 1.96 * sample_std / sqrt(n)`) — a
    rough-and-ready interval, not a rigorous one (n per group is typically 4-12 worlds, not a
    large sample), but better than reporting a bare mean with no sense of how noisy it is.
    `n <= 1` has no estimable spread; returned as "n/a" rather than a misleadingly tight interval."""
    n = len(s)
    if n <= 1:
        return "n/a"
    se = s.std(ddof=1) / (n ** 0.5)
    lo, hi = s.mean() - 1.96 * se, s.mean() + 1.96 * se
    return f"[{lo:.2f}, {hi:.2f}]"


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
            n=("offtake_vs_baseline_pct", "size"),
            mean_lift_pct=("offtake_vs_baseline_pct", "mean"),
            lift_ci95=("offtake_vs_baseline_pct", _ci95_str),
            mean_lift_vs_noop_pct=("offtake_vs_noop_pct", "mean"),
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
    ap.add_argument("--depth", default="L1", choices=("L1", "L2"), help="depth for the LLM arms only")
    ap.add_argument("--llm-arms", nargs="*", default=None,
                    help="restrict LLM arms to this subset, e.g. --llm-arms full")
    a = ap.parse_args()
    _, mode = build_llm_stack(load_params())
    print(f"LLM_MODE={mode!r} -> LLM arms {'ENABLED' if mode != 'off' else 'disabled (cost-free arms only)'}")
    df = run_matrix(a.worlds, a.replicates, include_perturbed=not a.no_perturbed, llm_depth=a.depth,
                    llm_arm_names=a.llm_arms)
    write_report(df, Path(a.out))
    print(f"wrote {a.out}/matrix.csv and {a.out}/report.md ({len(df)} rows)")


if __name__ == "__main__":
    main()
