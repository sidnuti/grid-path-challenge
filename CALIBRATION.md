# Calibration

The market's shape is taken from aggregated, multi-brand Blinkit production data (pulled 1 Oct 2026).
No brand-level or client-identifying figure is used. Synthetic choices are marked.

## From production aggregates

| Quantity | Value used | Source (aggregated) |
|---|---|---|
| Ad slot positions | 1, 5, 9, 13 | Industry rank curve. These four positions hold ≈ 91% of observed rows |
| Impressions vs slot 1 | 1.00 / 0.41 / 0.17 / 0.08 | Same, median ratio paired per keyword |
| Orders per impression | 0.85% / 0.60% / 0.39% / 0.29% | Same, median |
| Daypart search share | night 11% · morning 26% · afternoon 33% · evening 30% | Rank × hour bid curve, observations by hour |
| Bid level by hour | flat (0.98–1.01) | Same, median bid relative to keyword mean |
| Rank-1 CPM | ₹210–₹470 by keyword | Industry rank curve: median ₹300, IQR ₹209–₹500 |
| Direct ROAS, generic keywords | median 3.5×, p10 1.7×, p90 10.8× | MMM cell outputs |
| Direct ROAS, competitor keywords | median 1.75×, p10 1.0× | Same |

What the simulator produces in the 28-day warm-up: generic 2.5–7.0×, competitor 0.8–1.9×, brand 16–19×.
Spend is ₹18.9K/day, direct ROAS 4.63×, 20% of units come from ads, and campaigns run out of budget on
30% of campaign-days.

## Synthetic, chosen to be plausible

| Quantity | Value | Why |
|---|---|---|
| Slot price vs slot 1 | 1.00 / 0.94 / 0.86 / 0.76 | Production's paired CPM ratio is near-flat (1.00 / 1.00 / 0.92 / 0.80), partly a selection effect |
| Competitor bid spread | log-normal σ = 0.30 per auction (dev) | Gives a smooth, diminishing return to bidding up |
| Keyword intent | brand 2.4–2.6, generic 0.9–1.2, competitor 0.45–0.5 | Reproduces the ROAS ranges above |
| Incrementality (share of ad orders that would not have happened anyway) | dev: brand 0.15–0.18, generic 0.50–0.70, competitor 0.85; × 0.6 when the SKU ranks top-3 organically | MMM cell outputs show marginal ROI far below average direct ROAS, most of all on brand terms |
| Search volumes, prices, organic units | in `data/base/` | Scaled to a mid-size personal-care brand |

## Hidden from policies

Keyword intent and incrementality, SKU appeal, organic damping, the competitor bid spread, noise levels and
the scheduled shocks (an availability drop, a competitor bidding up, a demand rise) come from the scenario
file. Per-keyword curve deviations and city × keyword affinity are drawn from the seed. Dev's file is
`gpc/scenarios/dev.json`. The eval scenario uses different values and is not in this repo.
