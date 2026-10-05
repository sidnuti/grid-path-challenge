# 04 · Experiments E1–E3: MoHOLLM on the v2 market, from one objective to constraints

> Part of [grid_design_simulator](README.md). Uses the simulator in [02](02_simulator_v2_design.md), the goal ladder G-0/G-1/G-2 in [03 §4](03_goals_macro_micro.md), and the compiler in [05](05_compiler_and_verifier.md).
> Nothing here has been run. **No paid run starts without the user's go-ahead**; the pilot → record → replay → project protocol and the ledger from `sandbox/` apply.

---

## 0. TL;DR

| Experiment | Goal level | Question | Prediction |
|---|---|---|---|
| **E1** | G-0: max brand IncRev at budget B | Does partitioned MoHOLLM find good allocations in a 12-d decision space, versus random, classical BO, an unpartitioned LLM and an oracle? | Partitioned ≥ unpartitioned; near BO; well short of the oracle on scenarios with cold-start cells |
| **E2** | G-1: three objectives (IncRev, S5 North SOV, S6 sell-through) | Does it trace a useful Pareto front? | Front shape is right; coverage of the S6 extreme is poor (cold start) |
| **E3** | G-2: nine typed constraints | Which constraint classes does MoHOLLM respect, and what does a compiler add? | Box: always. Linear-on-decision: only by encoding. Outcome: violated during search, often at the end. Compiler: zero action/state violations by construction, buffered outcome violations, small regret |

The headline the user expects ("MoHOLLM won't respect constraints; it needs a compiler") is the E3 hypothesis H4–H6. The experiment is designed so that it can **fail**: if prompt-only MoHOLLM ends feasible on outcome constraints in ≥ 90% of seeds, the hypothesis is wrong for this problem.

---

## 1. Two tracks

| Track | Search space | Faithful to the paper? | Purpose |
|---|---|---|---|
| **A (this doc)** | A 12-d continuous decision vector decoded deterministically into all bids and budgets | Yes: MoHOLLM's KD-tree partitions a box, the LLM proposes points inside a leaf | Clean test of the method and of the constraint hypothesis |
| B (later) | Hypercube-native: KD-tree over the cell embedding from report 06 (log(1+iROAS), slot-1 share, run-out, ι_est), LLM proposes hypercubes, compiler + in-box MILP | No; our adaptation | Explainability and scale; reuses E1–E3's harness |

Track A first, because it isolates what MoHOLLM itself does.

---

## 2. Decision encoding and decoder (Track A)

### 2.1 The vector x ∈ [0, 1]^12

| Dim | Meaning | Decoded range |
|---|---|---|
| x1–x3 | bid multiplier by keyword type (brand, generic, competition) | 0.5–1.5 × live bid |
| x4–x5 | bid multiplier by nest (bar, liquid) | 0.7–1.3 |
| x6–x8 | budget **share** by region (North, West, South) | stick-breaking → simplex |
| x9 | total budget scale | 0.8–1.2 × B/6 per run |
| x10 | evening/night daypart tilt | −1 night off … +1 evening ×1.2 |
| x11 | festive aggressiveness (K11, S6, window only) | 0–2 × base bid |
| x12 | brand-defence threshold (defend K01 where competitor share > x12) | 0–1 |

The box [0, 1]^12 is MoHOLLM's native space. Note two things already: the **region shares must sum to 1** (a simplex, not a box), and the **budget scale times shares** couples dimensions. Encoding the simplex by stick-breaking keeps every point in the box valid for that one constraint; it is the encoding, not MoHOLLM, that guarantees it. Constraints like C5 (North ≥ 25%) are *not* expressible as box bounds after stick-breaking.

### 2.2 Decoder = the deterministic macro → micro step

`decode(x, observation) → actions` sets every cell's bid as live bid × type mult × nest mult (× festive mult in the window), splits budget by region share, scales by x9, applies the daypart tilt and the defence rule. It is a pure function: same x and observation ⇒ same actions. It is also where Track B will later plug in the in-box MILP.

### 2.3 Black box

$$f(x) = \text{Scorer v2}\big(\text{simulate}(\text{world}_{\text{seed}},\ \text{policy}=\text{decode}(x))\big)$$

