# Evaluation matrix report

## search
| arm        | mean_lift_pct | p_lift_negative | floor_met_share | mean_blocked_share | mean_fallbacks | total_cost_usd | total_calls |
| ---------- | ------------- | --------------- | --------------- | ------------------ | -------------- | -------------- | ----------- |
| baseline   | 0.0           | 0.0             | 1.0             | 0.106              | 0.0            | 0.0            | 0.0         |
| no_op      | 0.157         | 0.25            | 1.0             | 0.0                | 0.0            | 0.0            | 0.0         |
| tools_only | 0.66          | 0.0             | 1.0             | 0.0                | 0.0            | 0.0            | 0.0         |

## heldout
| arm        | mean_lift_pct | p_lift_negative | floor_met_share | mean_blocked_share | mean_fallbacks | total_cost_usd | total_calls |
| ---------- | ------------- | --------------- | --------------- | ------------------ | -------------- | -------------- | ----------- |
| baseline   | 0.0           | 0.0             | 1.0             | 0.0655             | 0.0            | 0.0            | 0.0         |
| no_op      | 0.181         | 0.0             | 1.0             | 0.0                | 0.0            | 0.0            | 0.0         |
| tools_only | 0.9825        | 0.0             | 1.0             | 0.0                | 0.0            | 0.0            | 0.0         |

## perturbed
| arm        | mean_lift_pct | p_lift_negative | floor_met_share | mean_blocked_share | mean_fallbacks | total_cost_usd | total_calls |
| ---------- | ------------- | --------------- | --------------- | ------------------ | -------------- | -------------- | ----------- |
| baseline   | 0.0           | 0.0             | 1.0             | 0.1612             | 0.0            | 0.0            | 0.0         |
| no_op      | -0.09         | 1.0             | 0.8333          | 0.0                | 0.0            | 0.0            | 0.0         |
| tools_only | 0.3303        | 0.0             | 1.0             | 0.0                | 0.0            | 0.0            | 0.0         |
