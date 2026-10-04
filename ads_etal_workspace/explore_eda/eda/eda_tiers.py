"""Top vs bottom SKUs and SKU x city cells, for decision making. Prints tables; saves tiers.csv."""
import pandas as pd, numpy as np
from pathlib import Path
R = Path(__file__).resolve().parents[1]; D = R / "grid-path-challenge/data"
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 40)
kw = pd.read_csv(D/"base/keywords.csv"); prod = pd.read_csv(D/"base/products.csv"); ks = pd.read_csv(D/"base/keyword_sku.csv")
f = pd.read_csv(D/"observed/daily_facts.csv").merge(kw[["keyword_id", "keyword_type"]], on="keyword_id")
sc = pd.read_csv(D/"observed/sku_city_daily.csv"); cd = pd.read_csv(D/"observed/campaign_daily.csv")
W = 28
f["sc"] = f.sku_id + "-" + f.city_id; sc["sc"] = sc.sku_id + "-" + sc.city_id

# displacement per SKU x keyword type (organic units lost per ad order), sku x city + day FE, all 70 days
d = f.groupby(["day", "sku_id", "city_id", "keyword_type"]).ad_orders.sum().unstack(fill_value=0).reset_index()
d = d.merge(sc[["day", "sku_id", "city_id", "organic_units"]], on=["day", "sku_id", "city_id"]); d["scid"] = d.sku_id + d.city_id
disp = {}
for s, g in d.groupby("sku_id"):
    X = pd.get_dummies(g[["scid", "day"]].astype(str)).astype(float).join(g[["brand", "generic", "competition"]].astype(float))
    b, *_ = np.linalg.lstsq(X.values, g.organic_units.values, rcond=None)
    disp[s] = {t: float(np.clip(-v, 0, 1)) for t, v in zip(X.columns, b) if t in ("brand", "generic", "competition")}
print("displacement (clipped 0..1):", {s: {k: round(v, 2) for k, v in x.items()} for s, x in disp.items()})

w = f[f.day < W].merge(prod[["sku_id", "asp_inr", "sub_category"]], on="sku_id")
w["incr_orders"] = w.apply(lambda r: r.ad_orders * (1 - disp[r.sku_id][r.keyword_type]), axis=1)
w["incr_rev"] = w.incr_orders * w.asp_inr

def table(keys):
    a = w.groupby(keys).agg(spend=("spend_inr", "sum"), rev=("ad_revenue_inr", "sum"), incr=("incr_rev", "sum"))
    a["droas"] = a.rev / a.spend; a["iroas"] = a.incr / a.spend; a[["spend", "rev", "incr"]] /= W
    return a

# ---------- SKU level ----------
sk = table(["sku_id"])
sw = sc[sc.day < W].groupby("sku_id").agg(offtake=("offtake_inr", "sum"), org=("organic_units", "sum"), adu=("ad_units", "sum"), tot=("total_units", "sum"))
sw["offtake"] /= W; sw["ad_share"] = sw.adu / sw.tot; sw["org_day"] = sw.org / W
sk = sk.join(sw[["offtake", "ad_share", "org_day"]]).join(prod.set_index("sku_id")[["sub_category", "asp_inr", "launch_age_days"]])
sk["offtake_share"] = sk.offtake / sk.offtake.sum(); sk["spend_share"] = sk.spend / sk.spend.sum()
sk["invest_ratio"] = sk.spend_share / sk.offtake_share
gen = ks.merge(kw, on="keyword_id"); gen = gen[gen.keyword_type == "generic"]
sk["generic_org_rank"] = gen.groupby("sku_id").organic_rank.mean()
# organic trend: eval weeks 4-9 vs warm-up (baseline-shaped)
o = sc.assign(ph=np.where(sc.day < W, "w", "e")).groupby(["sku_id", "ph"]).organic_units.mean().unstack()
sk["organic_trend_pct"] = (o.e / o.w - 1) * 100
# demand trend of the SKU's keywords: slot-1-equivalent reach, eval vs warm-up
view = pd.read_csv(D/"base/industry_rank_curve.csv").set_index("slot").view_rel
f["reach"] = f.impressions / f.slot.map(view)
rr = f.assign(ph=np.where(f.day < W, "w", "e")).groupby(["sku_id", "ph"]).reach.sum().unstack()
sk["reach_trend_pct"] = ((rr.e / 42) / (rr.w / W) - 1) * 100   # per-day reach, eval vs warm-up
ro = cd[cd.day < W].assign(sku_id=lambda x: x.campaign_id.str[2:4]).groupby("sku_id").ran_out.mean()
sk["runout_rate"] = ro
print("\n## SKU tiers (warm-up per day)")
print(sk[["sub_category", "asp_inr", "launch_age_days", "offtake", "offtake_share", "spend_share", "invest_ratio", "ad_share", "droas", "iroas",
          "generic_org_rank", "runout_rate", "organic_trend_pct", "reach_trend_pct"]].round(2).sort_values("offtake", ascending=False).to_string())

