# 02 · Simulator v2: a market with a shelf, brands, a calendar and competitors

> Part of [grid_design_simulator](README.md). Builds on `grid-path-challenge/gpc/{world,market}.py` and the design rules D1–D9 in [01](01_landscape_and_literature.md).
> Principle: **every new mechanism is behind a scenario flag, and with all flags off the simulator reproduces today's `dev` outputs byte for byte.** Existing data, guardrails, EDA and linkage work keep their meaning.

---

## 0. TL;DR

| Scenario the user asked for | New mechanism | What it makes true that is false today |
|---|---|---|
| Category-specific cannibalization | **Nested-logit shelf** per query (own + competitor SKUs, nests = sub-categories) | An S1 ad on "soap" takes orders from S3 and S5, not only from S1's own organic. SKU-level ι over-states brand-level ι by the sibling share |
| Brand ↔ product association ("butter ≈ Amul") | **Intent mix** π_q per query and city: loyal-to-brand-b vs open; **query reformulation** | A "generic" keyword can behave like a brand keyword (low ι) for the brand that owns it, and like a conquest keyword for challengers. The keyword-type label becomes a trap |
| Ephemeral / seasonal / festive | **Calendar**: seasonal curves, festive windows, ephemeral keywords and SKUs, finite stock, pull-forward; **competitor agents** whose festive budgets inflate CPMs | Some cells exist for 3 weeks with no history; a festive week borrows demand from the weeks after it; stock runs out |
| Macro vs micro goals (see [03](03_goals_macro_micro.md)) | **Scorer v2**: true brand-level incremental revenue by counterfactual, a 4-way decomposition, and per-goal pass/fail | iROAS can be scored on truth, at any level of the hierarchy, without the policy ever seeing truth |

---

## 1. Today's response model, and the one line we replace

Today, per SKU × city × day (`market.py` step 6):

$$\text{organic}_{s,c} = \text{base}_{s,c} - \sum_{k} (1-\iota_{s,k})\cdot \text{ad\_orders}_{s,c,k},\qquad \iota_{s,k} = \iota_k\cdot(0.6 \text{ if organic rank}\le 3)$$

Consequences we want to remove:
1. An ad can only cannibalize **its own SKU's** organic sales. There are no siblings and no competitors on the shelf.
2. ι is a constant per keyword: it does not depend on who is searching, whether a competitor is present, or how much we spend.
3. No ad can ever grow the category or take a sale from a competitor. "Incremental" just means "not subtracted".

v2 replaces that line with a **choice model on the search-result page**. Everything upstream (searches, auction, slot shares, OSA, budgets) is unchanged.

---

## 2. Module A — the shelf: nested logit per query (D1)

### 2.1 Items and nests

The shelf for query q in city c, daypart d, day t lists items i with a **position weight** w_i:

- own SKUs (S1–S5, later S6) and **competitor SKUs** (new, not controllable): V1 Velora Soap, V2 Velora Body Wash, N1 Nimbus Soap, N2 Nimbus Body Wash;
- each item may appear **organically** (rank r ⇒ weight w_org(r) from the industry view curve) and/or in an **ad slot** s won in this auction (weight w_ad(s) = SLOT_VIEW_REL[s]);
- nests n = sub-category: *bar* {S1, S3, S5, V1, N1}, *liquid* {S2, S4, V2, N2}; nest 0 = **no purchase** (outside option).

### 2.2 Choice probabilities (open shoppers)

Utility of item i: $V_i = a_i + \beta \log(w_{org,i} + w_{ad,i}) + \gamma_{q,i}$, where a_i is appeal (hidden) and γ_{q,i} is query-item fit (from `keyword_sku.relevance`).

$$P(i\mid n) = \frac{e^{V_i/\lambda_n}}{\sum_{j\in n} e^{V_j/\lambda_n}},\quad I_n = \lambda_n \log\sum_{j\in n} e^{V_j/\lambda_n},\quad P(n) = \frac{e^{I_n}}{e^{V_0} + \sum_m e^{I_m}}$$

