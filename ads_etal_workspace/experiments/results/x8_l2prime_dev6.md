<!-- code hashes: 951690e77e25, 9b13104d1e6c, c6db3cafe0e1  (MIXED) -->
# X8 · L2′ on dev6 (6 worlds)

Paired offtake lift (eval window) vs the cached `l0` and `baseline` arms in the same world. t-CI, exact sign-flip p. `true_iroas_vs_l0` = change in realised incremental revenue per rupee (offline, from hidden truth). Costs are per weekly run.

| arm | worlds | vs_l0_pct | ci_l0 | p_l0 | worse/better | vs_baseline_pct | floor_met | min_margin | true_iroas_vs_l0 | usd_per_run | tokens_per_run | calls_per_run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_op | 6 | -0.068 | -0.189 … 0.052 | 0.250 | 3/3 | 0.165 | 6/6 | 0.009 | -0.123 | 0.000 | 0.000 | 0.000 |
| l2p_aug_rules | 6 | 0.114 | -0.283 … 0.511 | 0.500 | 1/5 | 0.349 | 6/6 | 0.319 | 0.019 | 0.000 | 0.000 | 0.000 |
| l2p_nat_rules | 6 | 0.207 | -0.131 … 0.545 | 0.188 | 1/5 | 0.442 | 6/6 | 0.138 | -0.051 | 0.000 | 0.000 | 0.000 |
| l2p_aug_random | 6 | -0.616 | -1.024 … -0.207 | 0.062 | 5/1 | -0.384 | 6/6 | 0.393 | 0.018 | 0.000 | 0.000 | 0.000 |
| l2p_nat_random | 6 | -0.863 | -1.262 … -0.463 | 0.031 | 6/0 | -0.631 | 6/6 | 0.058 | -0.109 | 0.000 | 0.000 | 0.000 |
| l2p_aug_oracle | 6 | 0.876 | 0.684 … 1.068 | 0.031 | 0/6 | 1.112 | 6/6 | 0.598 | 0.174 | 0.000 | 0.000 | 0.000 |
| l2p_nat_oracle | 6 | 0.962 | 0.800 … 1.124 | 0.031 | 0/6 | 1.198 | 6/6 | 0.439 | 0.117 | 0.000 | 0.000 | 0.000 |

## Behaviour (per world, mean)

| arm | proposed_per_run | shipped_per_run | blocked_share | intents_per_run | rejects_per_run | from_intents_per_run | fallback_runs | pause | budget_cut | budget_raise | dayparts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no_op | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_rules | 17.556 | 17.361 | 0.012 | 21.833 | 8.361 | 12.250 | 0.000 | 0.000 | 0.000 | 10.167 | 0.000 |
| l2p_nat_rules | 12.417 | 11.778 | 0.055 | 21.944 | 8.389 | 12.417 | 0.000 | 0.000 | 0.000 | 8.333 | 0.000 |
| l2p_aug_random | 19.167 | 19.139 | 0.001 | 12.000 | 3.528 | 7.611 | 0.000 | 8.000 | 10.000 | 10.667 | 5.000 |
| l2p_nat_random | 7.639 | 7.306 | 0.044 | 12.000 | 3.444 | 7.639 | 0.000 | 8.000 | 10.000 | 1.167 | 5.000 |
| l2p_aug_oracle | 16.194 | 16.194 | 0.000 | 16.222 | 9.083 | 7.139 | 0.000 | 0.000 | 0.000 | 17.167 | 0.000 |
| l2p_nat_oracle | 7.361 | 7.361 | 0.000 | 16.444 | 9.083 | 7.361 | 0.000 | 0.000 | 0.000 | 15.167 | 0.000 |

## Intent verbs (total)

- `no_op`: {}
- `l2p_aug_rules`: {'raise_budget': 127, 'lead_market': 131, 'hold': 194, 'raise_bid': 93, 'cut_bid': 241}
- `l2p_nat_rules`: {'raise_budget': 133, 'lead_market': 126, 'hold': 194, 'raise_bid': 95, 'cut_bid': 242}
- `l2p_aug_random`: {'set_dayparts': 43, 'cut_budget': 64, 'lead_market': 61, 'pause': 49, 'cut_bid': 55, 'raise_bid': 50, 'hold': 52, 'raise_budget': 58}
- `l2p_nat_random`: {'set_dayparts': 43, 'cut_budget': 64, 'lead_market': 61, 'pause': 49, 'cut_bid': 55, 'raise_bid': 50, 'hold': 52, 'raise_budget': 58}
- `l2p_aug_oracle`: {'raise_bid': 360, 'cut_bid': 121, 'raise_budget': 103}
- `l2p_nat_oracle`: {'raise_bid': 360, 'cut_bid': 121, 'raise_budget': 111}


Ledger spend so far: $0.038
