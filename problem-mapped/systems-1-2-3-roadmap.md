# Systems 1 / 2 / 3 — roadmap

Companion to `A1-implementation.md`. Arnab's "three systems" note set the long-term shape this
build is one piece of. This doc says, concretely, which parts are built, which are hooks only, and
which are design notes — and how the trigger model (T, T+5m, T+1h, T+3h) maps onto what actually
runs today (once per week, per `gpc.runner`'s 7-day run cadence).

## System 1 — built (this repo, `harness/`)

Type-1, real-time: a fixed-depth, data-informed procedural chain reacting to events and campaign
feedback. The challenge's own cadence is weekly (`gpc.world.RUN_DAYS = 7`), so System 1 here fires
once per run, not at T/T+5m/T+1h/T+3h literally — those finer triggers describe the *intended*
production cadence this harness's logic would run at outside the challenge's weekly-decision
constraint, not something simulated inside it. The chain itself (`HTNHarness.recommend`, M0-M5):

```
T1 Diagnose (tools)        grid, verdicts, pacing, engine's own chosen bids (gpc.engine.*)
T2 Estimate                 incrementality (iota), siblings/leader, shocks (harness/tools/*)
T3 Leaves (L1/L2 depth)     L1 raise-size trust, L2 shock confirm, L3 sibling tie-break,
                            L4 explore — each narrows a mechanical candidate, never invents one
T4 Sizing                   Lagrangian knapsack over raises, bounded by the headroom allowance
T5 Review (L2 depth only)   L6, veto-only, over large raises
T6 Verify                   precheck (mirrors G0/G3/G4/G5/G7) -> gpc.guardrails has final say
T7 Emit                     actions + RunTrace (harness/trace/*, off unless TRACE_DIR is set)
```

Depth is `params.depth`: **L0** tools-only (`HTNToolsOnly`, M1's gate target), **L1** + leaves
(M3), **L2** + the review pass. Fail-soft at three levels (a leaf failure -> its default; a
guardrail failure -> the guardrail's own clamp/trim, unchanged from `gpc.guardrails`; any other
exception -> `DeterministicTraversal`) — see `A2-tests-and-scenarios.md`'s fail-soft section.

**Status**: M0-M4 done and gated (floor met + lift on 4 search seeds + 1 held-out seed, LLM layer
tested end-to-end including one live call). M5 (trace + S2 hooks) done this session. M6 is this
set of docs.

## System 2 — hooks only (`harness/s2/`, `harness/trace/`)

Type-2, offline cron: a feedback learner over playbook arms with reasoning-depth choices, reading
System 1's traces and proposing updated System 1 params. Built as hooks, not a real learner:

- **`trace/schema.py` + `writer.py`** — `RunTrace` (one JSONL line per run: params version,
  depth, an `obs_digest` hash, candidate/precheck/action counts, every leaf call's outcome,
  cumulative LLM usage, fallback reason) is what a real learner would read. Off by default
  (`TRACE_DIR` unset); on, it appends to `TRACE_DIR/<policy_name>.jsonl`.
- **`s2/arms.py`** — `ArmRegistry`: named `Params` overrides (headroom front/back-load, shock-z
  2.0/2.5/3.0, explore on/off, depth L0/L1/L2). **Not built**: a per-keyword-type depth override
  ("L0 for competitor, L2 for brand") — `Params.depth` is a single global field; that's a real
  plumbing change (every depth check in `policy.py`/`llm_methods.py` would need a
  `depth(keyword_type)` lookup instead of a scalar comparison), not a registry entry, and isn't
  built just because the plan's one-liner mentions it.
- **`s2/reward.py`** — `pair_reward`/`aggregate_reward`: paired lift %, a floor gate (`score =
  None` if any world in the group misses the floor — an arm can't look good by averaging over
  the worlds where it didn't break anything), $ cost, P(lift < 0).
- **`s2/learner_stub.py`** — `propose_params`: the stub is "best mean arm among the ones that
  held the floor everywhere", with a CLI (`python -m harness.s2.learner_stub --rewards
  rewards.json --out harness/params/learned.json`) that writes a file `PARAMS_PATH` can read
  next run. **What's missing to make this a real cron job**: something that actually runs each
  `s2.arms` arm across worlds and produces the `{arm_name: aggregate_reward}` JSON this CLI
  consumes — `harness_eval/run_matrix.py` sweeps *policy* arms (`tools_only`, `full`, LOO), not
  *params* arms, so wiring S2's arms into a run_matrix-style sweep is the next concrete step, not
  yet built.

Implicit reward signal (per the original note: campaign success implicit, human chat feedback
explicit) — only the implicit half (offtake lift, floor, cost) is modelled. A chat-feedback input
channel into `s2/reward.py` is not designed, let alone built; flagging it as unaddressed rather
than silently out of scope.

## System 3 — design note only (not built)

Persona/brand-specific evolving workflows: agents-as-code via ADAS-style search (Approach C,
`problem-mapped/C-adas-meta-agent-search.md`), vanilla vs. increasingly-specialized variants
(C1/C2/C3), alerts/alarms/highlights/adaptive insights as a separate surface from the bid/budget
levers System 1 touches. The plan's recommendation (`00-problem-map-and-recommendation.md`) keeps
this **offline-only, tuning System 1's prompts/settings against held-out seeds and scenario
variants** — never running model-written code against the live guardrail/market loop, which is
Approach C's main identified risk (it can run code, which could break the observation-only rule).
Nothing in `harness/` depends on System 3 existing; it stays a design note until there's a
concrete reason (a persona-specific workflow need, not just "the plan mentions it") to build it.

## What a real deployment's trigger model would look like

The challenge's weekly cadence means none of this is tested at T/T+5m/T+1h/T+3h granularity. If
System 1 ran at that cadence in production: **T** (event/feedback arrives) would re-run
`diagnose` + the cheap tools (siblings, headroom) immediately; **T+5m** would be too fast for an
LLM leaf round-trip at any real campaign count without batching — L2/L3/L4 would need the
"batched by city" grouping the earlier approach report already specs, not built here since the
challenge's cadence never requires it; **T+1h**/**T+3h** would be where a shock's L2 attribution
and a sibling tie-break's L3 call actually make sense latency-wise. This is scoped as a note for
a real deployment, not a claim that this repo's harness has been tested at that cadence — it
hasn't, and doing so would need a different (non-challenge) simulation harness entirely.