- λ_n ∈ (0, 1] is the **nest dissimilarity**. Small λ_bar (e.g. 0.35) ⇒ bar soaps substitute strongly for each other: the "category-specific cannibalization" knob. λ = 1 collapses to plain MNL.
- V_0 sets the **category conversion**: an ad that raises some V_i lifts I_n and pulls shoppers from the outside option, i.e. **category expansion**.
- An order is **ad-attributed** with probability w_ad,i / (w_ad,i + w_org,i) given that i was chosen (the platform credits the click path). This reproduces "ad orders that would have happened anyway" without a fixed ι.

### 2.3 Diversion ratios: the published hidden truth

For a small visibility change on item i, the share it takes from j is the diversion ratio

$$D_{j\to i} = -\frac{\partial P_j/\partial V_i}{\partial P_i/\partial V_i}$$

Nested logit gives it in closed form. With $Q_i = \tfrac{1}{\lambda_n}(1-P(i|n)) + P(i|n)(1-P(n))$ (so that $\partial \log P_i/\partial V_i = Q_i$):

$$D_{j\to i} = \begin{cases}\dfrac{P(j|n)\,\big(1/\lambda_n - 1 + P(n)\big)}{Q_i} & j \text{ in the same nest } n\\[2ex] \dfrac{P_j}{Q_i} & j \text{ in another nest, or } j = \text{no purchase}\end{cases}$$

The term 1/λ_n − 1 is what makes siblings lose more than items elsewhere; at λ_n = 1 both cases reduce to P_j/Q_i (plain MNL, proportional substitution). The simulator writes D for every (i, j, q, c) into `truth["diversion"]` so the linkage EDA can be scored against it (today the EDA had nothing to recover: caveat \*15).

### 2.4 The 4-way decomposition of every ad order

For each ad-attributed order of own SKU i the scorer (never the policy) splits the expected effect of the ad into

| Part | Meaning | Brand-incremental? |
|---|---|---|
| **self** | would have bought i organically | no |
| **sibling** | would have bought another own SKU (S3 instead of S1) | **no** |
| **competitor** | would have bought V1/N1/… | yes (stolen) |
| **expansion** | would not have bought in the category | yes |

$$\iota^{\text{SKU}}_i = \text{competitor}+\text{expansion}+\text{sibling},\qquad \iota^{\text{brand}}_i = \text{competitor}+\text{expansion}$$

**Today's estimator** (organic of SKU *s* on its own ad orders, report 06) measures ι^SKU. **The gap ι^SKU − ι^brand = sibling share is exactly the category-specific cannibalization the user wants captured**, and it is invisible to any per-SKU regression. It shows up only in a cross-SKU regression (S3 organic on S1 ad orders) or in brand totals.

Computation: the expectation is exact per auction (remove the ad, recompute the four probabilities), so the decomposition costs one extra softmax per (q, c, d, t). Joint removal of several ads is non-additive; the scorer reports leave-one-out per cell plus the true all-ads-off counterfactual (§7).

### 2.5 Default parameters (scenario `sc1_cannibal`)

| Parameter | Value | Why |
|---|---|---|
| λ_bar, λ_liquid | 0.35, 0.60 | Bar soaps are near-interchangeable; liquids less so (fragrance, format) |
| β (position sensitivity) | 1.0 | Choice ∝ visibility at fixed appeal; reproduces slot conv ratios |
| V_0 | tuned so warm-up category conversion ≈ today's | Keeps calibration |
| Competitor appeal | V1 1.05, N1 0.9, V2 0.95, N2 1.1 | Velora strong in bar, Nimbus in liquid |

Calibration target: with `sc1_cannibal`, warm-up direct ROAS by keyword type and ad share of units stay within CALIBRATION.md ranges (generic 2.5–7.0×, competitor 0.8–1.9×, brand 16–19×, ads ≈ 20% of units, run-out ≈ 30% of campaign-days). A calibration test fails the build otherwise.

---

## 3. Module B — intent mix and brand association (D2, D4)

