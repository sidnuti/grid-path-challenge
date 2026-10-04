# Next experiments (prioritised) and their limits

Seeds used so far: dev6 (7/11/23/42/101/202), fresh20 (303-322, used for tuning), 1001-1010 (spent), 2001-2010 (spent). Next untouched set: 3001-3010.

| # | Experiment | What it would show | Cost | Limitation |
|---|---|---|---|---|
| E1 | **X7.3 perturbed worlds** (iota +-30%, auction spread, appeal, intent, shock schedules) for L0, no-gate, fixed 3000, no-cuts and **`sm_r1500_c1.0`** | whether H1/H2 hold where values and shocks differ (the eval scenario's situation) | ~195 sims + ~39 for the sm arm | perturbations are self-authored |
| E2 | **Fresh confirmation (3001-3010)** of whatever gate rule is finally chosen, plus at least a few deliberately thin-margin worlds | safety evidence the 2001-2010 set lacked | ~50 sims | thin-margin worlds must be constructed |
| E3 | **X3.1 bid dose-response** | the shape of the marginal response; isolates the 1.7x forecast gap and informs H3/H5 | ~1 h | single-week effects |
| E4 | **Oracle-iota arm** | whether an accurate iota changes decisions at all (value of information) | medium | needs a plug-in iota table |
| E5 | **Frontier sweep**: offtake vs floor margin over the gate parameter space | choose the trade-off on purpose (H4) | ~100 sims | parameters from dev-structure worlds |
| E6 | **X3.2 budget dose-response** | budget-raise value (budget raises are the strongest earner) | low | single-week |
| E7 | **X6 traced narrative** and **X4 leaf plumbing** | readable end-to-end story; confidence in the LLM plumbing | low | one seed; explanatory |
| E8 | **Real-LLM slice (paid, $3 cap)** | real-model validity, variance, sensitivity | paid | hold until triggers/oracle change (02-llm-layer.md) |
| E9 | **Refresh `experiments/RESULTS.md` and the snapshot** after E1/E3 | keeps documents consistent | writing | none |

Order: E1 and E3 are already queued; E2 follows the decision on H1; E4/E5 inform H4/H5; E8 last.
