## X2 Ablation [no_generic_cuts] — 20 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| no_op | -0.130 | -0.23 … -0.03 | nan | 0.137 | 14/6 | 0.000 | 0.00 … 0.00 | 17/20 | -0.073 | 5.161 |
| l0 | 0.000 | 0.00 … 0.00 | nan | 0.000 | 0/0 | 0.131 | 0.03 … 0.23 | 20/20 | 0.201 | 0.000 |
| no_cuts | 0.048 | -0.03 … 0.13 | nan | 0.106 | 8/12 | 0.179 | 0.12 … 0.24 | 18/20 | -0.054 | 6.248 |
| no_generic_cuts | 0.090 | 0.01 … 0.17 | nan | 0.112 | 7/13 | 0.221 | 0.15 … 0.29 | 19/20 | -0.003 | 4.976 |