### 3.1 Who is searching

Each query q in city c has an intent mix over segments:

$$\pi_{q,c} = (\pi^{\text{Aurel}}, \pi^{\text{Velora}}, \pi^{\text{Nimbus}}, \pi^{\text{open}}),\quad \sum = 1$$

- **Loyal-to-b** shoppers choose among b's items with the within-brand logit; they buy elsewhere only if b is out of stock or not visible, or if **stolen** by a competitor ad.
- **Open** shoppers use the nested logit of §2.

So ι emerges: an Aurel ad shown to an Aurel-loyal searcher is never brand-incremental (at most it moves them between Aurel SKUs: sibling); to an open searcher it can expand or steal; to a Velora-loyal searcher it can steal only through the stealing channel below.

### 3.2 Stealing depends on presence (Simonov et al.)

A competitor ad in a slot above the loyal brand's best position steals a loyal shopper with probability

$$\sigma_{\text{steal}} = \begin{cases} \sigma_{\text{def}} \approx 0.01\text{–}0.05 & \text{the brand also has an ad at or above that slot}\\ \sigma_{\text{undef}} \approx 0.18\text{–}0.42 & \text{the brand is absent from paid slots}\end{cases}$$

and stolen shoppers convert at ≈ 0.3× (the 46% fast-bounce finding). This turns "pause the brand keyword" from a free saving (today, ι ≈ 0.15) into a **conditional** decision: cheap when no one conquests, expensive when someone does. It is the first place where a competitor's behaviour (Module D) changes the value of our own lever.

### 3.3 "Butter ≈ Amul": queries owned by a brand

Brand–category association is a large π^b on a generic query. Default table for `sc2_brand_assoc` (city-average; per-city values vary, see §3.5):

| Query | Public label | π^Aurel | π^Velora | π^Nimbus | π^open | Emergent behaviour for **Aurel** ads |
|---|---|---|---|---|---|---|
| K01 aurel | brand | 0.85 | — | — | 0.15 | brand-like: ι^brand ≈ 0.1–0.2 (defend only if conquested) |
| K02 aurel soap | brand | 0.90 | — | — | 0.10 | brand-like |
| K03 soap | generic | 0.10 | 0.25 | 0.05 | 0.60 | true generic: mix of expansion and stealing, **and** sibling cannibalization among S1/S3/S5 |
| K05 body wash | generic | 0.05 | 0.05 | **0.45** | 0.45 | **challenger**: Nimbus "owns" body wash. High ι, low conversion |
| K07 sandal soap | generic | **0.60** | 0.05 | — | 0.35 | **owned by Aurel**: behaves like a brand keyword although labelled generic. The "butter ≈ Amul" case from Aurel's side |
| K09 velora | competition | — | 0.85 | — | 0.15 | conquest: steal-only, poor conversion |
| K10 nimbus body wash | competition | — | — | 0.90 | 0.10 | conquest |

The **trap**: today's `_BID_MULT` and the plan's `goal_droas` key off `keyword_type`. In v2, K07's label says "generic, goal 3.2×", but its direct ROAS looks brand-like (high) and its brand-incremental ROAS is low. A policy that trusts labels over-bids K07; a policy that learns "K07 ≈ Aurel" from data (organic share of Aurel on K07, flat organic when ads pause) does not.

### 3.4 Keyword ↔ keyword: reformulation

A loyal-b shopper on a generic query who does not see b in the top positions **reformulates** to b's brand query with probability ρ_reform (default 0.4), otherwise buys from the open shelf or leaves. Effects:
- pausing Aurel on K03 "soap" raises searches on K01 "aurel" the same day;
- K01's ad orders rise and its attributed ROAS **improves** while brand totals fall: a classic attribution illusion;
- the linkage graph gets a new edge type, *keyword → keyword (reformulation)*, recoverable from the day-level correlation of K03 Aurel visibility with K01 volume.

### 3.5 Geography of brand strength

