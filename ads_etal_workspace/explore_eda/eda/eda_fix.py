import pandas as pd, numpy as np
from pathlib import Path
D = Path("grid-path-challenge/data")
f = pd.read_csv(D/"observed/daily_facts.csv").merge(pd.read_csv(D/"base/keywords.csv")[["keyword_id","keyword_type"]], on="keyword_id")
sc = pd.read_csv(D/"observed/sku_city_daily.csv")
d = f.groupby(["day","sku_id","city_id","keyword_type"]).ad_orders.sum().unstack(fill_value=0).reset_index()
d = d.merge(sc[["day","sku_id","city_id","organic_units","osa"]], on=["day","sku_id","city_id"])
d["sc"] = d.sku_id + d.city_id
for spec, fe in [("sku x city FE + day FE", ["sc","day"]), ("sku x city FE + dow", ["sc"])]:
    dd = d.copy(); dd["dow"] = dd.day % 7
    cols = fe + (["dow"] if "day" not in fe else [])
    X = pd.get_dummies(dd[cols].astype(str)).astype(float).join(dd[["brand","generic","competition","osa"]].astype(float))
    b, *_ = np.linalg.lstsq(X.values, dd.organic_units.values, rcond=None)
    print(spec, {c: round(v,3) for c, v in zip(X.columns, b) if c in ("brand","generic","competition","osa")})
# per-SKU generic coefficient (sku x city FE + day FE)
out = {}
for s, g in d.groupby("sku_id"):
    X = pd.get_dummies(g[["sc","day"]].astype(str)).astype(float).join(g[["brand","generic","competition"]].astype(float))
    b, *_ = np.linalg.lstsq(X.values, g.organic_units.values, rcond=None)
    out[s] = {c: round(v,2) for c, v in zip(X.columns, b) if c in ("brand","generic","competition")}
print("per SKU:", out)

view = pd.read_csv(D/"base/industry_rank_curve.csv").set_index("slot").view_rel
f["reach"] = f.impressions / f.slot.map(view); f["week"] = f.day // 7
rk = f.groupby(["week","city_id","keyword_id"]).reach.sum().unstack(["city_id","keyword_id"])
chg = (rk.loc[4:] / rk.loc[0:3].mean() - 1) * 100
s = chg.stack(["city_id","keyword_id"]).rename("pct").reset_index()
big = s[s.pct.abs() >= 25].sort_values("pct", key=abs, ascending=False)
print(big.groupby(["city_id","keyword_id"]).agg(first_week=("week","min"), weeks=("week","count"), max_pct=("pct", lambda x: x.loc[x.abs().idxmax()])).sort_values("max_pct", key=abs, ascending=False).round(0).head(15))
# bid changes by baseline in those cells (own-action confound)
ck = [pd.read_csv(D/f"runs/run_0{r}/actions.csv").assign(run=r) for r in range(1,7)]
ck = pd.concat(ck); ck["city_id"] = ck.campaign_id.str[-3:]
print(ck[ck.keyword_id.isin(["K03","K04","K07","K08"])].groupby(["city_id","keyword_id","action_type"]).size().unstack(fill_value=0).loc[["BLR","MUM","DEL"]])
# CPM change per cell between warmup and eval (competitor bid-up shock)
f["phase"] = np.where(f.day < 28, "w", "e")
c = f.groupby(["phase","city_id","keyword_id"]).apply(lambda g: g.spend_inr.sum()/g.impressions.sum()*1000, include_groups=False).unstack("phase")
c["pct"] = (c.e/c.w - 1)*100
print("CPM change, top:", c.sort_values("pct", key=abs, ascending=False).head(8).round(1).to_string())
