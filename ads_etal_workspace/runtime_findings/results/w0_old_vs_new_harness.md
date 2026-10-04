# W0 — old (0b73557) vs new (483ea9e) harness, dev6, paired

`gpc/` is identical in both commits; only the harness differs. Old runs are simulated from a git worktree at 0b73557.

| comparison | mean_pct | t95 | p | min | max |
|---|---|---|---|---|---|
| old_l0_vs_baseline | 0.824 | 0.55 … 1.10 | 0.031 | 0.355 | 1.116 |
| new_l0_vs_baseline | 0.234 | 0.07 … 0.40 | 0.031 | 0.097 | 0.455 |
| no_gate_vs_baseline | 1.082 | 0.77 … 1.39 | 0.031 | 0.560 | 1.371 |
| old_l0_vs_new_l0 | 0.589 | 0.40 … 0.78 | 0.031 | 0.258 | 0.786 |
| old_l0_vs_no_gate | -0.255 | -0.36 … -0.15 | 0.031 | -0.429 | -0.156 |
| old_spend_vs_new_l0_pct | 6.971 | 5.36 … 8.58 | 0.031 | 5.097 | 9.096 |

Per seed:

| seed | old_l0_vs_baseline | new_l0_vs_baseline | old_l0_vs_new_l0 | old_l0_vs_no_gate | no_gate_vs_baseline | old_spend_vs_new_l0_pct | old_floor_met | old_margin | new_margin | old_actions_shipped | new_actions_shipped |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 | 0.355 | 0.097 | 0.258 | -0.204 | 0.560 | 5.398 | True | 0.258 | 0.366 | 64 | 59 |
| 11 | 0.699 | 0.128 | 0.571 | -0.295 | 0.998 | 5.097 | True | 0.601 | 0.539 | 103 | 103 |
| 23 | 0.887 | 0.101 | 0.786 | -0.156 | 1.045 | 9.096 | True | 0.367 | 0.418 | 99 | 91 |
| 42 | 0.950 | 0.394 | 0.555 | -0.254 | 1.208 | 7.441 | True | 0.444 | 0.536 | 74 | 68 |
| 101 | 0.936 | 0.228 | 0.706 | -0.429 | 1.371 | 6.793 | True | 0.227 | 0.244 | 82 | 63 |
| 202 | 1.116 | 0.455 | 0.657 | -0.190 | 1.308 | 7.999 | True | 0.337 | 0.432 | 68 | 58 |

Baseline identity check (old worktree vs today): seed 7: True