π varies by city (log-normal around the table with a city tilt): Aurel stronger in the South (BLR, HYD), Velora in the North (DEL), like Amul's regional strength (Gujarat > rest). This creates *brand × geo* linkages and makes regional macro goals ("grow North") genuinely harder than "grow South".

---

## 4. Module C — calendar: seasonal, festive, ephemeral (D5, D7)

### 4.1 Event calendar

```json
"calendar": {
  "seasonal": [
    {"keywords": ["K12"], "shape": "sin", "period_days": 365, "peak_day": 40, "amp": 0.30}
  ],
  "events": [
    {"id": "FEST", "peak_day": 56, "ramp_days": 14, "tail_days": 3,
     "demand": {"K11": 6.0, "K03": 1.15, "K01": 1.10}, "evening_intent_lift": 1.25,
     "competitor_budget_mult": 2.5,
     "pull_forward": {"keywords": ["K03", "K04", "K07"], "rho": 0.5, "days_after": 14}}
  ],
  "ephemeral_keywords": [{"id": "K11", "keyword": "bath gift set", "live_from": 42, "live_to": 59}],
  "ephemeral_skus": [{"id": "S6", "name": "Aurel Festive Gift Pack", "nest": "bar", "asp": 549,
                       "stock_by_city": {"DEL": 2400, "MUM": 1800, "BLR": 1600, "HYD": 900, "PUN": 600},
                       "live_from": 42, "live_to": 59, "salvage_frac": 0.4}]
}
```

(Days are simulator day indices. With `START_DATE` moved to 2026-09-14, day 56 ≈ 9 Nov, near Diwali 2026\*.)

### 4.2 Mechanics

- **Festive demand curve** for keyword k: $m_k(t) = 1 + (A_k - 1)\cdot\exp\!\big(-\tfrac{(t - t^*)^2}{2w^2}\big)$ for t ≤ t* + tail, using the ramp width w; ephemeral keywords have m = 0 outside their live window.
- **Evening intent lift** in the window (the "7 pm before a gathering" effect): purchase utility +log(1.25) in the evening daypart.
- **Pull-forward** (temporal cannibalization): excess purchases E = Σ_t (m_k(t) − 1)·base during the window reduce base demand over the next `days_after` days by ρ·E, spread evenly. Total category units over the window plus tail rise by only (1 − ρ)·E. A policy that scores itself on the festive week alone over-states its lift; one that keeps spending into the post-festive dip buys depressed demand.
- **Finite stock** for S6: each unit sold (ad or organic) depletes city stock; at zero, OSA → 0 and its ads stop serving (existing OSA gating). Unsold stock at `live_to` is salvaged at 40% of ASP: a real cost of under-promotion.
- **Cold start**: K11 and S6 have **no warm-up history**. `keyword_sku` lists S6's relevance to K11, K01, K03 and S1/S3's relevance to K11 (public). The only way to price these cells is to transfer from analogues in the linkage graph (K11 ↔ K03 through shared SKUs; S6 ↔ S1 through the nest). This tests graph reasoning (deck: retrieve → compose → verify) directly.
- **Seasonal** keyword K12 "antibacterial soap" (monsoon, ±30%) co-moves with nothing we control. If a policy raises bids on K12 just as its season rises, a naive before/after reads the season as ad lift. The day fixed effects in our ι estimator absorb *common* seasonality but not *keyword-specific* seasonality; v2 makes that difference matter (requires keyword × week effects).

---

## 5. Module D — competitor agents (D6)

Replace the fixed median of the competitor level z with a small set of competitor agents (Velora, Nimbus, plus a long-tail "rest") that pace a daily budget:

$$\text{bidmult}_{c}(t+1) = \text{bidmult}_c(t)\cdot\exp\!\Big(\eta\cdot\frac{B_c(t) - \text{spend}_c(t)}{B_c(t)}\Big),\qquad B_c(t) = B_c^0\cdot \text{competitor\_budget\_mult}(t)$$

