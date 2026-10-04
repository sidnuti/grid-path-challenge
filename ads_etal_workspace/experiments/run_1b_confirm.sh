#!/bin/bash
# 1b confirmation (pre-registered in the log) + thin-world diagnostic. Queued behind X5.1. Run from anywhere.
cd /Users/arnabkar/Documents/Ads-etal/grid-path-challenge; export PYTHONPATH=.:..
while pgrep -f "run_arms --arms llm_" > /dev/null || pgrep -f "run_x51.sh" > /dev/null; do sleep 30; done
.venv/bin/python -m experiments.run_arms --arms no_op l0 sm_r1500_c1.0 gate_min2000 --seeds $(seq 2001 2010) --jobs ${JOBS:-3}
.venv/bin/python -m experiments.run_arms --arms sm_r1500_c1.0 gate_min2000 --seeds $(seq 1001 1010) --jobs ${JOBS:-3}
.venv/bin/python -m experiments.x2_ablation.x2_run --tag confirm2001 --seeds $(seq 2001 2010) --arms no_op l0 sm_r1500_c1.0 gate_min2000
.venv/bin/python -m experiments.x2_ablation.x2_run --tag diag1001 --seeds $(seq 1001 1010) --arms no_op l0 gate_min3000 sm_r1500_c1.0 gate_min2000 no_headroom_gate
