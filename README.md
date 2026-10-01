# Grid Path Challenge

A sandbox copy of the decision Gobblecube's engine makes every week: **turn a priced grid of ad
options into campaign actions.** The market is synthetic and the brand fictional. The data is
calibrated to aggregated production Blinkit numbers (see `CALIBRATION.md`).

**The objective:** increase total SKU offtake (ad + organic, ₹) over 6 weekly runs while keeping
portfolio direct ROAS at or above the warm-up level (−2% tolerance).

## The world

| | |
|---|---|
| Brand | Aurel (fictional), Bath & Body. Competitors Velora and Nimbus |
| SKUs | 5 (`data/base/products.csv`): two soaps, a body wash, a shower gel, a new kids' bar |
| Cities | 5 (`cities.csv`): Delhi NCR, Mumbai, Bengaluru, Hyderabad, Pune |
| Keywords | 10 (`keywords.csv`): 2 brand, 6 generic, 2 competitor. Relevance per SKU in `keyword_sku.csv` |
| Campaigns | 25, one per SKU × city (`campaigns.csv`). Each bids on its SKU's relevant keywords (`campaign_keywords.csv`) |
| Cells | 110 = campaign × keyword. The media plan (`plan.csv`) gives each a ₹/day budget, a direct-ROAS goal and a marginal floor |
| Grid | cell × ad slot (1 / 5 / 9 / 13) × daypart (night / morning / afternoon / evening) |
| Timeline | 28 warm-up days (3–30 Aug 2026), then 6 weekly runs. Each run: decide → guardrails → apply → 7 days of market |

## How a run works

```
observed data ──► 1 GRID ──► 2 LOOP ──► 3 TRAVERSAL ──► 4 LEDGER ──► 5 GUARDRAILS ──► hidden market ──► next week's data
                  gpc/engine/grid.py      traversal.py     ledger.py     gpc/guardrails.py   gpc/market.py
                            loop.py
```

1. **Grid** (`engine/grid.py`): from the last 28 days it estimates CPM, impressions, orders and revenue for every
   cell × slot × daypart. Capacity is read from days the campaign did not run out of budget. Thin evidence is shrunk.
2. **Loop** (`engine/loop.py`): one verdict per cell: CLEARS / MISSES / THIN against the plan's goal, with a
   **patience ladder** that paces cuts (3 / 5 / 7 miss-days → up to 10% / 25% / 50% of spend).
3. **Traversal** (`engine/traversal.py`), always in this order:
   - **bid first**: the best bid per cell from ±5…50% steps;
   - **then money**: freed rupees and a growth pool fund bid raises and budget-bound campaigns. A rupee moves only
     when the receiver's marginal ROAS is ≥ 1.2× the source's with P > 0.8, solved as one transport LP;
   - **then hours**: switch off a daypart where nothing earns its floor.
4. **Ledger** (`engine/ledger.py`): decisions become actions on real levers. A budget raise is sized by absorption
   (the share of days the campaign runs out).
5. **Guardrails** (`guardrails.py`): G0–G8. Every policy's actions pass through here; a policy cannot skip it.

`viewer/grid_path_viewer.html` shows every step for every run and cell. Open it first.

## Your policy

```python
# my_policy.py
import pandas as pd
from gpc.policy import Policy, DeterministicTraversal

class MyPolicy(Policy):
    name = "mine"
    def recommend(self, obs) -> pd.DataFrame:
        # obs: base tables + plan, current campaigns and bids, all observed data before obs.day,
        #      obs.roas_floor. Never the market's internals.
        # return columns: campaign_id, keyword_id, action_type, new_value, reason
        ...
```

Action types: `increase_cpm` / `reduce_cpm` / `pause_keyword` (need `keyword_id`), `increase_budget` /
`reduce_budget`, `set_dayparts` (`new_value` = e.g. `"morning,afternoon,evening"`).

```bash
make setup
make score POLICY=my_policy:MyPolicy     # vs no-op and the baseline, dev scenario (~2 min)
make run   POLICY=my_policy:MyPolicy     # one policy, run by run
make viewer                              # rebuild the viewer for the baseline
make test
```

Reference points on the dev scenario:

| Policy | Offtake ₹/day | vs no-op | Direct ROAS | Floor 4.54× |
|---|---:|---:|---:|---|
| No-op | 4,09,146 | — | 4.60× | met |
| Baseline traversal | 4,09,517 | +0.1% | 4.97× | met |
| Naive scaler (`examples/naive_scaler.py`) | 4,22,505 | +3.3% | 3.99× | **fails** |

## Rules

- A policy reads only its `Observation`. Importing `gpc.market` or reading `World.truth` is disqualifying.
- You may change anything in `gpc/engine/`: it is the baseline, not the harness. Do not change `gpc/market.py`,
  `gpc/guardrails.py`, `gpc/runner.py` or `gpc/score.py`; we score with our copies.
- We also score on a private **eval scenario**: same mechanics, different seed, and shocks in different places
  and at different times. Do not tune to dev's shocks.

## Data

`data/` is the baseline's trajectory on the dev scenario:

- `data/base/`: every public table above, plus `industry_rank_curve.csv` and `dayparts.csv` (priors)
- `data/observed/`: `daily_facts.csv` (campaign × keyword × daypart × slot × day), `campaign_daily.csv`
  (budget, spend, run-out), `sku_city_daily.csv` (on-shelf availability, ad / organic / total units, offtake)
- `data/runs/run_0N/`: every intermediate table of that run (`grid`, `verdicts`, `pacing`, `bid_choices`,
  `bid_options`, `sources`, `demands`, `transfers`, `dayparts`, `ledger_log`, `proposed_actions`,
  `guardrail_log`, `actions`, `summary.json`)