- Per-auction spread stays log-normal (σ = 0.30) around the agents' bid level, so `_slot_shares` keeps its closed form.
- During the festive window B_c × 2.5 ⇒ clearing CPMs rise by an **emergent** ≈ 1.3–1.5× (calibrate η so it lands in the trade-press range of 30–50%), while searches rise less: attention does not scale with spend.
- **Opportunism**: a competitor raises its bid on Aurel's brand query when Aurel's slot-1 share there drops below 50% for 3 days (stealing is cheap when the brand is absent, §3.2). This makes "pause brand terms" a dynamic, not static, decision.
- The legacy `price` shock (MUM ×1.35 on K05/K06) becomes one competitor's budget step in the legacy-compatible scenario.

---

## 6. Module E — optional organic halo (D9, off by default)

Organic rank r_{i,q} updates weekly: if i's 7-day orders on q exceed the item above it by more than h (default 20%), i moves up one position; the reverse moves it down. Ads drive orders, so ads can move organic rank with a lag. Default **off**, because the current calibration and finding \*8 ("organic +20% is infeasible through ads") assume no halo. Scenario `sc5_halo` turns it on to test whether methods **detect** a mechanism when present and do **not** hallucinate it when absent.

---

## 7. Module F — Scorer v2 and observations

### 7.1 Truth-side scoring (policy never sees it)

With common random numbers, the scorer runs the horizon twice: under the policy and under **"all Aurel ads off from the end of warm-up"**. Then

$$\text{IncRev}^{\text{brand}} = \sum_{t,s,c} \text{offtake}^{\text{policy}}_{t,s,c} - \text{offtake}^{\text{ads-off}}_{t,s,c},\qquad \text{iROAS} = \frac{\text{IncRev}^{\text{brand}}}{\text{Spend}}$$

plus the §2.4 decomposition per cell, per SKU, per nest, per event phase, and a **per-goal pass/fail** table for whatever GoalSpec is active ([03](03_goals_macro_micro.md)). The legacy score (offtake s.t. floor) is still reported, so old and new results stay comparable.

### 7.2 New observations (public)

| Table | Content | Why realistic |
|---|---|---|
| `shelf_daily` | per query × city: organic rank of every listed item (own and competitor), daily | Search results are public; brands scrape them |
| `category_share_weekly` | per nest × city: own-brand share of category units, ±3 pp noise, **7-day lag** | Platforms and panels sell category insights with a lag |
| `calendar_public` | event dates, ephemeral keyword/SKU live windows, S6 stock by city | Brands know their own festive plans and stock |
| `lift_readout` (on request) | result of a **holdout action**: one cell paused in one city for one run ⇒ noisy brand-incremental estimate with a CI | Lift tests exist and cost money; [01 §3.3](01_landscape_and_literature.md) |

A seventh lever, `request_holdout(cell, city)`, is added to `ACTION_TYPES`; it is a measurement action with a real cost (lost sales in that cell) and goes through the guardrails like any other.

---

## 8. Scenario files

| File | Flags on | Main trap | What a good policy does |
|---|---|---|---|
| `dev.json` (unchanged) | none | — | — (backward compatibility, byte-identical outputs) |
| `sc1_cannibal.json` | A | raising S1 and S3 together on K03/K04 trades share between them; SKU-level ι says both are fine | raise the one with higher brand-level marginal value per market, hold the other |
| `sc2_brand_assoc.json` | A, B, D(opportunism) | K07 labelled generic but Aurel-owned; pausing K03 lifts K01 attributed ROAS; pausing K01 invites conquest | treat K07 like a brand term; judge K03 on brand totals; defend K01 only where conquested |
| `sc3_festive.json` | A, C, D | cold-start K11/S6; CPM ×1.4; pull-forward; stock-out | pre-load spend on S6/K11 within stock; stop before stock-out; cut core generics in the post-festive dip |
| `sc4_seasonal.json` | A, C(seasonal) | K12's season masquerades as ad lift | estimate with keyword × week effects or a holdout |
| `sc5_halo.json` | A, E | halo present: ads move organic rank | detect and value the lagged organic gain |
| `sc_all.json` | A–D | all of the above at once | — (the integration test for E1–E3 in [04](04_experiment_protocol.md)) |
| `eval_*.json` (private) | same families, different values | — | — |

