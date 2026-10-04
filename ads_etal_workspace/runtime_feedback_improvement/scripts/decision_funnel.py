"""Per-run decision funnel for HTNToolsOnly (L0) on one seed."""
import sys
from harness.policy import HTNToolsOnly
from gpc.runner import simulate
from gpc.score import summarize
from gpc.world import build_world
seed = int(sys.argv[1])
rows = []
class P(HTNToolsOnly):
    def recommend(self, obs):
        a = super().recommend(obs); t = self.last_trace; d = t["diagnostics"]
        b = d.bids
        rc = t["candidates_raised"]; cc = t["candidates_cut"]
        rows.append(dict(run=obs.run, day=obs.day,
            cells=len(b), CLEARS=int((b.verdict=="CLEARS").sum()), MISSES=int((b.verdict=="MISSES").sum()), THIN=int((b.verdict=="THIN").sum()),
            tierA=int((b.tier=="A").sum()), tierB=int((b.tier=="B").sum()), tierC=int((b.tier=="C").sum()),
            held=len(t["sibling_holds"]),
            reprice=int((rc.action_type=="increase_cpm").sum()) if len(rc) else 0,
            budget=int((rc.action_type=="increase_budget").sum()) if len(rc) else 0,
            raise_dspend=round(float(rc.pred_delta_spend.sum()),0) if len(rc) else 0,
            allowance=t["headroom"].allowance_inr_day, headroom=t["headroom"].headroom_inr_day,
            droas_to_date=t["headroom"].droas_to_date, floor_m=t["headroom"].roas_floor,
            comp_cuts=int(cc.reason.str.startswith("M_CompetitorCut").sum()) if len(cc) else 0,
            base_cuts=int(cc.reason.str.startswith("M_Base").sum()) if len(cc) else 0,
            precheck_dropped=len(t["precheck_dropped"]),
            drop_reasons=t["precheck_dropped"].precheck_reason.str[:2].value_counts().to_dict() if len(t["precheck_dropped"]) else {},
            emitted=len(a)))
        return a
res = simulate(build_world(seed), P(), verbose=False)
for r, run in zip(rows, res.runs):
    r["shipped"] = len(run["final"])
    log = run.get("guardrail_log") if isinstance(run, dict) else None
    print(r)
print("KEYS", list(res.runs[0].keys()))
s = summarize(res); print("SUMMARY", {k: s[k] for k in ("offtake_inr_per_day","warmup_offtake_inr_per_day","ad_spend_inr_per_day","direct_roas","roas_floor","roas_constraint_met","actions_shipped","actions_proposed") if k in s})
print("SUMKEYS", list(s.keys()))
