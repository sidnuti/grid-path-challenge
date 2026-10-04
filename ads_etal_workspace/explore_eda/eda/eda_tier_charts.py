"""Charts for the top-vs-bottom SKU section."""
import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
R = Path(__file__).resolve().parents[1]; F = R / "figures"
INK, INK2, GRID, SURF, BLUE, ORANGE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb", "#2a78d6", "#eb6834"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.titleweight": "bold",
    "axes.titlesize": 11, "axes.titlelocation": "left"})
sk = pd.read_csv(R/"eda/sku_tiers.csv", index_col=0); cc = pd.read_csv(R/"eda/sku_city_tiers.csv", index_col=0)
names = {"S1": "S1 Sandal soap", "S2": "S2 Body wash", "S3": "S3 Aloe soap", "S4": "S4 Shower gel", "S5": "S5 Kids bar"}

# 8. spend share vs offtake share per SKU (paired bars)
s = sk.sort_values("offtake_share", ascending=False); y = np.arange(len(s))
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.barh(y - 0.19, s.offtake_share, height=0.36, color=BLUE, label="share of offtake")
ax.barh(y + 0.19, s.spend_share, height=0.36, color=ORANGE, label="share of ad spend")
for yi, (o, sp, r) in enumerate(zip(s.offtake_share, s.spend_share, s.invest_ratio)):
    ax.text(max(o, sp) + 0.01, yi, f"spend ÷ offtake share = {r:.2f}", va="center", fontsize=8.5, color=INK2)
ax.set_yticks(y, [names[i] for i in s.index]); ax.invert_yaxis(); ax.set_xlim(0, 0.62); ax.grid(axis="y", visible=False)
ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0)); ax.legend(frameon=False, fontsize=9, loc="lower right")
ax.set_title("Top SKU S1 is under-funded relative to its offtake; S3 and the new S5 are over-funded (warm-up)")
fig.savefig(F/"08_sku_spend_vs_offtake.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 9. direct vs incremental ROAS per SKU (dumbbell)
s = sk.sort_values("iroas"); y = np.arange(len(s))
fig, ax = plt.subplots(figsize=(8, 3.2))
for yi, (dr, ir) in enumerate(zip(s.droas, s.iroas)): ax.plot([ir, dr], [yi, yi], color=GRID, lw=3, zorder=1)
ax.scatter(s.droas, y, s=70, color=ORANGE, zorder=2, label="direct ROAS (what the floor sees)", edgecolor=SURF, linewidth=1.5)
ax.scatter(s.iroas, y, s=70, color=BLUE, zorder=3, label="incremental ROAS estimate", edgecolor=SURF, linewidth=1.5)
for yi, (dr, ir) in enumerate(zip(s.droas, s.iroas)):
    ax.text(dr + 0.2, yi, f"{dr:.1f}×", va="center", fontsize=8.5, color=INK2); ax.text(ir - 0.2, yi, f"{ir:.1f}×", va="center", ha="right", fontsize=8.5, color=INK2)
ax.set_yticks(y, [names[i] for i in s.index]); ax.set_xlim(-0.6, 10); ax.grid(axis="y", visible=False)
ax.legend(frameon=False, fontsize=8.5, loc="lower right")
ax.set_title("Counting only incremental sales reorders the SKUs: body wash and shower gel lead, both soaps fall")
fig.savefig(F/"09_sku_droas_vs_iroas.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 10. SKU x city heatmap of incremental ROAS, with run-out marker
cc["sku"] = cc.index.str[:2]; cc["city"] = cc.index.str[3:]
cities = ["DEL", "MUM", "BLR", "HYD", "PUN"]; skus = ["S1", "S3", "S2", "S4", "S5"]
M = cc.pivot(index="sku", columns="city", values="iroas").loc[skus, cities]
O = cc.pivot(index="sku", columns="city", values="offtake").loc[skus, cities]
RO = cc.pivot(index="sku", columns="city", values="runout").loc[skus, cities]
fig, ax = plt.subplots(figsize=(8.4, 4.2))
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#eef4fc", "#9cc0ee", "#2a78d6", "#123f78"])
im = ax.imshow(M.values, cmap=cmap, vmin=0, vmax=5, aspect="auto")
for i in range(len(skus)):
    for j in range(len(cities)):
        v = M.values[i, j]; col = "white" if v > 2.8 else INK
        cap = "  ● capped" if RO.values[i, j] >= 0.5 else ""
        ax.text(j, i - 0.12, f"{v:.1f}×{cap}", ha="center", va="center", fontsize=9, color=col, fontweight="bold")
        ax.text(j, i + 0.22, f"₹{O.values[i, j]/1000:.0f}K/day", ha="center", va="center", fontsize=7.5, color=col)
ax.set_xticks(range(5), cities); ax.set_yticks(range(5), [names[s] for s in skus]); ax.grid(False)
for sp in ax.spines.values(): sp.set_visible(False)
cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02); cb.set_label("incremental ROAS", color=INK2); cb.outline.set_visible(False)
ax.set_title("Incremental ROAS by SKU × city, with offtake per day. ● = ran out of budget on ≥ 50% of warm-up days")
fig.savefig(F/"10_sku_city_iroas_heatmap.png", dpi=160, bbox_inches="tight"); plt.close(fig)
print("ok")
