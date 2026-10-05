#!/bin/bash
# Restart MoHOLLM jobs whose log shows a halt/crash, that have no result.json and no live process. Resumes from the cache.
cd /Users/arnabkar/Documents/Ads-etal/sandbox/mohollm
export SANDBOX_LLM_MODE=record
while read cfg seed; do
  name=$(basename "$cfg" .json); log=../logs/rm1_${name}_s${seed}.log
  [ -f "$log" ] || continue
  grep -qE "SandboxHalt|Traceback" "$log" || continue
  ls runs/work/full_${name}_s${seed}_qwen3.7-flash/result.json >/dev/null 2>&1 && continue
  pgrep -f "r_m1.py --config $cfg --seed $seed" >/dev/null && continue
  mv "$log" "../logs/halted_${name}_s${seed}_$(date +%H%M%S).log"
  echo "resuming $name seed $seed"
  nohup uv run python runs/r_m1.py --config "$cfg" --seed "$seed" > "$log" 2>&1 &
done < ../logs/mohollm_jobs.txt