print("\n## SKU x keyword type: direct vs incremental ROAS")
t = table(["sku_id", "keyword_type"]); print(t[["spend", "droas", "iroas"]].unstack().round(2).to_string())
print("\n## Sub-category x keyword type: incremental ROAS")
print(table(["sub_category", "keyword_type"]).iroas.unstack().round(2))

# ---------- SKU x city ----------
cc = table(["sc"])
cw = sc[sc.day < W].groupby("sc").agg(offtake=("offtake_inr", "sum"), adu=("ad_units", "sum"), tot=("total_units", "sum"), osa=("osa", "mean"))
cw["offtake"] /= W; cw["ad_share"] = cw.adu / cw.tot
cc = cc.join(cw[["offtake", "ad_share", "osa"]])
cro = cd[cd.day < W].assign(sc=lambda x: x.campaign_id.str[2:4] + "-" + x.campaign_id.str[5:]).groupby("sc").agg(runout=("ran_out", "mean"), util=("spend_inr", "sum"), bud=("daily_budget_inr", "sum"))
cc["runout"] = cro.runout; cc["util"] = cro.util / cro.bud
cc["offtake_share"] = cc.offtake / cc.offtake.sum(); cc["spend_share"] = cc.spend / cc.spend.sum()
cc = cc.sort_values("offtake", ascending=False)
cc["cum_offtake_share"] = cc.offtake_share.cumsum()
# bid headroom from run_01 bid options: does any higher step raise predicted revenue?
bo = pd.read_csv(D/"runs/run_01/bid_options.csv")
cur = bo[bo.step_pct == 0].set_index(["campaign_id", "keyword_id"]).pred_rev
top = bo[bo.step_pct > 0].groupby(["campaign_id", "keyword_id"]).pred_rev.max()
hr = ((top - cur) > 1).rename("bid_headroom").reset_index()
hr["sc"] = hr.campaign_id.str[2:4] + "-" + hr.campaign_id.str[5:]
cc["cells"] = hr.groupby("sc").size(); cc["cells_bid_headroom"] = hr.groupby("sc").bid_headroom.sum()
print("\n## SKU x city (warm-up per day), sorted by offtake")
print(cc[["offtake", "offtake_share", "cum_offtake_share", "spend_share", "droas", "iroas", "ad_share", "runout", "util", "osa", "cells", "cells_bid_headroom"]].round(2).to_string())
n = len(cc); k = int(np.ceil(0.2 * n))
print(f"\nPareto: top {k}/{n} SKU x city = {cc.offtake_share.iloc[:k].sum():.0%} of offtake, {cc.spend_share.iloc[:k].sum():.0%} of spend")

# ---------- role rules ----------
med_i = cc.iroas.median()
def role(r):
    if r.runout >= 0.5 and r.iroas >= med_i: return "fund budget"
    if r.runout >= 0.5: return "hold budget"
    if r.iroas >= med_i and r.cells_bid_headroom > 0: return "scale bids / keywords"
    if r.iroas >= med_i: return "efficient, saturated"
    return "trim / re-mix"
cc["role"] = cc.apply(role, axis=1)
print("\n## Roles (rule: run-out >= 50% of days, iROAS vs median", round(med_i, 2), ")")
print(cc.groupby("role").agg(n=("offtake", "size"), offtake_share=("offtake_share", "sum"), spend_share=("spend_share", "sum"), iroas=("iroas", "median")).round(2))
print(cc[["role"]].T.to_string())

# ---------- contested markets: who leads vs who should ----------
s1 = f[(f.day < W) & (f.slot == 1)].groupby(["city_id", "keyword_id", "sku_id"]).impressions.sum()
tot = f[f.day < W].groupby(["city_id", "keyword_id", "sku_id"]).impressions.sum()
share = (s1 / tot).rename("slot1_share")
mi = w.groupby(["city_id", "keyword_id", "sku_id"]).agg(spend=("spend_inr", "sum"), incr=("incr_rev", "sum"), rev=("ad_revenue_inr", "sum"))
mi["iroas"] = mi.incr / mi.spend; mi["droas"] = mi.rev / mi.spend
m = mi.join(share).reset_index()
m = m[m.groupby(["city_id", "keyword_id"]).sku_id.transform("nunique") >= 2]
lead = m.loc[m.groupby(["city_id", "keyword_id"]).spend.idxmax()][["city_id", "keyword_id", "sku_id", "iroas"]].rename(columns={"sku_id": "spend_leader", "iroas": "leader_iroas"})
best = m.loc[m.groupby(["city_id", "keyword_id"]).iroas.idxmax()][["city_id", "keyword_id", "sku_id", "iroas"]].rename(columns={"sku_id": "best_iroas_sku", "iroas": "best_iroas"})
mm = lead.merge(best, on=["city_id", "keyword_id"])
mm["match"] = mm.spend_leader == mm.best_iroas_sku
print(f"\n## Contested markets: spend leader is the best-incremental SKU in {mm.match.sum()}/{len(mm)}")
print(mm[~mm.match].merge(kw[["keyword_id", "keyword_type"]], on="keyword_id").round(2).to_string(index=False))
sk.to_csv(R/"eda/sku_tiers.csv"); cc.to_csv(R/"eda/sku_city_tiers.csv"); mm.to_csv(R/"eda/contested_markets.csv", index=False)
