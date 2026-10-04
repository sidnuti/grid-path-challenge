# Plan: slice-and-dice experiments for the System 1 harness

## Context

You want to understand the system piece by piece (each module alone, then modules together, then
the harness against the market simulator), and you are worried the current measurements aren't
the right ones (click-through, conversion, offtake).

What exists today measures one thing well: paired offtake lift of a whole policy vs. the baseline
(+0.82% over 6 seeds). It does not tell you *which* module produces the lift, whether each
module's own estimates are right, or whether offtake lift is even the right lens. Three facts
from the code shape the design:

- **No clicks exist in the simulator.** The funnel is searches → slot share → impressions →
  ad orders (Poisson on impressions × conversion) → revenue. "Conversion" = orders per impression.
- **Searches are never emitted**, so impression share is invisible to a policy. It can be
  reconstructed offline from `World.truth` + `Market._draws`.
- **Offtake = organic + ad units**, and organic is reduced by the cannibalised share of ad orders
  (true incrementality, hidden). The score uses offtake; the floor uses *direct* ROAS.

Your decisions: use the real funnel (no proxy CTR); deliver design doc + scripts + run all
cost-free experiments; include a small capped paid LLM run.

## Ground rules

- **No edits to `gpc/`, `harness/`, `harness_eval/`** (another session owns them). All new code
  goes in a new top-level folder `Ads-etal/experiments/`.
- Experiments are **offline tooling**, so they may read `World.truth` (as `harness_eval` does).
  The harness itself still never sees truth.
- Every comparison is **paired under common random numbers** (same seed, same market draws).
- Paid LLM spend is capped at **$3 total**, enforced by `LLM_MAX_USD_PER_RUN` plus a call-count
  guard in the experiment runner. Record once, replay for free.

## Deliverables

```
Ads-etal/experiments/
  EXPERIMENT_DESIGN.md      the design: questions, hypotheses, metrics, procedures, diagrams
  RESULTS.md                findings per experiment, written after the runs
  lib/
    oracle.py               truth-side measurement: searches, impression share, true incremental
                            units, true iROAS, cannibalised units (reads World.truth, Market._draws)
    funnel.py               the metric tree per cell / keyword type / SKU×city / week
    switchable_policy.py    L0 policy with on/off switches per module (composes harness functions)
    counterfactual.py       run a simulation with and without one action / one module (paired)
    scripted_llm.py         oracle / always-yes / always-no / random LLM stand-ins
    stats.py                paired lift, bootstrap CI, minimum detectable effect
  x0_measurement/ … x7_harness_eval/   one script per experiment
  results/                  raw CSV/JSON per experiment
  run_free.sh               runs every cost-free experiment
  run_paid.sh               the capped LLM slice (separate, explicit)
```

## The measurement layer (built first — everything else reports through it)

**Metric tree** (`lib/funnel.py`, with `lib/oracle.py` for the hidden parts):

| Stage | Metric | Observable to a policy? | Source |
|---|---|---|---|
| Demand | searches per market × daypart | No | oracle: replicate `market.py` search formula from truth + `_draws` + `_shock` |
| Auction | impression share by slot (1/5/9/13); slot mix | Slot mix yes, share no | `daily_facts.slot` + oracle searches |
| Delivery | impressions; CPM; spend; run-out truncation | Yes | `daily_facts`, `campaign_daily` |
| Conversion | ad orders per 1,000 impressions, by slot | Yes | `daily_facts` |
| Direct value | ad revenue; **direct ROAS** (the floor metric) | Yes | `daily_facts` |
| Incremental value | true incremental units = ad orders × ι × organic damp; **true iROAS**; cannibalised units | No | oracle |
| Outcome | organic units, total units, **offtake ₹** (the score) | Yes | `sku_city_daily` |

Click-through is stated as not modelled; the design doc says so and uses impression share and
orders-per-impression in its place.

## Experiments

Simulation cost: ~35 s each, no LLM. Seeds: search 7/11/23/42, held-out 101/202.

### X0 — Are the measurements right? (do this first)