- The decoded policy is applied at each of the 6 runs (re-decoded on that run's observation, so it adapts mechanically, e.g. live bids move).
- Same world seed for every evaluation within an optimisation run (common random numbers) ⇒ the black box is deterministic per seed, and differences between x are not noise.
- **Generalisation check:** the best x from each optimiser is re-scored on 5 **held-out** world seeds of the same scenario family.
- Cost per evaluation: one 70-day world plus one counterfactual ≈ 2 simulator runs; target < 60 s, $0.

### 2.4 Two oracles

| Oracle | How | What it bounds |
|---|---|---|
| **In-space oracle** | CMA-ES with 2,000 evaluations on f(x) (no LLM), plus the best of 10 restarts | Best achievable *in this 12-d encoding* |
| **Full-space oracle** | Exact MILP over every cell's bid/budget options using **true** response parameters (expected-value mode, no Poisson noise) | Best achievable by *any* policy; the gap to the in-space oracle is the **encoding loss** |

Both are $0. Regret is reported against both.

---

## 3. Arms

### 3.1 E1 and E2

| Arm | Description |
|---|---|
| A0 | no-op, and the existing `deterministic_traversal` baseline (legacy reference) |
| A1 | uniform random search in the box (Sobol) |
| A2 | classical BO: BoTorch qLogEI (E1) / qLogEHVI (E2) — already installed in the MoHOLLM env |
| A3 | MoHOLLM **unpartitioned** (`optimization_method: mohollm`, the global baseline; note upstream's inverted naming, REPLICATION finding 7) |
| A4 | MoHOLLM **partitioned** (`SpacePartitioning`, `ScoreRegionRHVC`, cosine-annealed α; the paper's method, finding 8) |
| A5 | partitioned, with the LLM replaced by random sampling in the selected leaf (MoHOLLM's own ablation) |
| O1, O2 | in-space and full-space oracles |

A5 vs A4 measures what the LLM adds beyond the partitioning; A4 vs A3 measures what the partitioning adds.

### 3.2 E3 (constraints on), all built on A4

| Arm | How constraints are handled | Analogue |
|---|---|---|
| **A4-blind** | not mentioned; scored after the fact | G-0 policy judged on G-2 |
| **A4-prompt** | constraints written in the prompt and the task context, nothing enforced | "just tell the LLM" |
| **A4-penalty** | each constraint's violation becomes an extra minimised objective (or a summed one) | BoTorch CarSideImpact's f4 ([01 §3.6](01_landscape_and_literature.md)) |
| **A4-reject** | infeasible evaluations return the worst observed value | death penalty |
| **A4+compiler-repair** | every proposal passes the compiler: action/state constraints repaired (clamp, trim), projected constraints enforced on the projection, outcome constraints enforced with a buffer; the **repaired** point is evaluated and fed back | Chimera's guardian + repair |
| **A4+compiler-box** | as above, and the compiler also **tightens each KD leaf** to its feasible sub-box before the LLM samples (where constraints are box-expressible) and returns a reason code per rejected region | our proposal; Track B's precursor |
| O1c, O2c | oracles with constraints (CMA-ES with repair; MILP with the constraints as rows) | upper bounds under constraints |

Feeding back the **proposed** vs the **repaired** point is a known design choice (it decides what the LLM learns from). Default: repaired, as Chimera does; an ablation runs the other.

---

## 4. Metrics

### 4.1 E1 / E2

| Metric | Definition |
|---|---|
| Best IncRev @ n | best f found after n evaluations (n = 10, 25, 50, 100) |
| Regret | 1 − best/oracle, against O1 and O2 |
| Evals to 90% | first n with best ≥ 0.9 × O1 |
| HV, HV regret (E2) | hypervolume with a per-scenario reference point (from no-op and the oracle front) |
| Front coverage (E2) | share of O1's front within ε of the found front, per objective extreme |
| Generalisation | held-out-seed score of the final x, as a share of in-seed score |
| $ and tokens | from the ledger |
| Interpretability probe | does the best x encode the scenario's correct move? (sc1: S1 and S3 not both raised; sc2: K07 bid like a brand term; sc3: festive spend stops before stock-out) — scored by rule, yes/no |

### 4.2 E3 (constraints)

| Metric | Definition |
|---|---|
| **Search-time violation rate** | share of *evaluated* points violating each constraint class |
| **Final violation** | does the recommended x violate, per class, per held-out seed |
| Violation severity | normalised amount (e.g. ROAS shortfall / floor) |
| Feasible regret | 1 − best feasible / O1c |
| Wasted evals | share of evaluations spent on infeasible points |
| Proposal drift (repair arms) | ‖proposed − repaired‖, and how it changes over the run (does the LLM learn the feasible region?) |
| Explanation completeness | share of final decisions carrying a goal ledger and reason codes ([03 §6](03_goals_macro_micro.md), [05 §6](05_compiler_and_verifier.md)) |

**Why search-time violations matter.** In the simulator an infeasible evaluation is free. In production every evaluation is a week of real spend: a search that violates the ROAS floor on 40% of its evaluations has spent 40% of its weeks below the floor. E3 reports both, and the production-relevant one is search-time.

---

## 5. Hypotheses (pre-registered)

| # | Hypothesis | Falsified if |
|---|---|---|
| H1 | E1: A4 ≥ A3 and A4 ≥ A1 at n = 50 on ≥ 3 of 4 scenarios | A4 < A1 on ≥ 2 scenarios |
| H2 | E1: A4 is within 10% of A2 (classical BO) at n = 50 | A4 better than A2 by > 10% (which would be a positive surprise) or worse by > 10% |
| H3 | E1: the encoding loss (O2 − O1) is largest on sc3 (cold-start cells and stock are poorly captured by 12 global multipliers) | another scenario has a larger loss |
| H4 | E3: A4-prompt violates **action-linear** constraints (C5, C6) on ≥ 20% of evaluated points and **outcome** constraints (C4, C7, C9) on ≥ 30% | rates below half of these |
| H5 | E3: A4-penalty reaches a feasible final point on ≥ 80% of seeds but spends ≥ 30% of evaluations infeasible | < 10% wasted, or < 50% feasible finals |
| H6 | E3: A4+compiler-repair has **0** action/state violations (by construction), **0** projected violations on the projection, realised C9 violation on ≤ 10% of held-out seeds (buffered chance constraint), and feasible regret within 5 pp of A4-penalty's | any action/state violation (a compiler bug), or regret > 10 pp worse |
| H7 | E3: A4+compiler-box needs fewer evaluations than compiler-repair to reach 90% of O1c, because the LLM never samples infeasible regions | no difference |
| H8 | E1–E3: the LLM in A4 proposes more **interpretable** moves than A5 (random-in-leaf) on the probe in §4.1 | no difference |

---

## 6. Design of the runs

| Item | Choice |
|---|---|
| Scenarios | sc1, sc2, sc3, sc_all (sc4, sc5 in a second pass) |
| World seeds | 3 per scenario for optimisation; 5 held-out for generalisation |
| Optimiser seeds | 1 per world seed (the world seed sets both); 3 for the cheapest arms if variance matters |
| Evaluation budget | 50 (paper default) and 100; initial design 5 Sobol points shared by all arms |
| LLM | `qwen/qwen3.7-flash` via OpenRouter (the user's MoHOLLM choice), reasoning effort as in the earlier pilot |
| Determinism | `PYTHONHASHSEED=0`, content-seeded shuffles, CachingTransport record/replay (sandbox findings 16–20) |
| Integration | new `GridMarketBenchmark(BENCHMARK)` in `sandbox/mohollm/adapters/` with `evaluate_point`, `n_obj`, `metrics`, bounds; compiler arms wrap `evaluate_point` and, for compiler-box, the region bounds. Upstream stays byte-identical |
| Cost control | pilot = 2 evaluations per LLM arm on sc1, recorded and replayed at $0, then projected. Needs a **new ledger cap** (the existing `mohollm_qwen` cap is $2 for the replication). Ask before spending |

Order of work: (1) simulator v2 steps 1–5 ([02 §10](02_simulator_v2_design.md)); (2) decoder, oracles, A0–A2 and A5 at $0; (3) compiler ([05](05_compiler_and_verifier.md)) and its tests at $0; (4) LLM pilot; (5) full E1 → E2 → E3 after approval.

---

## 7. What each outcome would mean

| Outcome | Reading | Next step |
|---|---|---|
| H1, H2 hold; H4–H6 hold | MoHOLLM is a reasonable explorer; constraints need a compiler. The user's thesis stands | build Track B with the compiler at the centre |
| H1 holds, H2 fails (A4 ≫ BO) | the LLM's priors help here (e.g. reading "festive" and "gift set") | invest in the proposer; test priors on cold-start cells |
| H1 fails (A4 ≤ random) | 12 global multipliers are too coarse, or the LLM adds noise | Track B directly; the in-box MILP does the work, the LLM only picks boxes |
| H4 fails (prompt-only is feasible) | outcome constraints were slack in these scenarios | tighten C4/C9 or the B, re-run E3; the compiler is then about explanation, not safety |
| H6 fails on action/state | compiler bug | fix; this is what the property tests in [05 §5](05_compiler_and_verifier.md) exist for |

---

## Assumptions and caveats

| # | Assumption |
|---|---|
| \*1 | Track A's 12 global multipliers cannot express cell-level moves (e.g. "raise S3 on K04 in BLR only"). Its optimum is an encoding-limited optimum; O2 − O1 measures how limited. |
| \*2 | A deterministic black box per world seed removes evaluation noise that a production optimiser would face. Held-out seeds partly restore it. |
| \*3 | MoHOLLM was designed for static black-box functions. Our f(x) wraps a 6-run sequential process, decoded open-loop from x; adaptive (closed-loop) policies are outside Track A. |
| \*4 | Hypothesis thresholds (20%, 30%, 80%, 10 pp) are judgement calls set before running, so they can be wrong in either direction; they are not derived from power calculations. |
| \*5 | LLM cost per evaluation is unknown until the pilot. MoHOLLM's prompt size grows with the in-leaf history, and reasoning models add hidden tokens (sandbox finding 20). |
| \*6 | `qwen3.7-flash` replaces the paper's models; results test whether the *method* transfers, not a replication of reported numbers. |
