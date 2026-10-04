## X2 Ablation [reserved10] — 10 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| no_op | -0.081 | -0.22 … 0.06 | 0.230 | 0.178 | 6/4 | 0.000 | 0.00 … 0.00 | 7/10 | -0.079 | 4.842 |
| l0 | 0.000 | 0.00 … 0.00 | 1.000 | 0.000 | 0/0 | 0.081 | -0.06 … 0.23 | 10/10 | 0.140 | 0.000 |
| gate_min3000 | 0.763 | 0.56 … 0.96 | 0.002 | 0.249 | 0/10 | 0.845 | 0.56 … 1.13 | 9/10 | -0.015 | 8.315 |
| no_headroom_gate | 0.799 | 0.58 … 1.02 | 0.002 | 0.272 | 0/10 | 0.881 | 0.58 … 1.18 | 9/10 | -0.019 | 8.727 |