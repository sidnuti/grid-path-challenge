"""Charts for the EDA report. Writes PNGs to explore_eda/figures/."""
import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
R = Path(__file__).resolve().parents[1]; D = R / "grid-path-challenge/data"; F = R / "figures"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
TYPE_C = {"brand": "#2a78d6", "competition": "#eb6834", "generic": "#1baf7a"}
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.titleweight": "bold",
    "axes.titlesize": 11, "axes.titlelocation": "left"})
kw = pd.read_csv(D/"base/keywords.csv"); prod = pd.read_csv(D/"base/products.csv")
f = pd.read_csv(D/"observed/daily_facts.csv").merge(kw, on="keyword_id")
sc = pd.read_csv(D/"observed/sku_city_daily.csv"); cd = pd.read_csv(D/"observed/campaign_daily.csv")
W = 28; w = f[f.day < W]

# 1. direct ROAS by keyword vs spend share
g = w.groupby(["keyword_id", "keyword", "keyword_type"]).agg(spend=("spend_inr", "sum"), rev=("ad_revenue_inr", "sum")).reset_index()
g["droas"] = g.rev / g.spend; g["share"] = g.spend / g.spend.sum(); g = g.sort_values("droas")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True, gridspec_kw={"wspace": 0.08})
y = np.arange(len(g)); lab = g.keyword + "  (" + g.keyword_id + ")"
for ax, col, title, fmt in [(a1, "droas", "Direct ROAS, warm-up", "{:.1f}×"), (a2, "share", "Share of ad spend, warm-up", "{:.0%}")]:
    ax.barh(y, g[col], color=[TYPE_C[t] for t in g.keyword_type], height=0.62)
    for yi, v in zip(y, g[col]): ax.text(v, yi, " " + fmt.format(v), va="center", fontsize=9, color=INK2)
    ax.set_title(title); ax.grid(axis="y", visible=False); ax.set_xlim(0, g[col].max() * 1.22)
