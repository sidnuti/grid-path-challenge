#!/bin/bash
# Re-replay the 3 partitioned runs that missed before the schedule + hole fixes (2026-10-05).
cd /Users/arnabkar/Documents/Ads-etal/sandbox/mohollm
export SANDBOX_LLM_MODE=replay
printf '%s\n' "Penicillin/MOHOLLM-Penicillin-Context-Gemini.json 31415927" "Penicillin/MOHOLLM-Penicillin-Context-Gemini.json 42" "Simple2D/Gemini/MOHOLLM-BraninCurrin-Gemini.json 42" |
  xargs -P 3 -L 1 sh -c 'uv run python runs/r_m1.py --config "$0" --seed "$1" --out runs/work_replay > ../logs/replay/rm1_$(basename "$0" .json)_s$1.log 2>&1'
