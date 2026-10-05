#!/bin/bash
# Detached supervisor: every 90 s restart halted MoHOLLM jobs; exits when no r_c2/r_m1 process is left.
cd /Users/arnabkar/Documents/Ads-etal/sandbox/logs
while true; do
  ./resume_halted.sh >> autoresume.log 2>&1
  [ "$(pgrep -f 'r_c2.py|r_m1.py' | wc -l)" -eq 0 ] && { echo "$(date +%T) all finished" >> autoresume.log; exit 0; }
  sleep 90
done
