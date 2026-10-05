# 03 · Goals: one global iROAS objective, then sub-objectives, then constraints; macro vs micro made specific

> Part of [grid_design_simulator](README.md). Extends GoalSpec from `explore-and-understand/05_l2dprime_macro_planner_and_explainability.md` §5 and the macro/micro section of report 06 §5.
> The simulator mechanics referenced here (sibling cannibalization, intent mix, calendar, stock) are in [02](02_simulator_v2_design.md).

---

## 0. TL;DR

1. **"Maximise iROAS" is not yet a well-posed goal.** A ratio is maximised by spending ₹1 on the single best cell. It needs a budget, a margin, or a marginal floor. We fix the global objective as **maximise brand-level incremental revenue at a fixed budget B**, which is the same thing as maximising iROAS at that budget, and report the other two forms.
2. **Macro vs micro is a difference of scope, horizon, owner and unit, not of size.** A macro goal is about a portfolio aggregate over weeks, owned by a brand or CMO, in money or share. A micro goal is about a cell or a small hypercube over days, owned by an operator, in delivery terms (slot share, pacing, stock cover).
3. **They meet through prices.** The macro problem has a budget price λ and a floor price μ. Each micro goal, once written as a constraint, gets its own shadow price: *what that goal costs the macro objective*. "S5 slot-1 ≥ 60% on K08 in DEL costs ₹410 of brand-incremental revenue per week" is the explanation format.
4. **With cannibalization on, SKU-level goals and brand-level goals disagree.** S1 can hit "+10% units" by taking units from S3. Macro goals must be scored at brand level; micro goals that are stated per SKU need a "not from siblings" clause or they reward cannibalization.
5. **Goal ladder for the experiments** ([04](04_experiment_protocol.md)): G-0 global objective only → G-1 add 2 sub-objectives (a Pareto problem) → G-2 add 9 typed constraints (feasibility problem).

---

## 1. Making "iROAS" a well-posed objective

Let x be the policy's decisions, Spend(x) its spend over the horizon, and IncRev(x) the **brand-level** incremental revenue from the scorer v2 counterfactual.

| Form | Statement | Optimum behaviour | When it is the right goal |
|---|---|---|---|
| Ratio alone | max IncRev/Spend | degenerate: tiny spend on the top cell | never as a stand-alone objective |
| **F1 fixed budget** | max IncRev s.t. Spend = B | spends B, ordered by marginal iROAS | **the global objective for E1**, B = warm-up spend × 6 weeks |
| F2 profit | max m·IncRev − Spend (m = contribution margin) | spends until marginal iROAS = 1/m | when the budget is genuinely flexible |
| F3 marginal floor | max IncRev s.t. marginal iROAS ≥ θ on every rupee | stops each cell where its marginal falls to θ | when finance sets a hurdle rate |

Two scoring rules apply to all forms:
- **Brand level, not SKU level.** IncRev counts expansion + stolen only. Sibling transfers are zero ([02 §2.4](02_simulator_v2_design.md)).
- **Horizon includes the tail.** With the calendar on, IncRev runs to the end of the pull-forward window, so festive "lift" that was borrowed from later weeks is netted out.

The legacy direct-ROAS floor (G8, ≥ 0.98 × warm-up) is **not** part of G-0. It comes back in G-2 as a constraint. Keeping it out of G-0 shows how much it costs: in the current world it already turns low-ι brand keywords into ROAS ballast (linkage report caveat \*6).

---

## 2. What a goal is: the typed record

```
Goal {
  id:        "G-NORTH-SOV"
  kind:      objective | constraint | target | preference
  scope:     hypercube expression, e.g. sku∈{S5} × city∈North × kw∈{K08,K01,K03} × phase∈{normal}
  metric:    inc_revenue | units | slot1_share | spend | droas | iroas | sell_through | category_share | sibling_share
  basis:     direct | sku_incremental | brand_incremental          # what "revenue" means
  aggregate: sum | ratio_of_sums | min_over_cells | max_over_cells
  op, value: ≥ 0.60
  horizon:   run | 6_runs | event_window | event_window+tail
  chance:    deterministic | P(≥ 0.9) | expected                   # how it is judged under noise
  priority:  1..n (lexicographic tiers) or weight
  owner:     cmo | brand_manager | operator | finance | platform_policy
  provenance:[{field, quote}]                                     # the sentence it came from
}
```

`basis` and `chance` are the two fields the old GoalSpec lacked. Without `basis`, "ROAS ≥ 3" is ambiguous between direct and incremental, a factor of up to 6 on brand keywords. Without `chance`, a goal on a realised outcome cannot be verified by a deterministic compiler ([05 §3](05_compiler_and_verifier.md)).

---

## 3. Macro vs micro, specifically

### 3.1 The hierarchy

| Level | Node | Example | Typical owner |
|---|---|---|---|
| L0 | Portfolio (brand) | all Aurel | CMO, finance |
| L1 | Category nest | bar soap, liquid | brand manager |
| L2 | SKU, or region | S5, North | brand manager, regional lead |
| L3 | SKU × city | S5 × DEL | operator |
| L4 | Cell: SKU × city × keyword | S5 × DEL × K08 | operator |
| L5 | Cell × daypart | … × evening | operator / platform |
| L6 | Bid, budget value | ₹420 CPM | the optimiser |

