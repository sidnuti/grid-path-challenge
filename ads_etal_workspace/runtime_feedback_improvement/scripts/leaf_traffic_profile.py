"""Profile LLM leaf traffic in HTNHarness at L2 with a deterministic mock LLM.
Mock answers are 'permissive' (confirm every surge, explore yes, never veto, multiplier 1.0) to get
an upper bound on call counts; L3 returns an invalid id so the mechanical leader is kept."""
import sys, json, dataclasses, collections
from harness.config import load_params
from harness.policy import HTNHarness, HTNToolsOnly
from harness.llm.client import Usage
from gpc.runner import simulate
from gpc.score import summarize
from gpc.world import build_world

seed = int(sys.argv[1]); explore = sys.argv[2] == "explore"
ANS = {"bid_multiplier": 1.0, "confidence": 0.6, "is_shock": True, "magnitude": 3.0, "direction": "surge",
       "leader_campaign_id": "__none__", "explore": True, "max_spend_inr_day": 500.0, "veto": False}
class CountingLLM:
    def __init__(self): self.run = 0; self.calls = collections.Counter(); self.chars = collections.Counter()
    def complete_json(self, system, user, schema, timeout, leaf="", **kw):
        n = len(system) + len(user) + len(json.dumps(schema)) + 230
        self.calls[(self.run, leaf)] += 1; self.chars[(self.run, leaf)] += n
        out = {k: ANS.get(k, "") for k in schema.get("properties", {})}
        return out, Usage(calls=1)
p = load_params()
p = dataclasses.replace(p, depth="L2", explore_enabled=explore, explore_max_thin_cells=3 if explore else 0,
                        explore_spend_cap_inr_day=500.0 if explore else 0.0)
llm = CountingLLM()
class P(HTNHarness):
    def recommend(self, obs):
        llm.run = obs.run
        a = super().recommend(obs)
        t = self.last_trace
        sh = t.get("shocks")
        nshock = int(((sh.shock_reach) & (sh.direction == "surge")).sum()) if sh is not None and len(sh) else 0
        nconf = int(((sh.shock_reach) & (sh.direction == "surge") & sh.own_action_confound).sum()) if sh is not None and len(sh) else 0
        reasons = a.reason.str.split(":").str[0].value_counts().to_dict() if len(a) else {}
        print(f"run {obs.run}: fallback={'fallback_reason' in t} surge_flags={nshock} (own-confound {nconf}) actions={len(a)} {reasons}", flush=True)
        return a
res = simulate(build_world(seed), P(params=p, llm=llm), verbose=False)
s = summarize(res)
print("SUMMARY", {k: s[k] for k in s if k in ("roas_constraint_met", "direct_roas", "roas_floor", "offtake_vs_baseline_pct")})
tot = collections.Counter(); totc = collections.Counter()
for (r, l), n in sorted(llm.calls.items()):
    print(f"  run {r} {l}: calls={n} prompt_chars={llm.chars[(r,l)]}")
    tot[l] += n; totc[l] += llm.chars[(r, l)]
print("TOTAL", dict(tot), "chars", dict(totc))