Each scenario's truth is drawn from priors with the seed (as today), so the same scenario family produces many worlds; hidden values never ship to policies.

---

## 9. Effect on the hypercube and linkage work

- **Hypercube axes** gain **time phase** T ∈ {normal, ramp, peak, tail, post} and the **owner of the query** as a keyword-node attribute: H = S × C × K × D × T × Λ. New nodes: S6, K11, K12, competitor items (read-only).
- **New edge types** for the linkage graph, each with a ground-truth table to score recovery:

| Edge | Truth field | How a method can estimate it |
|---|---|---|
| SKU → SKU diversion | `truth.diversion` | cross-SKU regression of sibling organic on own ad orders (now non-spurious), category share |
| keyword → brand ownership π | `truth.intent_mix` | own organic share on the query; organic response to pauses |
| keyword → keyword reformulation | `truth.reformulation` | day-level co-movement of brand-query volume with own visibility on the generic |
| event → keyword demand | `truth.calendar` | public calendar + observed volume |
| competitor → keyword pressure | `truth.competitors` | CPM level by keyword over time |

- The four trust levels from the linkage report (declared / measured / mechanism-backed / confounded / spurious) stay; v2 adds truth for all of them so "confounded" and "spurious" can be graded, not just argued.

---

## 10. Implementation plan ($0, no LLM calls)

| Step | Files | Test that gates it |
|---|---|---|
| 1 | `gpc/shelf.py` (nested logit, decomposition), flag `shelf_model: legacy\|nested_logit` | legacy path byte-identical on `dev`; MNL limit (λ=1) matches IIA; diversion rows sum to ≤ 1 |
| 2 | `gpc/intent.py` (π, stealing, reformulation) | calibration ranges in CALIBRATION.md hold for `sc2` warm-up |
| 3 | `gpc/calendar.py`, `gpc/stock.py` | pull-forward conserves units: Σ excess·ρ = Σ dip; stock never negative; S6 OSA 0 after stock-out |
| 4 | `gpc/competitors.py` | festive CPM ratio in [1.3, 1.5] on `sc3`; legacy shock reproduced |
| 5 | `gpc/score_v2.py` (counterfactual, decomposition, goal table) | IncRev = 0 for `no_op`; decomposition sums to attributed orders; CRN: same seed ⇒ same counterfactual |
| 6 | `observation.py` additions, `request_holdout` lever + guardrail rules | G0 schema accepts it; holdout readout CI covers truth ≥ 90% over 50 seeds |
| 7 | scenario JSONs, `make scenarios` | all scenarios run in < 30 s per 70-day world |

---

## Assumptions and caveats

| # | Assumption |
|---|---|
| \*1 | Nested logit is a modelling choice, not a fact about Blinkit shoppers. It is the simplest model with tunable within-nest substitution; real substitution may be asymmetric (premium → value but not back), which needs a richer model. |
| \*2 | The intent-mix values (e.g. π^Nimbus = 0.45 on "body wash") are illustrative. They are chosen to produce the traps, not estimated from data. |
| \*3 | Simonov et al. measured clicks on Bing web search; transferring the steal rates to quick-commerce product search is an assumption. |
| \*4 | Diwali 2026 falls in early-to-mid November; the exact date and the START_DATE shift should be confirmed before fixing `peak_day`. Days in the scenario are indices, so the mechanics do not depend on the real date. |
| \*5 | The pull-forward coefficient ρ = 0.5 is a guess; stockpiling of soap around festivals is plausible but unmeasured here. |
| \*6 | Counterfactual scoring with "all ads off" defines incrementality relative to *no advertising*, not relative to the warm-up policy. Both baselines are reasonable; we report the first and can add the second. |
| \*7 | Backward compatibility is a test target, not yet verified: floating-point order changes in shared code paths could break byte identity and would need a tolerance. |
