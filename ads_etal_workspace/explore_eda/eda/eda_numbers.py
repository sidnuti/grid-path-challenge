"""Numeric EDA of the Grid Path Challenge data (baseline trajectory, dev scenario). Prints tables."""
import pandas as pd, numpy as np
from pathlib import Path
D = Path(__file__).resolve().parents[1] / "grid-path-challenge" / "data"
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
b = {p.stem: pd.read_csv(p) for p in (D / "base").glob("*.csv")}
f = pd.read_csv(D / "observed/daily_facts.csv")
cd = pd.read_csv(D / "observed/campaign_daily.csv")
sc = pd.read_csv(D / "observed/sku_city_daily.csv")
kw = b["keywords"]; prod = b["products"]
f = f.merge(kw[["keyword_id", "keyword_type", "keyword"]], on="keyword_id").merge(prod[["sku_id", "sub_category", "asp_inr"]], on="sku_id")
WARM = 28
f["phase"] = np.where(f.day < WARM, "warmup", "eval")
sc["phase"] = np.where(sc.day < WARM, "warmup", "eval")

print("days", f.day.min(), f.day.max(), "| rows", len(f))
print("\n## 1. Structure")
ks = b["keyword_sku"].merge(kw, on="keyword_id")
print(pd.crosstab(ks.sku_id, ks.keyword_id, values=ks.relevance, aggfunc="first").fillna("").to_string())
print(ks.groupby(["sku_id"]).keyword_type.value_counts().unstack(fill_value=0))
mk = b["campaign_keywords"].merge(b["campaigns"][["campaign_id", "sku_id", "city_id"]], on="campaign_id")
mkt = mk.groupby(["city_id", "keyword_id"]).sku_id.nunique()
print("markets (city x kw):", len(mkt), "| contested (>=2 Aurel SKUs):", (mkt >= 2).sum(), "| max SKUs in one market:", mkt.max())
print(mkt.groupby(level=1).max().rename("max_skus_per_market").to_frame().T)

print("\n## 2. Plan by keyword type")
pl = b["plan"].merge(kw, on="keyword_id")
print(pl.groupby("keyword_type").agg(cells=("sku_id", "size"), budget=("plan_budget_inr_day", "sum"),
      goal_med=("goal_droas", "median"), floor_med=("marginal_floor_droas", "median")))
print(pl.evidence_tier.value_counts())

def agg(g):
    s = g.agg(spend=("spend_inr", "sum"), impr=("impressions", "sum"), orders=("ad_orders", "sum"), rev=("ad_revenue_inr", "sum"))
    s["droas"] = s.rev / s.spend; s["cpm"] = s.spend / s.impr * 1000; s["cvr_pct"] = s.orders / s.impr * 100
    return s

w = f[f.phase == "warmup"]
print("\n## 3. Warm-up by keyword type (per day)")
t = agg(w.groupby("keyword_type")); t[["spend", "impr", "orders", "rev"]] /= WARM
t["spend_share"] = t.spend / t.spend.sum(); print(t.round(2))
print("\n## 3b. Warm-up by keyword (per day)")
t = agg(w.groupby(["keyword_type", "keyword_id", "keyword"])); t[["spend", "rev"]] /= WARM; print(t[["spend", "rev", "droas", "cpm", "cvr_pct"]].round(2))
print("\n## 3c. Warm-up by sub-category x keyword type: dROAS")
print(agg(w.groupby(["sub_category", "keyword_type"])).droas.unstack().round(2))

print("\n## 4. SKU and city (warm-up, per day)")
for k in ["sku_id", "city_id"]:
    a = agg(w.groupby(k)); a[["spend", "rev"]] /= WARM
    s = sc[sc.phase == "warmup"].groupby(k).agg(offtake=("offtake_inr", "sum"), ad_u=("ad_units", "sum"), tot_u=("total_units", "sum"))
    s["offtake"] /= WARM; s["ad_unit_share"] = s.ad_u / s.tot_u
    print(a[["spend", "rev", "droas"]].join(s[["offtake", "ad_unit_share"]]).round(3))