| ID | Question | Procedure | Output |
|---|---|---|---|
| X0.1 | Do the books balance? | Accounting identities on every run: offtake = (organic + ad) × ASP; ad revenue agrees between `daily_facts` and `sku_city_daily`; count days where `max(organic − cannibal, 0)` clips (hidden cannibalisation) | pass/fail table |
| X0.2 | Is the oracle right? | Rebuild impressions from oracle searches × slot share × view ratio × OSA; compare with emitted impressions (must match to rounding on non-truncated days) | max error |
| X0.3 | What is the noise floor? | A/A (baseline vs. itself = 0 exactly); same policy across 6 seeds; a one-bid ±5% nudge → size of lift change | SD of paired lift; **minimum detectable effect** for n = 6, 12, 24 seeds |
| X0.4 | Is offtake lift the right lens? | Decompose each policy's lift into Δad units and Δorganic units, by keyword type, SKU, city, week; compare with oracle incremental units | where lift comes from; does direct ROAS mislead vs. true iROAS |
| X0.5 | Are 42 days / weekly windows hiding dynamics? | Lift per run (week), cumulative | lift curve per seed |

### X1 — Each L0 module alone, scored against truth (M1)

| Module | Question | Metric |
|---|---|---|
| `features.diagnose` / grid | Are predicted CPM, impressions, orders per slot right? | prediction vs. oracle expectation, by tier A/B/C |
| `incrementality` | Does ι recover truth? | error vs. true ι per SKU × type, across 6 seeds and windows 28/56/84 days |
| `siblings` | Is `leader_score` ranking the truly best SKU? Are wrong-leader flags real? | rank agreement with oracle value per impression |
| `headroom` | Does the allowance track real floor slack? | allowance vs. realised end-of-window slack |
| `sizing` | How far is the selection from the best feasible set? | vs. an oracle knapsack on true incremental value |
| `precheck` | Agreement with guardrails, both directions | confusion matrix |
| `shocks` | Does it find the injected shocks, and when? | precision / recall / lead time vs. `truth["shocks"]`, on dev + P1–P6 |
| `guardrails.project_actions` | Are projected Δspend / Δrevenue right? | projected vs. realised, per action (uses X3.3) |

### X2 — Modules together: which ones produce the lift? (L0 interactions)

`lib/switchable_policy.py` rebuilds the L0 pipeline with switches, reusing the harness's own
functions (`m_reprice_raises`, `m_budget_raises`, `m_base_cuts`, `m_sibling_holds`,
`compute_headroom`, `select_raises`, `filter_precheck`). A test asserts it reproduces
`HTNToolsOnly` exactly with all switches on.

Arms (each × 6 seeds, paired vs. full L0 and vs. no-op):

| Arm | What it isolates |
|---|---|
| reprice only / budget raises only / cuts only | each lever's standalone contribution |
| full − sibling holds | value of the hold rule (half the portfolio is held) |
| full − headroom gate (always allow) | value of the gate; does G8 then trim? |
| full − precheck | does precheck change outcomes or only tidiness? |
| full − budget raises, full − cuts, full − reprice | leave-one-out |
| cuts from the baseline engine + nothing else | how much of "lift" is just not doing the baseline's harmful moves |

~11 arms × 6 seeds ≈ 66 simulations ≈ 40 min.

### X3 — Harness ↔ market: how the simulator responds

| ID | Question | Procedure |
|---|---|---|
| X3.1 | Dose-response of a bid | For ~12 cells (4 per keyword type, tiers A/B), sweep the bid −50…+50% for one week; record slot mix, impression share, orders, spend, offtake; overlay the grid's prediction |
| X3.2 | Dose-response of a budget | For the 6 chronic run-out campaigns, sweep budget ×1.0…×1.5 |
| X3.3 | Causal effect of each action | For one full L0 run-week, re-simulate with each shipped action removed (paired) → true Δofftake, Δspend per action; compare with the projection the policy used |
| X3.4 | Sibling collision | In 3 contested markets, sweep the follower's bid past the leader's; confirm displacement and measure market-level offtake |
| X3.5 | Carry-over | Does an action in week t change verdicts / ladder / candidates in weeks t+1…? Trace one seed |

### X4 — The LLM layer alone (M2): "what is a leaf?"

The design doc explains a leaf in one page (trigger → prompt → typed answer → default). Experiments:

| ID | Question | Procedure | Cost |
|---|---|---|---|
| X4.1 | Does each leaf's plumbing behave? | Every fault mode × every leaf through the real stack with a scripted LLM | $0 |
| X4.2 | How does a real model answer? | ~15 fixed prompts per leaf (5 leaves) harvested from real runs, × 3 replicates, real model, `record` | paid, ~225 calls |
| | Metrics | valid-JSON rate, default rate, clip rate, answer variance across replicates, latency, tokens, **sensitivity** (flip one input, e.g. `own_action_confound`; does the answer move?) | |

### X5 — LLM-aided methods in the loop (M3): can they matter, and do they?