### 3.2 The distinction

| Property | Macro goal | Micro goal |
|---|---|---|
| Scope | L0–L2 aggregate (a large hypercube) | L3–L5 (a small hypercube) |
| Horizon | ≥ 1 run, often the event window or quarter | a day to a run |
| Unit | ₹ incremental, category share, iROAS | slot share, pacing, stock cover, delivery |
| Owner | CMO, brand manager, finance | operator, platform rules |
| Who can verify it | only the scorer, after the fact (outcome) | often the compiler, before acting (action or projection) |
| Typical kind | objective, or soft target | hard constraint, or preference |
| Failure mode | silently under-delivers | blocks or wastes spend locally |

A goal like "North +5% units" is **macro** even though it is about one region: it is an L2 aggregate over weeks, in business units. A goal like "never let S6 ads run with < 2 days of stock cover" is **micro** even though it applies everywhere: it is an L3 delivery rule judged per day.

### 3.3 How they meet: prices

Write the macro problem with the micro goals as constraints:

$$\max_x\ \text{IncRev}(x)\quad\text{s.t.}\quad \text{Spend}(x)\le B\ [\lambda],\quad \text{dROAS}(x)\ge R\ [\mu],\quad g_j(x)\ge v_j\ [\nu_j]\ \ \forall j\in\text{micro}$$

At the optimum each cell receives spend until its marginal value equals the prices it touches:

$$\iota^{\text{brand}}_i\, r_i'(s_i) + \mu\,(r_i'(s_i) - R) + \sum_j \nu_j\,\frac{\partial g_j}{\partial s_i} = \lambda$$

- λ and μ are the **macro prices**, the same duals Balseiro et al. pace online ([01 §3.5](01_landscape_and_literature.md)).
- ν_j is the **price of micro goal j**: the IncRev lost per unit of tightening. ν_j = 0 means the goal costs nothing (not binding). That gives the explanation sentence for every goal, binding or not.
- **Macro → micro handoff.** Each hypercube H receives an envelope (min/max spend, the prices λ, μ). The in-box optimiser only has to beat λ inside H; it never reasons about the whole portfolio. This is the "macro → micro" step in the user's turn-n loop.
- **Micro → macro feedback.** If micro goals are infeasible inside H's envelope, the box returns an IIS (irreducible infeasible subset) instead of a plan, and the macro layer either relaxes or re-prices.

### 3.4 Conflict taxonomy, with grid examples

| Conflict | Example in v2 | Resolution |
|---|---|---|
| **Aligned** | "max IncRev" and "defend K01 where Velora conquests" (defence is incremental when conquest is present, [02 §3.2](02_simulator_v2_design.md)) | none needed; ν ≈ 0 |
| **Competing** (share a budget) | "North +5% units" vs "max IncRev" (Aurel is weak in North, so North rupees earn less) | price it: ν_North; or a Pareto front |
| **Contradictory** (infeasible) | "+20% organic S1" (ads cannot raise organic without halo, finding \*8); "S6 sell-through ≥ 95%" with stock 2,400 in DEL and demand cap 1,900 | IIS + minimal relaxation ("feasible at 79%") |
| **Measurement mismatch** | "direct ROAS ≥ 4.5" vs "max brand IncRev": brand terms help the first and barely the second | make `basis` explicit; show the cost of the direct floor as μ |
| **Level mismatch** (cannibalization) | "S1 +10% units" met by taking S3's units on K03 | restate with `basis: brand_incremental` or add `sibling_share ≤ 30%` |
| **Temporal** | "festive week +40%" vs "event window + tail IncRev" (pull-forward) | score over window+tail; the week goal becomes a target, not the objective |

### 3.5 Aggregation pitfalls the scorer must avoid

- Portfolio iROAS is a **ratio of sums**, not a mean of cell iROAS. A policy can raise every cell's iROAS and lower the portfolio's (Simpson-style mix shift).
- **Sum of SKU incremental ≠ brand incremental** whenever siblings share a nest. With λ_bar = 0.35, the gap on K03/K04 can be most of the SKU number.
- **Average vs marginal**: goals are set on averages; allocation must use marginals (linkage caveat \*5). A cell can beat its average-ROAS goal while its last rupee is far below λ.

---

## 4. The goal ladder used in the experiments

### G-0: one global objective

> **max brand-level IncRev over the horizon (incl. tail), Spend = B.** Nothing else.

Only box bounds on the decision vector (they define the search space). Report direct ROAS, sibling share, stock outcomes, but do not constrain them.

### G-1: add sub-objectives (a 3-objective problem)

| Objective | Scope | Why it conflicts with f1 |
|---|---|---|
| f1 = brand IncRev | L0 | — |
| f2 = S5 slot-1 share on {K08, K01, K03} in North | L2–L4 (new launch, 45 days old) | North is Velora-strong; S5 competes with S1/S3 on K01/K03 (68–80% displacement today) |
| f3 = S6 sell-through by event end | L2 (festive SKU) | cold start, CPM ×1.4, and a stock-out stops ads; pushing it can buy pull-forward |