print("\n## 5. Slots and dayparts (warm-up)")
print(agg(w.groupby("slot"))[["impr", "cpm", "cvr_pct", "droas"]].assign(impr_share=lambda x: x.impr / x.impr.sum()).round(3))
print(agg(w.groupby("daypart"))[["spend", "cpm", "cvr_pct", "droas"]].assign(spend_share=lambda x: x.spend / x.spend.sum()).round(3))

print("\n## 6. Budget run-out")
cd["phase"] = np.where(cd.day < WARM, "warmup", "eval")
r = cd.groupby(["phase"]).ran_out.mean(); print("run-out rate", r.round(3).to_dict())
ro = cd[cd.phase == "warmup"].groupby("campaign_id").ran_out.sum().sort_values(ascending=False)
print("warm-up run-out days by campaign (top 10):", ro.head(10).to_dict())
print("run-out daypart:", cd[cd.ran_out].ran_out_daypart.value_counts().to_dict())
print("budget utilisation warm-up:", round((cd[cd.phase=='warmup'].spend_inr.sum() / cd[cd.phase=='warmup'].daily_budget_inr.sum()), 3))

print("\n## 7. Portfolio by week (baseline trajectory)")
f["week"] = f.day // 7; sc["week"] = sc.day // 7
wk = agg(f.groupby("week")).join(sc.groupby("week").agg(offtake=("offtake_inr", "sum"), org=("organic_units", "sum"), adu=("ad_units", "sum")))
wk[["spend", "rev", "offtake"]] /= 7
print(wk[["spend", "rev", "droas", "offtake", "org", "adu"]].round(2))

print("\n## 8. Cannibalisation: organic units ~ ad orders by keyword type (sku x city x day, FE)")
d = f.groupby(["day", "sku_id", "city_id", "keyword_type"]).ad_orders.sum().unstack(fill_value=0).reset_index()
d = d.merge(sc[["day", "sku_id", "city_id", "organic_units", "osa"]], on=["day", "sku_id", "city_id"])
d["dow"] = d.day % 7
X = pd.get_dummies(d[["sku_id", "city_id", "dow"]].astype(str), drop_first=False).astype(float)
X = X.join(d[["brand", "generic", "competition"]].astype(float)).join(d[["osa"]])
beta, *_ = np.linalg.lstsq(X.values, d.organic_units.values, rcond=None)
print({c: round(v, 3) for c, v in zip(X.columns, beta) if c in ("brand", "generic", "competition", "osa")})

print("\n## 9. Anomalies: weekly z of slot-1-equivalent reach per city x keyword (eval weeks vs warm-up)")
view = b["industry_rank_curve"].set_index("slot").view_rel
f["reach"] = f.impressions / f.slot.map(view)
rk = f.groupby(["week", "city_id", "keyword_id"]).reach.sum().unstack(["city_id", "keyword_id"])
base_m, base_s = rk.loc[0:3].mean(), rk.loc[0:3].std()
z = ((rk - base_m) / base_s).loc[4:]
top = z.stack(["city_id", "keyword_id"]).abs().sort_values(ascending=False).head(12)
print(top.round(1).to_string())
print("\nCPM by week, competitor keywords:")
print(agg(f[f.keyword_type == "competition"].groupby(["week", "keyword_id"])).cpm.unstack().round(0))
print("\nOSA min by sku x city (all days):")
o = sc.groupby(["sku_id", "city_id"]).osa.agg(["min", "mean"]); print(o[o["min"] < 0.8].round(2))
lo = sc[sc.osa < 0.6][["day", "sku_id", "city_id", "osa"]]; print(lo.groupby(["sku_id", "city_id"]).day.agg(["min", "max", "count"]))

print("\n## 10. Baseline actions per run")
acts = []
for r_ in range(1, 7):
    p = D / f"runs/run_0{r_}"
    a = pd.read_csv(p / "actions.csv"); pr = pd.read_csv(p / "proposed_actions.csv")
    acts.append(dict(run=r_, proposed=len(pr), shipped=len(a), **a.action_type.value_counts().to_dict()))
print(pd.DataFrame(acts).fillna(0).set_index("run"))
print(pd.read_csv(D / "runs/run_03/guardrail_log.csv").head(3).to_string())