a1.set_yticks(y, lab)
from matplotlib.patches import Patch
a1.legend(handles=[Patch(color=c, label=t) for t, c in TYPE_C.items()], frameon=False, loc="lower right", fontsize=9)
fig.suptitle("Brand terms look best on direct ROAS; 'soap' and 'velora' take 54% of spend", x=0.01, ha="left", fontsize=12, fontweight="bold")
fig.savefig(F/"01_keyword_droas_spend.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 2. cannibalisation (sku x city FE + day FE) vs direct ROAS story
d = f.groupby(["day", "sku_id", "city_id", "keyword_type"]).ad_orders.sum().unstack(fill_value=0).reset_index()
d = d.merge(sc[["day", "sku_id", "city_id", "organic_units"]], on=["day", "sku_id", "city_id"]); d["sc"] = d.sku_id + d.city_id
X = pd.get_dummies(d[["sc", "day"]].astype(str)).astype(float).join(d[["brand", "generic", "competition"]].astype(float))
b, *_ = np.linalg.lstsq(X.values, d.organic_units.values, rcond=None); coef = dict(zip(X.columns, b))
types = ["brand", "generic", "competition"]; disp = [-coef[t] for t in types]; incr = [1 - x for x in disp]
fig, ax = plt.subplots(figsize=(7, 3.2))
ax.barh(types, disp, color=[TYPE_C[t] for t in types], height=0.55)
for i, v in enumerate(disp): ax.text(max(v, 0), i, f"  {v:.2f} organic units lost  →  ~{max(0, 1 - v):.0%} of ad orders incremental", va="center", fontsize=9, color=INK2)
ax.set_xlim(0, 1.9); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
ax.set_title("Organic units displaced per ad order (sku×city and day fixed effects, 70 days)")
fig.savefig(F/"02_cannibalisation.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 3. portfolio by week: small multiples, one axis each
f["week"] = f.day // 7; sc["week"] = sc.day // 7
wk = f.groupby("week").agg(spend=("spend_inr", "sum"), rev=("ad_revenue_inr", "sum")).join(sc.groupby("week").offtake_inr.sum())
wk["droas"] = wk.rev / wk.spend
for c in ["spend", "offtake_inr"]: wk[c] = wk[c] / wk.loc[0:3, c].mean() * 100
fig, axs = plt.subplots(1, 3, figsize=(11, 3.1), gridspec_kw={"wspace": 0.28})
for ax, col, title, fmt in [(axs[0], "offtake_inr", "Offtake (warm-up avg = 100)", "{:.1f}"), (axs[1], "spend", "Ad spend (warm-up avg = 100)", "{:.1f}"), (axs[2], "droas", "Direct ROAS", "{:.2f}×")]:
    ax.axvspan(-0.5, 3.5, color=GRID, alpha=0.6, lw=0); ax.plot(wk.index, wk[col], color="#2a78d6", lw=2, marker="o", ms=4)
    ax.set_title(title); ax.set_xticks(range(10), ["W" + str(i) for i in range(4)] + ["R" + str(i) for i in range(1, 7)], fontsize=8)
    ax.text(wk.index[-1], wk[col].iloc[-1], "  " + fmt.format(wk[col].iloc[-1]), va="center", fontsize=8.5, color=INK2)
    ax.text(1.5, ax.get_ylim()[1], "warm-up", ha="center", va="top", fontsize=8, color=INK2)
axs[0].set_ylim(90, 104); axs[1].set_ylim(90, 104)
axs[2].axhline(4.54, color=INK2, lw=1, ls="--"); axs[2].text(0, 4.56, "floor 4.54×", fontsize=8, color=INK2, va="bottom")
fig.suptitle("Baseline trajectory: offtake flat (±1%), spend down ~8%, ROAS climbs well above the floor", x=0.01, ha="left", fontsize=12, fontweight="bold", y=1.06)
fig.savefig(F/"03_portfolio_weekly.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 4. run-out heatmap campaign x day
m = cd.pivot(index="campaign_id", columns="day", values="ran_out").astype(float)
order = m.loc[:, :W - 1].sum(axis=1).sort_values(ascending=False).index; m = m.loc[order]
fig, ax = plt.subplots(figsize=(11, 5.4))
ax.imshow(m.values, aspect="auto", cmap=matplotlib.colors.ListedColormap([SURF, "#2a78d6"]), interpolation="nearest")
ax.set_yticks(range(len(m)), m.index, fontsize=8); ax.set_xticks([0, 14, 28, 35, 42, 49, 56, 63], ["d0", "d14", "R1", "R2", "R3", "R4", "R5", "R6"], fontsize=8)
ax.axvline(W - 0.5, color=INK, lw=1); ax.grid(False)
ax.set_title("Budget run-out by campaign and day (blue = ran out). Six campaigns ran out on all 28 warm-up days")
fig.savefig(F/"04_runout_heatmap.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 5. anomalies: reach index for flagged cells
view = pd.read_csv(D/"base/industry_rank_curve.csv").set_index("slot").view_rel
f["reach"] = f.impressions / f.slot.map(view)
rk = f.groupby(["week", "city_id", "keyword_id"]).reach.sum().unstack(["city_id", "keyword_id"])
idx = rk / rk.loc[0:3].mean() * 100
cells = [("BLR", "K07", "sandal soap"), ("BLR", "K08", "kids soap"), ("DEL", "K07", "sandal soap"), ("DEL", "K08", "kids soap"), ("MUM", "K05", "body wash"), ("MUM", "K06", "shower gel")]
fig, axs = plt.subplots(2, 3, figsize=(11, 5), sharey=True, gridspec_kw={"hspace": 0.45, "wspace": 0.1})
for ax, (c, k, name) in zip(axs.flat, cells):
    s = idx[(c, k)]; ax.axvspan(-0.5, 3.5, color=GRID, alpha=0.6, lw=0); ax.axhline(100, color=INK2, lw=0.8)
    ax.plot(s.index, s.values, color="#2a78d6", lw=2, marker="o", ms=3.5)
    ax.set_title(f"{c} · {k} {name}", fontsize=10); ax.set_xticks(range(10), ["W0", "", "", "W3", "R1", "", "", "R4", "", "R6"], fontsize=8)
    ax.text(9, s.iloc[-1], f" {s.iloc[-1]:.0f}", va="center", fontsize=8.5, color=INK2)
axs[0, 0].set_ylabel("reach index (warm-up = 100)"); axs[1, 0].set_ylabel("reach index (warm-up = 100)")
fig.suptitle("Demand anomalies in slot-1-equivalent reach: K07/K08 surge (BLR, then DEL); MUM body wash and shower gel rise, then fall (confounded with the baseline's own bid cuts)", x=0.01, ha="left", fontsize=11.5, fontweight="bold", y=1.0)
fig.savefig(F/"05_anomalies_reach.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 6. OSA dip
fig, ax = plt.subplots(figsize=(8, 2.8))
for (s_, c_), col in [(("S2", "HYD"), "#eb6834"), (("S2", "BLR"), "#2a78d6")]:
    x = sc[(sc.sku_id == s_) & (sc.city_id == c_)]; ax.plot(x.day, x.osa, color=col, lw=2, label=f"{s_} {c_}")
ax.axhline(0.6, color=INK2, lw=0.8, ls="--"); ax.text(0, 0.61, "G4: no increases below 60% OSA (3-day)", fontsize=8, color=INK2)
ax.axvline(W - 0.5, color=INK, lw=0.8); ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.set_ylim(0.35, 1)
ax.set_title("On-shelf availability: S2 (charcoal body wash) in HYD drops to 0.42 on days 42–48")
fig.savefig(F/"06_osa_dip.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 7. baseline action mix per run
rows = []
for r in range(1, 7):
    p = D/f"runs/run_0{r}"; a = pd.read_csv(p/"actions.csv"); pr = pd.read_csv(p/"proposed_actions.csv")
    rows.append(dict(run=f"R{r}", blocked=len(pr) - len(a), **a.action_type.value_counts().to_dict()))
am = pd.DataFrame(rows).set_index("run").fillna(0)[["reduce_cpm", "increase_cpm", "increase_budget", "blocked"]]
cols = {"reduce_cpm": "#2a78d6", "increase_cpm": "#eb6834", "increase_budget": "#1baf7a", "blocked": "#c9c7c0"}
fig, ax = plt.subplots(figsize=(8, 3.2)); bottom = np.zeros(len(am))
for c in am.columns:
    ax.bar(am.index, am[c], bottom=bottom, color=cols[c], width=0.6, label=c.replace("_", " "), edgecolor=SURF, linewidth=2); bottom += am[c].values
for i, v in enumerate(bottom): ax.text(i, v, f"{int(v)}", ha="center", va="bottom", fontsize=9, color=INK2)
ax.legend(frameon=False, fontsize=8.5, ncol=4, loc="upper right"); ax.grid(axis="x", visible=False); ax.set_ylim(0, bottom.max() * 1.25)
ax.set_title("Baseline actions per run: mostly bid cuts; never pause, budget cut or daypart change")
fig.savefig(F/"07_baseline_actions.png", dpi=160, bbox_inches="tight"); plt.close(fig)
print("ok", sorted(p.name for p in F.glob("*.png")))
