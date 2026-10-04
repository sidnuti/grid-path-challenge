"""Instrument HTNToolsOnly: sizing behaviour, sibling holds, precheck drops, per run."""
import sys
import harness.policy as hp
from harness.tools import sizing
from harness.tools.siblings import contested_markets
from gpc.runner import simulate
from gpc.world import build_world

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
log = []
orig_select = sizing.select_raises

def probe_select(raises, allowance, params):
    out = orig_select(raises, allowance, params)
    rec = {"n_raises": len(raises), "allowance": allowance}
    if len(raises):
        g = raises.groupby(["campaign_id", "keyword_id", "action_type"]).size()
        rec["max_rows_per_group"] = int(g.max())
        rec["sum_dspend_all"] = round(float(raises.pred_delta_spend.sum()), 1)
        rec["n_dspend_gt1"] = int((raises.pred_delta_spend > 1).sum())
        # does mu change the choice at all?
        rec["n_selected"] = len(out)
        rec["selected_dspend"] = round(float(out.pred_delta_spend.sum()), 1) if len(out) else 0.0
        rec["overshoot"] = rec["selected_dspend"] > allowance
    log.append(rec)
    return out

hp.select_raises = probe_select

class P(hp.HTNToolsOnly):
    def recommend(self, obs):
        a = super().recommend(obs)
        t = self.last_trace
        rec = log[-1] if log else {}
        rec["run"] = obs.run
        rec["fallback"] = "fallback_reason" in t
        if not rec["fallback"]:
            mk = t["sibling_markets"]
            cm = contested_markets(mk)
            rec["n_hold"] = len(t["sibling_holds"])
            rec["n_contested"] = len(cm)
            rec["n_wrong_leader"] = int(cm.wrong_leader.sum()) if len(cm) else 0
            # leaders that got a raise in a wrong-leader market
            wl = cm[cm.wrong_leader] if len(cm) else cm
            leaders = set(wl.leader_campaign_id + "|" + wl.keyword_id) if len(wl) else set()
            raised = set(a[a.action_type == "increase_cpm"].campaign_id + "|" + a[a.action_type == "increase_cpm"].keyword_id)
            rec["wrong_leader_markets_where_leader_raised"] = len(leaders & raised)
            rec["precheck_dropped"] = len(t["precheck_dropped"])
            rec["n_actions"] = len(a)
            rec["by_type"] = a.action_type.value_counts().to_dict()
        return a

res = simulate(build_world(seed), P(), verbose=False)
for r in log:
    print(r)
for r in res.runs:
    print(r["run"], "proposed", len(r["proposed"]), "final", len(r["final"]))
