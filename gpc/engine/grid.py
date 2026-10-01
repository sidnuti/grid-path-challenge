"""Step 1 — the priced grid.

For every cell (one campaign = one SKU × city, so a cell is campaign × keyword) the grid estimates,
per daypart and per ad slot (1 / 5 / 9 / 13): clearing CPM, impressions per day, orders per
day, revenue per day and spend per day. It is built only from observed data plus public priors.

Three things production taught us are encoded here on purpose:

* **Slots in one daypart are alternatives.** A bid buys one slot per daypart; the grid lists the
  options, it never adds them up.
* **Budget-truncated days understate capacity.** A campaign that ran out at 3pm shows little
  evening demand. Capacity is read from "full" days only (the campaign was still serving at the
  end of that daypart), else from the public search-volume prior.
* **Thin evidence is shrunk.** Conversion is pulled toward the keyword's cross-city average with
  weight orders / (orders + 25). Every value carries its provenance and a confidence tier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..observation import Observation
from ..world import DAYPART_PRICE, DAYPARTS, SLOTS

SHRINK_ORDERS = 25          # pseudo-orders behind the prior
WINDOW_DAYS = 28


def _curve(obs: Observation) -> pd.DataFrame:
    return obs.public["industry_rank_curve"].set_index("slot")


def build_grid(obs: Observation, window: int = WINDOW_DAYS) -> pd.DataFrame:
    p = obs.public
    curve = _curve(obs)
    view_rel, price_rel = curve.view_rel, curve.price_rel
    conv_rel = curve.conv_per_impr / curve.conv_per_impr.loc[1]
    cities = p["cities"].set_index("city_id")
    kws = p["keywords"].set_index("keyword_id")
    prods = p["products"].set_index("sku_id")
    rel = p["keyword_sku"].set_index(["sku_id", "keyword_id"]).relevance
    sku_city = p["sku_city"].set_index(["sku_id", "city_id"])

    f = obs.window("daily_facts", window).copy()
    cd = obs.window("campaign_daily", window)
    dp_idx = {dp: i for i, dp in enumerate(DAYPARTS)}

    # which (campaign, day, daypart) were "full" — still serving at the end of the daypart
    ran = cd.set_index(["campaign_id", "day"]).ran_out_daypart.to_dict()

    def full(cid, day, dp):
        r = ran.get((cid, day), "")
        return (r == "") or dp_idx[r] > dp_idx[dp]

    if len(f):
        f["full"] = [full(c, d, dp) for c, d, dp in zip(f.campaign_id, f.day, f.daypart)]
        f["impr_s1eq"] = f.impressions / f.slot.map(view_rel)              # slot-1-equivalent reach
        f["conv_w"] = f.impressions * f.slot.map(conv_rel)                  # slot-1-equivalent impressions for conv
        f["cpm_s1eq_x_impr"] = f.spend_inr * 1000 / f.slot.map(price_rel)   # rank-1 CPM × impressions

    # keyword-level parent conversion (slot-1 equivalent), for shrinkage
    if len(f):
        kw_par = f.groupby(["keyword_id"]).agg(o=("ad_orders", "sum"), w=("conv_w", "sum"))
        kw_par = (kw_par.o / kw_par.w).to_dict()
    else:
        kw_par = {}
    curve1 = float(curve.conv_per_impr.loc[1])

    rows = []
    ck = obs.campaign_keywords.merge(obs.campaigns[["campaign_id", "sku_id", "city_id"]])
    osa_recent = obs.window("sku_city_daily", 7).groupby(["sku_id", "city_id"]).osa.mean().to_dict()
    for r in ck.itertuples():
        c, k = cities.loc[r.city_id], kws.loc[r.keyword_id]
        asp = float(prods.loc[r.sku_id, "asp_inr"])
        cell = f[(f.campaign_id == r.campaign_id) & (f.keyword_id == r.keyword_id)] if len(f) else f
        orders = float(cell.ad_orders.sum()) if len(cell) else 0.0
        osa = osa_recent.get((r.sku_id, r.city_id), float(sku_city.loc[(r.sku_id, r.city_id), "base_osa"]))

        # conversion at slot 1, shrunk toward the keyword parent (or the industry prior × relevance)
        prior_conv1 = kw_par.get(r.keyword_id, curve1) * rel.loc[(r.sku_id, r.keyword_id)]
        if len(cell) and cell.conv_w.sum() > 0:
            obs_conv1 = cell.ad_orders.sum() / cell.conv_w.sum()
            wgt = orders / (orders + SHRINK_ORDERS)
            conv1 = wgt * obs_conv1 + (1 - wgt) * prior_conv1
        else:
            conv1 = prior_conv1
        tier = "A" if orders >= 25 else ("B" if orders >= 10 else "C")

        for d, dp in enumerate(DAYPARTS):
            seg = cell[cell.daypart == dp] if len(cell) else cell
            seg_full = seg[seg.full] if len(seg) else seg
            n_full_days = seg_full.day.nunique() if len(seg_full) else 0
            prior_reach = k.searches_30d / 30 * c.demand_share * c[f"share_{dp}"] * osa
            if n_full_days >= 3:
                reach = float(seg_full.impr_s1eq.sum() / n_full_days)
                reach_src = "observed"
            elif len(seg) and seg.day.nunique() >= 3:
                # only truncated days: scale the observed reach up by the prior's share — still a guess
                reach = max(float(seg.impr_s1eq.sum() / seg.day.nunique()), 0.5 * prior_reach)
                reach_src = "truncated"
            else:
                reach = prior_reach
                reach_src = "prior"
            prior_cpm1 = k.rank1_cpm_inr * c.cpm_index * DAYPART_PRICE[d]
            if len(seg) and seg.impressions.sum() > 0:
                obs_cpm1 = seg.cpm_s1eq_x_impr.sum() / seg.impressions.sum()
                w_cpm = seg.impressions.sum() / (seg.impressions.sum() + 2000)
                cpm1 = w_cpm * obs_cpm1 + (1 - w_cpm) * prior_cpm1
                cur_slot = int(round(np.average(seg.slot, weights=seg.impressions)))
            else:
                cpm1, cur_slot = prior_cpm1, 0
            for s in SLOTS:
                impr = reach * view_rel.loc[s]
                cpm = cpm1 * price_rel.loc[s]
                orders_d = impr * conv1 * conv_rel.loc[s]
                rows.append({
                    "campaign_id": r.campaign_id, "sku_id": r.sku_id, "city_id": r.city_id,
                    "keyword_id": r.keyword_id, "daypart": dp, "slot": s,
                    "cpm_inr": round(cpm, 1), "impressions_day": round(impr, 1),
                    "orders_day": round(orders_d, 3), "spend_day": round(impr * cpm / 1000, 2),
                    "revenue_day": round(orders_d * asp, 2), "droas": round(orders_d * asp / (impr * cpm / 1000), 3),
                    "reach_source": reach_src, "tier": tier, "orders_28d": orders, "current_slot": cur_slot,
                })
    return pd.DataFrame(rows)


def slot_at_bid(cell_dp: pd.DataFrame, bid: float) -> int | None:
    """Best slot whose estimated clearing CPM the bid meets, for one cell × daypart."""
    ok = cell_dp[cell_dp.cpm_inr <= bid]
    return int(ok.slot.min()) if len(ok) else None


def predict_cell(cell_grid: pd.DataFrame, bid: float, dayparts_on: dict[str, bool]) -> dict:
    """Unconstrained (no budget cap) daily spend / revenue / orders for one cell at one bid."""
    out = {"spend": 0.0, "revenue": 0.0, "orders": 0.0, "slots": {}}
    for dp, g in cell_grid.groupby("daypart", sort=False):
        if not dayparts_on.get(dp, True):
            out["slots"][dp] = None
            continue
        s = slot_at_bid(g, bid)
        out["slots"][dp] = s
        if s is None:
            continue
        row = g[g.slot == s].iloc[0]
        out["spend"] += row.spend_day
        out["revenue"] += row.revenue_day
        out["orders"] += row.orders_day
    return out