Scored by hypervolume with a fixed reference point per scenario (computed from the no-op and the oracle). Scalarised views (weighted, Chebyshev, lexicographic) are reported for comparison.

### G-2: add constraints, typed by how they can be checked

| # | Constraint | Class | Checkable before acting? |
|---|---|---|---|
| C1 | Spend ≤ B per run; bid in [₹200, ₹10k]; bid step ±50%; budget step +50%/−30% (G1, G2, G6) | **action** | yes, exactly |
| C2 | No raise where 3-day OSA < 60% (G4); no S6 ads with < 2 days stock cover | **state-gated** | yes, from observations |
| C3 | No spend on K11 or S6 outside the live window | **action** (calendar) | yes, exactly |
| C4 | Projected portfolio direct ROAS ≥ 0.98 × warm-up (G8) | **projected outcome** | on the projection only |
| C5 | North share of spend ≥ 25% each run | **action** (linear on decisions) | yes, exactly |
| C6 | Competitor-keyword spend ≤ 10% of total | **action** | yes, exactly |
| C7 | K01 slot-1 share ≥ 70% in any city where a competitor bids on it | **projected outcome** | on the projection, via the slot model |
| C8 | Sibling share of attributed orders ≤ 30% in every nest × city | **realised outcome** (needs truth or a lift test) | no; only via an estimate with a buffer |
| C9 | **Realised** portfolio direct ROAS ≥ 0.98 × warm-up over the horizon | **realised outcome** | no; chance constraint, P ≥ 0.9 |

The classes matter for [04](04_experiment_protocol.md) and [05](05_compiler_and_verifier.md): a compiler guarantees **action** and **state-gated** constraints by construction; it guarantees **projected** constraints only relative to its projection; it can only **buffer** realised-outcome constraints (Chimera's 1% safety buffer is the same idea for rounding).

---

## 5. Scenario-specific macro/micro examples

| Scenario | Macro goal (owner) | Micro goals (owner) | What makes it hard |
|---|---|---|---|
| sc1 cannibal | "Bar soap +5% brand IncRev, all cities" (brand mgr) | "S3 never below slot 5 on K04 in BLR" (operator) | raising S1 and S3 together mostly trades share; the micro goal forces S3 visibility that cannibalizes S1 |
| sc2 brand assoc | "Grow body-wash share vs Nimbus" (brand mgr) | "Defend K01 slot-1 where conquested" (operator) | K05 is Nimbus-owned: high ι, low conversion; K07 looks generic but is ours |
| sc3 festive | "Max IncRev over festive window + tail" (CMO) | "S6 sell-through ≥ 85% per city", "no ads below 2 days cover" (ops) | cold start, CPM inflation, pull-forward, stock-out; the two micro goals pull opposite ways near stock-out |
| sc4 seasonal | "Hold iROAS through monsoon" (finance) | "K12 bids follow the season" (operator) | season masquerades as ad lift; a micro rule that "follows" the season can look brilliant and add nothing |

---

## 6. Explainability: the goal ledger

Every decision record from [05](05_compiler_and_verifier.md) carries a goal ledger:

| Goal | Kind | Status | Binding? | Price | Sentence |
|---|---|---|---|---|---|
| f1 IncRev | objective | ₹1.92L | — | λ = 2.3 | "Last rupee anywhere earns 2.3 incremental" |
| C4 dROAS floor | constraint | 4.61 ≥ 4.54 | yes | μ = 0.4 | "The direct floor costs ₹2.1k/week; it keeps K01 funded" |
| C5 North ≥ 25% | constraint | 25.0% | yes | ν = 0.7 | "North minimum costs ₹410/week" |
| C8 sibling ≤ 30% | constraint | 22% (est., CI 15–31%) | no | 0 | "Not binding; estimate from the K03 holdout" |
| f2 S5 North SOV | objective | 52% | — | — | "Front point 3 of 7; +8 pp costs ₹1.3k IncRev" |

(Values illustrative; nothing is built yet.)

---

## Assumptions and caveats

| # | Assumption |
|---|---|
| \*1 | B = warm-up spend × 6 weeks keeps E1 comparable with the legacy score; a different B changes which cells are marginal. |
| \*2 | The KKT condition in §3.3 assumes concave, differentiable response. The real grid is discrete (bid options), so the prices come from the LP relaxation or from the MILP's duals at the optimal basis, and are approximate at breakpoints. |
| \*3 | The goal ladder's thresholds (25% North, 10% competitor, 30% sibling, 70% K01 defence) are illustrative policy choices, picked so that each constraint binds in at least one scenario. |
| \*4 | f2 and f3 are proxies for what a brand manager means by "launch visibility" and "festive success". Other proxies (new-to-brand buyers, sell-through value) would change the front. |
| \*5 | Brand-level IncRev needs the counterfactual, which only the simulator has. In production it would come from lift tests and models, with error that this design does not represent in G-0. |
