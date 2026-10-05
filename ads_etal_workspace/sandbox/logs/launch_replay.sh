#!/bin/bash
# Replay verification (2026-10-05): rerun every recorded Phase 2 run from the cache; any miss is a hard error, cost must be $0.
cd /Users/arnabkar/Documents/Ads-etal/sandbox
export SANDBOX_LLM_MODE=replay
for i in 0 1 2; do for b in decrease increase; do
  (cd chimera && nohup uv run python runs/r_c2.py --weeks 52 --salt seed$i --sim-seed $((42+i)) --biases $b --out runs/results_replay > ../logs/replay/rc2_seed${i}_${b}.log 2>&1 &)
done; done
cd mohollm
nohup sh -c 'cat ../logs/mohollm_jobs_replay.txt | xargs -P 5 -L 1 sh -c '"'"'uv run python runs/r_m1.py --config "$0" --seed "$1" --out runs/work_replay > ../logs/replay/rm1_$(basename "$0" .json)_s$1.log 2>&1'"'"'' > ../logs/replay/rm1_queue.log 2>&1 &
