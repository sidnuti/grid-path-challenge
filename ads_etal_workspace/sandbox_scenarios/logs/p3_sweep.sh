#!/bin/sh
# P3 $0 baseline sweep (design/04 §6): E1 (G0) on sc1, sc2, sc3, sc_all × seeds 7, 11, 23 for A0, A1, A2, A5 at
# 50 evaluations; E2 (G1) on sc3, sc_all for A1, A2, A5; then O1 (CMA-ES, gpc env: cma 4.x) per E1 problem.
# Usage: sh logs/p3_sweep.sh <o1_evals>      (from sandbox_scenarios/; GPC_PY = python of the gpc_v2 env, default gpc_v2/.venv/bin/python)
set -u
O1_EVALS=${1:-1000}
ROOT=$(pwd)
JOBS=logs/p3_jobs.txt
: > $JOBS
for sc in sc1_cannibal sc2_brand_assoc sc3_festive sc_all; do
  for s in 7 11 23; do
    echo "bench A0 $sc $s G0" >> $JOBS
    echo "bench A1 $sc $s G0" >> $JOBS
    echo "bench A2 $sc $s G0" >> $JOBS
    echo "mohollm A5 $sc $s G0" >> $JOBS
  done
done
for sc in sc3_festive sc_all; do
  for s in 7 11 23; do
    echo "bench A1 $sc $s G1" >> $JOBS
    echo "bench A2 $sc $s G1" >> $JOBS
    echo "mohollm A5 $sc $s G1" >> $JOBS
  done
done
mkdir -p logs/p3_runs
export ROOT
cat $JOBS | xargs -P 8 -L 1 sh -c 'ROOT='"$ROOT"'; log="$ROOT/logs/p3_runs/$1_$2_$4_s$3.log";
  if [ "$0" = bench ]; then (cd "$ROOT/mohollm" && PYTHONPATH=..:../gpc_v2 PYTHONWARNINGS=ignore uv run python -m bench.arms --arm $1 --scenario $2 --seed $3 --goal $4 --evals 50) > "$log" 2>&1;
  else (cd "$ROOT/mohollm" && uv run python runs/r_ads.py --arm $1 --scenario $2 --seed $3 --goal $4 --evals 50) > "$log" 2>&1; fi;
  echo "done $1 $2 $4 s$3 exit=$?"'
echo "=== O1 ($O1_EVALS evals each)"
for sc in sc1_cannibal sc2_brand_assoc sc3_festive sc_all; do
  for s in 7 11 23; do
    [ -f "results/p3/O1/${sc}_G0_s${s}.json" ] && { echo "skip O1 $sc s$s (exists)"; continue; }
    PYTHONPATH=.:gpc_v2 PYTHONWARNINGS=ignore "${GPC_PY:-gpc_v2/.venv/bin/python}" -m bench.arms --arm O1 --scenario $sc --seed $s --evals $O1_EVALS --workers 10 > logs/p3_runs/O1_${sc}_G0_s$s.log 2>&1
    echo "done O1 $sc s$s exit=$?"
  done
done
echo "=== sweep finished"
