#!/bin/bash
# X7.3: L0 and gate variants on perturbed worlds (7 value variants + P1-P6 shock worlds) x 3 fresh seeds. Run from grid-path-challenge/.
export PYTHONPATH=.:..
PATHS=$(.venv/bin/python -c "from experiments.lib.scenarios import scenario_paths as s; print(' '.join(s().values()))")
for sc in $PATHS; do
  .venv/bin/python -m experiments.run_arms --arms no_op l0 no_headroom_gate gate_min3000 no_cuts sm_r1500_c1.0 ${EXTRA_ARMS:-} --seeds 303 304 305 --scenario "$sc" --jobs ${JOBS:-5}
done
