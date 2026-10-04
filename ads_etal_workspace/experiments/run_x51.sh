#!/bin/bash
# X5.1/X5.2: scripted-LLM arms. Run from grid-path-challenge/.
export PYTHONPATH=.:..
ARMS=""
for l in L1 L2 L3 L6; do for m in always_yes always_no random oracle; do ARMS="$ARMS llm_default_${l}_$m"; done; done
for m in always_yes always_no oracle; do ARMS="$ARMS llm_default_all_$m"; done
for l in L4 L6; do for m in always_yes always_no random oracle; do ARMS="$ARMS llm_recal_${l}_$m"; done; done
for m in always_yes always_no oracle; do ARMS="$ARMS llm_recal_all_$m"; done
.venv/bin/python -m experiments.run_arms --arms $ARMS --seeds 7 11 23 42 101 202 --jobs ${JOBS:-4}
