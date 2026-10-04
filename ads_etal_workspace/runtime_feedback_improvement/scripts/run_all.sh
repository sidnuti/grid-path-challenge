#!/usr/bin/env bash
# Re-runs every probe behind RUNTIME_FEEDBACK_REPORT.md. Cost-free: no LLM, no network.
# Usage (from the repo root):  bash runtime_feedback_improvement/scripts/run_all.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GPC="$ROOT/grid-path-challenge"; OUT="$ROOT/runtime_feedback_improvement/results"; SCR="$ROOT/runtime_feedback_improvement/scripts"
cd "$GPC"; export PYTHONPATH=.
for s in 7 11 23 42; do .venv/bin/python "$SCR/sizing_siblings_probe.py" "$s" > "$OUT/rerun_sizing_siblings_seed_$s.txt"; done
.venv/bin/python "$SCR/decision_funnel.py" 7 > "$OUT/rerun_decision_funnel_seed_7.txt"
for s in 7 42; do .venv/bin/python "$SCR/leaf_traffic_profile.py" "$s" explore > "$OUT/rerun_leaf_traffic_seed_$s.txt"; done
.venv/bin/python -m harness_eval.run_matrix --out "$OUT/matrix_full"   # ~25 min, 12 worlds x 3 cost-free arms
.venv/bin/python -m harness_eval.probes > /dev/null   # note: also rewrites harness_eval/out/probes.json
cp harness_eval/out/probes.json "$OUT/rerun_probes.json"
