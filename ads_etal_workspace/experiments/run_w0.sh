#!/bin/bash
# W0: old-harness runs from the 0b73557 worktree, queued behind the 1b and X5.1 batches. Run from anywhere.
cd /Users/arnabkar/Documents/Ads-etal/w0_old_harness
while pgrep -f "run_arms --arms (sm_|llm_)" > /dev/null || pgrep -f "run_x51.sh" > /dev/null; do sleep 30; done
PYTHONPATH=. ../grid-path-challenge/.venv/bin/python ../experiments/w0/w0_sim.py --arm baseline --seeds 7 --jobs 1
PYTHONPATH=. ../grid-path-challenge/.venv/bin/python ../experiments/w0/w0_sim.py --arm l0 --jobs ${JOBS:-3}
cd ../grid-path-challenge && PYTHONPATH=.:.. .venv/bin/python -m experiments.w0.w0_run
