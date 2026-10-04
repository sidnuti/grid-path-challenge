import harness.policy as hp
from harness.tools import sizing
from gpc.runner import simulate
from gpc.world import build_world
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
orig = sizing.select_raises
state = {"run": 0}
def probe(raises, allowance, params):
    out = orig(raises, allowance, params)
    state["run"] += 1
    if state["run"] in (5, 6) and len(raises):
        print("RUN", state["run"], "allowance", allowance)
        print(raises[["campaign_id","keyword_id","action_type","current_value","new_value","pred_delta_spend","pred_delta_rev","iota"]])
        print("selected idx", list(out.index), "sum", out.pred_delta_spend.sum())
        print("rows/group", raises.groupby(["campaign_id","keyword_id","action_type"]).size().max())
    return out
hp.select_raises = probe
simulate(build_world(23), hp.HTNToolsOnly(), verbose=False)
