# X5.1 / X5.2 — scripted-LLM bounds and trigger rates

Depth L2, scripted leaves, 6 dev worlds, paired vs the cached L0 arm. `default` = harness defaults (explore off, review threshold 500); `recal` = explore on (5 cells, 1000 INR/day) and review threshold 300. `always_no` is the passive answer (dampen / deny / keep mechanical leader / no explore / no veto), `always_yes` the active one, `oracle` reads hidden truth (an upper bound, not a realistic model). MDE of a 6-world paired test is roughly 0.1pp.

| params | leaf | mode | vs_l0_pct | t95 | p | worse/better | floor_met | min_margin | answered_per_world | defaulted_per_world | fallbacks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| default | L1 | always_no | -0.001 | -0.003 … 0.001 | 0.500 | 2/0 | 6/6 | 0.244 | 2.667 | 37.000 | 0 |
| default | L1 | random | -0.001 | -0.002 … 0.001 | 0.500 | 2/0 | 6/6 | 0.244 | 2.500 | 37.000 | 0 |
| default | L1 | always_yes | 0.000 | -0.002 … 0.002 | 1.000 | 1/1 | 6/6 | 0.244 | 2.167 | 37.000 | 0 |
| default | L1 | oracle | 0.000 | -0.002 … 0.002 | 1.000 | 1/1 | 6/6 | 0.244 | 2.167 | 37.000 | 0 |
| default | L2 | always_no | 0.000 | 0.000 … 0.000 | 1.000 | 0/0 | 6/6 | 0.244 | 5.667 | 33.500 | 0 |
| default | L2 | random | 0.000 | -0.000 … 0.001 | 1.000 | 0/1 | 6/6 | 0.244 | 5.667 | 33.500 | 0 |
| default | L2 | always_yes | -0.001 | -0.002 … 0.001 | 0.500 | 2/0 | 6/6 | 0.244 | 5.667 | 33.500 | 0 |
| default | L2 | oracle | -0.000 | -0.001 … 0.001 | 1.000 | 1/0 | 6/6 | 0.244 | 5.667 | 33.500 | 0 |
| default | L3 | always_no | 0.000 | 0.000 … 0.000 | 1.000 | 0/0 | 6/6 | 0.244 | 30.167 | 9.000 | 0 |
| default | L3 | random | 0.021 | -0.012 … 0.054 | 0.250 | 0/3 | 6/6 | 0.244 | 29.333 | 9.167 | 0 |
| default | L3 | always_yes | 0.003 | -0.047 … 0.053 | 0.875 | 2/2 | 6/6 | 0.238 | 29.833 | 8.833 | 0 |
| default | L3 | oracle | -0.002 | -0.060 … 0.057 | 0.750 | 2/1 | 6/6 | 0.244 | 30.667 | 9.667 | 0 |
| default | L6 | always_no | 0.000 | 0.000 … 0.000 | 1.000 | 0/0 | 6/6 | 0.244 | 1.167 | 38.000 | 0 |
| default | L6 | random | -0.015 | -0.042 … 0.012 | 0.500 | 2/0 | 6/6 | 0.244 | 1.167 | 38.000 | 0 |
| default | L6 | always_yes | -0.056 | -0.111 … -0.001 | 0.031 | 6/0 | 6/6 | 0.248 | 1.167 | 38.333 | 0 |
| default | L6 | oracle | -0.030 | -0.057 … -0.003 | 0.125 | 4/0 | 6/6 | 0.244 | 1.167 | 38.333 | 0 |
| default | all | always_no | -0.001 | -0.003 … 0.001 | 0.500 | 2/0 | 6/6 | 0.244 | 39.667 | 0.000 | 0 |
| default | all | always_yes | -0.063 | -0.108 … -0.018 | 0.031 | 6/0 | 6/6 | 0.242 | 38.667 | 0.000 | 0 |
| default | all | oracle | -0.050 | -0.098 … -0.003 | 0.062 | 5/0 | 6/6 | 0.244 | 39.833 | 0.000 | 0 |
| recal | L4 | always_no | 0.000 | 0.000 … 0.000 | 1.000 | 0/0 | 6/6 | 0.244 | 30.000 | 40.500 | 0 |
| recal | L4 | random | -0.100 | -0.225 … 0.025 | 0.125 | 4/2 | 6/6 | 0.257 | 30.000 | 38.500 | 0 |
| recal | L4 | always_yes | -0.070 | -0.238 … 0.098 | 0.281 | 4/2 | 6/6 | 0.248 | 30.000 | 38.667 | 0 |
| recal | L4 | oracle | -0.033 | -0.184 … 0.117 | 0.531 | 4/2 | 6/6 | 0.281 | 30.000 | 37.000 | 0 |
| recal | L6 | always_no | 0.000 | 0.000 … 0.000 | 1.000 | 0/0 | 6/6 | 0.244 | 2.500 | 68.000 | 0 |
| recal | L6 | random | -0.086 | -0.154 … -0.018 | 0.062 | 5/0 | 6/6 | 0.249 | 2.500 | 68.333 | 0 |
| recal | L6 | always_yes | -0.140 | -0.193 … -0.086 | 0.031 | 6/0 | 6/6 | 0.245 | 3.000 | 68.500 | 0 |
| recal | L6 | oracle | -0.061 | -0.106 … -0.017 | 0.062 | 5/0 | 6/6 | 0.239 | 2.667 | 68.500 | 0 |
| recal | all | always_no | -0.001 | -0.003 … 0.001 | 0.500 | 2/0 | 6/6 | 0.244 | 71.000 | 0.000 | 0 |
| recal | all | always_yes | -0.235 | -0.385 … -0.085 | 0.031 | 6/0 | 6/6 | 0.250 | 68.333 | 0.000 | 0 |
| recal | all | oracle | -0.123 | -0.284 … 0.038 | 0.156 | 4/2 | 6/6 | 0.279 | 66.833 | 0.000 | 0 |

## Calls per world (mean of the all-oracle and all-always-yes arms)

| params | leaf | ok |
|---|---|---|
| default | L1_value | 1.830 |
| default | L2_shock | 6.000 |
| default | L3_sibling | 30.670 |
| default | L6_review | 1.330 |
| recal | L1_value | 1.830 |
| recal | L2_shock | 3.830 |
| recal | L3_sibling | 28.330 |
| recal | L4_explore | 30.000 |
| recal | L6_review | 2.830 |