| ID | Question | Procedure | Cost |
|---|---|---|---|
| X5.1 | Upper and lower bounds per leaf | Scripted LLMs inside the simulation: **oracle** (answers from truth), always-yes, always-no, random; one leaf at a time, 6 seeds | $0 |
| X5.2 | Do the triggers fire? | Call counts and trigger rates per leaf at default params and at recalibrated params (review threshold ₹300, explore on) | $0 |
| X5.3 | Real model, end to end | L1 and L2 on seeds 7 and 101, `record` then `replay`; leave-one-out per leaf on seed 7 | paid, ≤ ~700 calls |

X5.1 decides whether X5.3 is worth paying for per leaf: if even the oracle leaf adds nothing, skip it.

### X6 — One scenario end to end (dev scenario, seed 7)

A traced run (`TRACE_DIR` on) of baseline, L0 and L2 side by side, written as a week-by-week
narrative: what the market did (the three injected shocks: OSA dip S2/HYD run 3, price shock MUM
K05/K06 from run 4, demand shock K03/K04 from run 5), what each policy saw, decided, shipped,
and what happened next. This answers "whole flow top to bottom" with real numbers.

### X7 — Deep dive on `harness_eval`

| ID | Question | Procedure |
|---|---|---|
| X7.1 | Determinism | Same arm, same seed, twice → identical rows |
| X7.2 | Power | Using X0.3's SD: how many seeds to detect 0.1 / 0.2 / 0.5 pp |
| X7.3 | Do the worlds stress the policy? | Add parameter-perturbed worlds (ι ±30% per type, auction σ 0.2 / 0.45, appeal shuffled) × 3 seeds; compare spread with P1–P6 |
| X7.4 | Reporting | Recompute the matrix report with lift vs. no-op and bootstrap CIs |

## How your notebook questions map

| Notebook item | Experiments |
|---|---|
| M1 → L0 | X1, X2 |
| M2 → L1/L2, separate | X4 |
| M3 "with some data — how this works / would work" | X5 |
| M4 "how this ties into L0/L1–L2" | X7 (+ X5.3 uses its arms) |
| Harness ↔ Env + Market, "what interactions look like" | X3 |
| Env + Market "how this works" | X0.2, X3.1–X3.4 |
| Deep-dive dev scenario + LLM world | X6, X4.2 |
| Scenario e2e on this system | X6 |
| Whole flow top to bottom; "leaf means what" | design doc §flow, X4 |
| Deep-dive harness_eval | X7 |
| Measurements (click-through, conversion, offtake) | X0, measurement layer |

## Execution order

1. Write `EXPERIMENT_DESIGN.md` (this plan, expanded with diagrams and exact metrics).
2. Build `lib/` + tests (oracle reconstruction check, switchable policy == `HTNToolsOnly`).
3. Run X0 → fix the measurement layer if anything fails → X1, X3 → X2, X7 → X5.1, X5.2, X4.1 → X6.
4. Paid slice (X4.2, X5.3) last, only for leaves X5.1 shows can matter; stop at $3.
5. Write `RESULTS.md`.

Estimated compute: ~250 simulations ≈ 2.5 h, run in the background in batches.

## Reuse

- `gpc.runner.simulate`, `gpc.score.summarize`, `gpc.world.build_world`, `gpc.market.Market._draws/_shock`
- `harness_eval.worlds.world_specs`, `harness_eval.run_matrix.LeafAblationLLM / run_one`
- `harness.policy._tools_only_recommend` building blocks; `harness.trace.writer`
- `runtime_feedback_improvement/scripts/*` (funnel, sizing probe, leaf traffic) as starting points

## Verification

- `pytest experiments/` — oracle reconstructs emitted impressions; switchable policy equals `HTNToolsOnly` on seed 7; A/A lift = 0.
- `bash experiments/run_free.sh` completes; every experiment writes a results file.
- Full existing suite still passes (`pytest -q tests -m "not slow"`), confirming nothing outside `experiments/` changed.
- Paid slice: metered cost printed and ≤ $3; a `replay` rerun reproduces the same results at $0 of new spend.

## Risks

- **Another session may change `harness/` mid-run.** Each results file records the file hashes of `harness/` it ran against.
- **The oracle replicates private simulator logic.** X0.2 guards against drift; if it fails, oracle-based metrics are marked unavailable rather than reported.
- **Lift differences between arms may be below the noise floor.** X0.3 sets the bar; results below it are reported as "not distinguishable".
