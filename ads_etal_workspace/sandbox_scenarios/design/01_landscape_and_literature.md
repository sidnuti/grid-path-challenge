# 01 · Landscape: simulators, literature, practitioner evidence, and what each means for our market

> Part of [grid_design_simulator](README.md). Date: 2026-10-05.
> Purpose: before extending `grid-path-challenge/gpc/{world,market}.py`, collect what others built and measured, and turn each finding into a design rule for our simulator (rules are tagged **→ D#** and used in [02](02_simulator_v2_design.md)).

---

## 1. What our simulator already is

`gpc` is a one-brand, five-SKU, five-city, ten-keyword sponsored-search market for quick commerce (Blinkit-like), calibrated to aggregated production data (`grid-path-challenge/CALIBRATION.md`).

| Layer | Today | Where |
|---|---|---|
| Demand | searches/day per city × keyword × daypart, weekend lift, log-normal noise, scheduled shocks | `market.py` step 1 |
| Auction | 4 slots (1/5/9/13); competitor level z ~ LogNormal(0, σ=0.30) per auction; a bid wins a *share* of auctions per slot; own-brand collision pushes the lower bid down a slot | `_slot_shares`, step 2 |
| Response | ad orders ~ Poisson(impr × slot conv × intent × relevance × appeal); OSA gates impressions | steps 3–5 |
| Incrementality | **one fixed number per keyword** ι_k (brand 0.15–0.18, generic 0.50–0.70, competitor 0.85), × 0.6 if the SKU ranks top-3 organically; organic = base − Σ(1−ι)·ad_orders | step 6 |
| Cross-SKU effects | **none** (the EDA's cross-SKU t-stats are spurious by construction, caveat \*15 of the linkage report) | — |
| Time | 28 warm-up days + 6 runs × 7 days; three scheduled shocks (OSA drop, CPM ×1.35, demand ×1.15) | `dev.json` |
| Score | max total offtake s.t. portfolio direct ROAS ≥ 0.98 × warm-up | `score.py` |
| Rules | G0–G8 guardrails, deterministic, run on every policy | `guardrails.py` |

The four scenarios the user wants (category cannibalization, brand↔category association, ephemeral/seasonal categories, macro vs micro goals) all need mechanics the simulator does not have. The rest of this file is the evidence for how to add them.

---

## 2. Comparable simulators and benchmarks

| System | What it simulates | What we borrow | What it lacks for us |
|---|---|---|---|
| **AuctionGym** (Amazon, AdKDD'22 best paper; KDD'23) — [repo](https://github.com/amazon-science/auction-gym), [paper](http://papers.adkdd.org/2022/papers/adkdd22-jeunen-learning.pdf) | Repeated auctions with learned bidders; first/second price; off-policy learning-to-bid | Separating the **auction** from **value estimation**; reproducible offline evaluation with fixed randomness (we already do this with common random numbers) | No organic channel, so no cannibalization; no catalogue |
| **AdCraft** — [arXiv 2306.11971](https://arxiv.org/abs/2306.11971), [repo](https://github.com/Mikata-Project/adcraft) | SEM bid + budget per keyword, **non-stationary** keyword parameters (auction volume, CTR, CVR drift) | Time-varying keyword parameters as a first-class, seeded process (→ **D5**) | No brand/organic structure; single advertiser |
| **AuctionNet** (Alibaba, NeurIPS'24 D&B) — [arXiv 2412.10798](https://arxiv.org/abs/2412.10798), [repo](https://github.com/alimama-tech/AuctionNet) | 48 competing auto-bidders, GSP, budget and CPA constraints, 500M records | **Competitors as agents with their own budgets and constraints**, which is what makes festive CPM inflation endogenous rather than a scheduled ×1.35 (→ **D6**) | Ad-opportunity value only; no organic shelf; no catalogue cannibalization |
| **PlatformBid** — [arXiv 2607.27265](https://arxiv.org/html/2607.27265v1) | Auto-bidding from the platform's side | Platform-level view of constraints | Same gaps |
| **RecSim NG** (Google) — [arXiv 2103.08057](https://arxiv.org/abs/2103.08057), [repo](https://github.com/google-research/recsim_ng) | Users, providers, recommender as a dynamic Bayesian network; **multinomial-logit (MNL) user choice** | The **choice model** as the place where substitution lives; latent user state; probabilistic programs for "hidden truth" (→ **D1, D2**) | Not about auctions or ads economics |
| **Chimera `EcommerceSimulatorV5`** (our sandbox copy, `sandbox/chimera/upstream/src/components.py`) | 52 weeks, price, ad spend, trust with hysteresis, seasonality σ(θ)=1+0.2·sin(2πθ/52) | The **guardian + repair** pattern; a latent slow variable (trust) that punishes myopic policies (→ **D7**) | One SKU, one channel; ads are a log-response scalar. Our replication found the seasonality floor 0.75 never binds and the causal engine is exactly linear in treatment (REPLICATION_REPORT findings 3–4) |
| **Robyn / Meridian** (Meta / Google MMM) — [comparison](https://mbuzz.co/articles/robyn-vs-meridian), [Meridian guide](https://eliya.io/blog/media-mix-modeling/practical-guide-for-meridian-mmm-from-zero-to-hero) | Adstock (carry-over), Hill saturation, trend/seasonality/holiday decomposition, geo-level | The **response-curve vocabulary** and holiday regressors; our `plan.csv` is already an "MMM read" stand-in (→ **D5, D8**) | Aggregate; no auction or keyword |

**Takeaway.** No public simulator combines an auction, an organic shelf, a multi-SKU catalogue and a calendar. The closest pieces are AuctionNet (strategic competitors), AdCraft (non-stationarity) and RecSim NG (choice-based substitution). Our extension is the union of those, anchored on the current `gpc` auction so that existing data, guardrails and EDA keep working.

---

## 3. Literature on incrementality and cannibalization

### 3.1 Brand keywords are mostly not incremental

- **Blake, Nosko & Tadelis (2015), *Econometrica*** — [NBER w20171](https://www.nber.org/system/files/working_papers/w20171/w20171.pdf). eBay switched off brand-keyword ads on Yahoo!/MSN and kept **99.5%** of the clicks through organic links. For non-brand keywords, ads moved new and infrequent users, but frequent users (who would buy anyway) absorbed most of the spend, so average returns were negative.
  - **→ D2:** incrementality is a property of **who is searching** (loyal vs open), not of the keyword label. A keyword's ι must emerge from its intent mix.
  - **→ D3:** within one keyword, ι should fall as spend rises (marginal shoppers are increasingly the ones who would have bought anyway). Our current ι is constant in spend.

### 3.2 Competitors on your brand term: defend or not?

- **Simonov, Nosko & Rao (2018)**, Bing randomized experiment — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2668265), [BSE paper](https://events.bse.eu/live/files/2651-andreysimonov66894pdf):
  - with no competitors, the focal brand's own ad adds **1–4%** clicks (smaller for bigger brands);
  - when the focal brand's ad is present, competitors in positions 2–4 steal **1–5%**;
  - when the focal brand does **not** advertise, competitors steal **18–42%**;
  - removing the focal brand from the top slot raises stealing from 1–2% to **6–15%**;
  - "stolen" clicks convert poorly (46% bounce within 30 s, vs 3.5–6% on the focal link).
  - **→ D4:** brand-keyword ι must be **conditional on competitor presence**. Our dev ι for K01/K02 (0.15–0.18) is the "defend" value; with an aggressive conquester present, pausing the brand term should cost far more. That is a scenario, not a constant.

### 3.3 Attribution overstates; correct it hierarchically

- **"Attributed, But Not Incremental"** (Li et al., June 2026) — [arXiv 2606.26690](https://arxiv.org/abs/2606.26690). Uses sparse lift experiments as causal anchors and allocates the calibrated cannibalization **down a business hierarchy under consistency constraints**; deployment cut measured cannibalization by ~15 pp.
  - **→ D8:** the simulator should expose the **true** decomposition (expansion / stolen-from-competitor / own-organic / sibling-SKU) for scoring, and occasionally a noisy **lift-test readout** to policies, so methods that calibrate to experiments can be tested.
- **CanniUplift** — [arXiv 2607.05242](https://arxiv.org/pdf/2607.05242): seller and incentive cannibalization in uplift models. Same message: SKU-level uplift double-counts what siblings lose.

### 3.4 Substitution inside a category

- **Multinomial / nested logit** is the standard model of within-category substitution — [PyMC Labs explainer](https://www.pymc-labs.com/blog-posts/causal-sales-analytics-discrete-choice-modeling), [counterfactual choice across categories, arXiv 1906.02635](https://arxiv.org/abs/1906.02635), [restricted-logit demand transfer at scale, arXiv 2608.12680](https://arxiv.org/pdf/2608.12680).
  - Plain MNL forces **proportional** substitution (IIA): an ad for S1 takes share from every item in proportion to its share.
  - **Nested** logit lets substitution be stronger inside a nest (bar soap ↔ bar soap) than across nests (bar soap ↔ body wash).
  - **→ D1:** a nested-logit shelf is the cheapest model that produces product↔product cannibalization with a tunable strength, and it yields closed-form **diversion ratios** that we can publish as hidden truth.

### 3.5 Constrained auto-bidding: the optimisation side

- **Balseiro et al. (2024), "A Field Guide for Pacing Budget and ROS Constraints"**, ICML — [PMLR 235](https://proceedings.mlr.press/v235/balseiro24a.html). Budget and return-on-spend constraints are paced with **one Lagrange multiplier per constraint**, updated online; the bid multiplier is a function of the duals.
- **Deng et al. (2023), "Multi-channel Autobidding with Budget and ROI Constraints"**, ICML — [PMLR 202](https://proceedings.mlr.press/v202/deng23c/deng23c.pdf). A **global** ROI and budget across channels behave differently from per-channel ones: per-channel optimisation can be badly sub-optimal.
- **Aggarwal et al., auto-bidding survey** — [SIGecom Exchanges](https://sigecom.org/exchanges/volume_22/1/AGGARWAL.pdf).
  - **→ Goal design ([03](03_goals_macro_micro.md))**: our λ (budget) and μ (dROAS floor) are exactly these duals. Deng et al. is the formal version of "cell-level optimisation misses the global optimum" (report 05 §2), and is why macro goals must be evaluated at portfolio level.

### 3.6 LLMs and hard constraints

- **COMPASS** (2025) — [arXiv 2510.07043](https://arxiv.org/abs/2510.07043). Frontier LLM agents reach **70–90% feasibility but only 20–60% optimality** on constrained optimisation tasks.
- **LLMs as formalizers on CSPs** — [arXiv 2505.13252](https://arxiv.org/pdf/2505.13252). Formalisations miss constraints or add wrong logic.
- **Solver-hard is not model-hard** — [arXiv 2607.17047](https://arxiv.org/pdf/2607.17047).
- **MoHOLLM itself.** In our sandbox copy (`sandbox/mohollm/upstream`), "constraints" means **parameter box bounds** only (`builder.py: parameter_constraints`). Benchmarks with real constraints either **drop them** (Chankong–Haimes, Schaffer N2, Test Function 4: "For this benchmark we drop the constraints") or take BoTorch's **CarSideImpact**, whose 4th objective is the summed violation of its 10 constraints (`g = where(g<0, −g, 0)`, checked in the sandbox's BoTorch install). So the one "constrained" benchmark MoHOLLM ships turns constraints into a soft objective.
  - **→ [04](04_experiment_protocol.md) / [05](05_compiler_and_verifier.md):** the user's hypothesis ("MoHOLLM won't respect constraints; it needs a compiler") is consistent with both the literature and the code. The interesting measurement is *how* it fails: box bounds hold, linear constraints on the decision (budget simplex) hold only by encoding, and **outcome constraints** (realised dROAS floor, stock sell-through) are learned only after violating them.

---

## 4. Practitioner evidence (blogs, trade press, testimonials)

Treat as directional; numbers are self-reported and often marketing-adjacent.

| Claim | Source | Design rule |
|---|---|---|
| Festive premium placements on quick commerce cost **30–40% more** around Diwali; some report 40–50% | [Storyboard18](https://www.storyboard18.com/advertising/festive-rush-pushes-quick-commerce-ad-rates-up-30-40-as-brands-shift-more-digital-spend-108755.htm), [Inc42](https://inc42.com/features/blinkit-zepto-instamart-d2c-ad-strategy-festive-season/) | **D6** festive CPM inflation ×1.3–1.5, endogenous via competitor budgets |
| Advertisers spend **50–60% of the annual budget in a 2–3 month window**; CPC moves from ₹60 to ₹240; "brands paying 4× more for the same pool of customers" | [Storyboard18](https://www.storyboard18.com/how-it-works/quick-commerce-ad-costs-soar-this-festive-season-ws-l-110678.htm) | **D6** festive demand rises less than competition does: attention does not scale with spend |
| Quick-commerce conversion 3–8% vs 1.5–3% on Meta/Google; "someone opening Blinkit at 7 pm before a Diwali gathering is buying" | [Inc42](https://inc42.com/features/blinkit-zepto-instamart-d2c-ad-strategy-festive-season/) | **D5** festive evening daypart intent lift |
| Ads only serve where the SKU is stocked in the nearest dark store; ads into stock-outs waste money | [42signals](https://www.42signals.com/blog/visibility-on-quick-commerce-platforms/), [MetricsCart](https://metricscart.com/insights/advertising-on-quick-commerce-platforms/) | Already modelled (OSA gates impressions, G4). Extend: **finite festive stock** that ads deplete (**D7**) |
| "The 6× ROAS on your Blinkit dashboard": platform ROAS intercepts shoppers already in the app, often already yours; rising share at flat GMV means cannibalizing your baseline | [Meerkats.ai](https://www.meerkats.ai/blog/quick-commerce-roas-truth/) | **D2/D8** score on brand-level incremental, not attributed |
| Amazon "flywheel": sponsored sales feed organic rank; caveat — if 90% of sales vanish when ads stop, there is no flywheel | [SellerApp](https://www.sellerapp.com/blog/amazon-advertising-impact-on-organic-ranking/), [LandingCube](https://landingcube.com/amazon-ppc-impact-on-organic-search-rankings/) | **D9** optional halo: ad-driven velocity lifts organic rank with a lag. Off by default; a scenario tests whether a method can *detect* it |
| Amul holds roughly 80–90% of Indian butter (figures vary by year and source) | [Forbes India](https://www.forbesindia.com/article/work-in-progress/amuls-going-utterly-butterly-digital/55855/1), [Osum](https://blog.osum.com/amul-butter-market-share/) | **D2** "butter ≈ Amul": a generic query whose intent mass is mostly one brand's loyalists. Ads by that brand on it behave like brand-keyword ads |
| 70% of advertisers struggle to measure retail-media incrementality | [via Eva Guru summary](https://eva.guru/blog/amazon-ad-incrementality-measurement/) | Motivates exposing lift-test readouts (**D8**) |

---

## 5. Design rules collected

| Rule | Statement | Scenario it serves |
|---|---|---|
| **D1** | Replace "organic = base − Σ(1−ι)·ad" with a **nested-logit shelf** per query: items = own SKUs + competitor SKUs; nests = sub-categories; ads change an item's visibility | Category cannibalization |
| **D2** | Each query carries a latent **intent mix** π_q over {loyal-to-brand-b, open}. ι emerges from it; keyword labels (brand/generic/competitor) become *public metadata that can be wrong* | Brand↔category association; replaces fixed ι |
| **D3** | ι falls with spend inside a cell (deeper auctions reach more loyal shoppers) | Marginal vs average (caveat \*5) |
| **D4** | Competitor stealing on a brand query depends on whether the focal brand is present (Simonov et al. calibration) | Brand defence; pause traps |
| **D5** | A **calendar** of seasonal curves, festive windows, ephemeral keywords and SKUs, with pull-forward | Ephemeral / seasonal / festive |
| **D6** | **Competitor agents** with budgets that surge in festive windows ⇒ CPM inflation emerges | Festive CPM |
| **D7** | **Finite stock** for limited SKUs; ads deplete it; stock-out ends delivery | Festive gift packs; a hard constraint the compiler must project |
| **D8** | Scorer computes **true brand-level incremental revenue** by counterfactual (same seed, ads off), and the true 4-way decomposition; policies can request noisy lift readouts at a cost | iROAS objective |
| **D9** | Optional organic halo with lag (off by default) | Tests whether methods detect a mechanism that is absent vs present |

\* Practitioner numbers in §4 are self-reported, vary by source and year, and are used only to set plausible ranges, never as calibration targets.
