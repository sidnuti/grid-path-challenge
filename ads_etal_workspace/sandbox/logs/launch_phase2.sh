#!/bin/bash
# Phase 2 launch (2026-10-05): Chimera R-C2 on minimax-m3, MoHOLLM R-M1 on qwen3.7-flash. Record mode; resumable (cache).
cd /Users/arnabkar/Documents/Ads-etal/sandbox
export SANDBOX_LLM_MODE=record
for i in 0 1 2; do for b in decrease increase; do
  (cd chimera && nohup uv run python runs/r_c2.py --weeks 52 --salt seed$i --sim-seed $((42+i)) --biases $b > ../logs/rc2_seed${i}_${b}.log 2>&1 &)
done; done
cd mohollm
nohup sh -c 'cat ../logs/mohollm_jobs.txt | xargs -P 5 -L 1 sh -c '"'"'uv run python runs/r_m1.py --config "$0" --seed "$1" > ../logs/rm1_$(basename "$0" .json)_s$1.log 2>&1'"'"'' > ../logs/rm1_queue.log 2>&1 &
