#!/bin/bash
# X3.1 bid dose-response. Run from grid-path-challenge/.
export PYTHONPATH=.:..
for s in 7 11; do .venv/bin/python -m experiments.x3_market.x3_1_bid_dose --seed $s --run 3 --jobs ${JOBS:-4}; done
