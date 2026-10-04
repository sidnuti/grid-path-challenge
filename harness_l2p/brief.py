"""State brief for L2′: a compact, observation-only picture of the portfolio that the planner (LLM or
rules) reads. Every row carries a `ref` id so an intent can cite its evidence.

Built only from what a policy may see (`Observation`) and the harness's own read-only tools:
`diagnose` (grid, verdicts, pacing, bids, options), `iota_lookup`, `siblings.markets`,
`detect_shocks`, `compute_headroom`. No world truth, no scenario file, no dev constants.

Sections
    P   portfolio: dROAS to date, floor, headroom, allowance
    R:  SKU x city role table (offtake/spend share, incremental ROAS estimate, run-out, bid headroom, OSA, role)
    K:  sub-category x keyword-type table (spend, dROAS, incremental ROAS)
    C:  cell table (campaign x keyword): verdict, tier, bid, slot-1 share, ROAS vs goal, marginal ROAS of a +20% bid
    M:  contested markets: current slot-1 holder vs best incremental sibling, gap, near-tie
    A:  anomalies: reach / CPM shocks (with own-action confound), OSA dips, reach trends by city x keyword
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gpc.guardrails import BID_CEIL, BID_FLOOR, BID_STEP, BUDGET_DOWN, BUDGET_MIN, BUDGET_UP, OSA_MIN, TOP_SLOT_SHARE
from gpc.observation import Observation

from harness.config import Params
from harness.tools.features import Diagnostics
from harness.tools.headroom import Headroom, compute_headroom
from harness.tools.shocks import detect_shocks
from harness.tools.siblings import markets

ROLE_WINDOW = 28
NEAR_TIE = 0.10


@dataclass
class Brief:
    run: int
    portfolio: dict
    roles: pd.DataFrame
    subcat: pd.DataFrame
    cells: pd.DataFrame
    markets: pd.DataFrame
    anomalies: pd.DataFrame
    trends: pd.DataFrame
    headroom: Headroom
    text: str = ""
    digest: str = ""
    refs: set = field(default_factory=set)


def _cell_id(cid: str, kid: str) -> str:
    return f"{cid}/{kid}"


def _roles(obs: Observation, diag: Diagnostics, iota: dict) -> pd.DataFrame:
    f = obs.window("daily_facts", ROLE_WINDOW)
    sc = obs.window("sku_city_daily", ROLE_WINDOW)
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    prod = obs.public["products"].set_index("sku_id")
    camp = obs.campaigns.set_index("campaign_id")
    f = f.assign(keyword_type=f.keyword_id.map(kt))
    f["io"] = [iota.get((s, t), 0.5) for s, t in zip(f.sku_id, f.keyword_type)]
    f["incr_rev"] = f.ad_orders * f.io * f.sku_id.map(prod.asp_inr)
    g = f.groupby("campaign_id").agg(spend=("spend_inr", "sum"), rev=("ad_revenue_inr", "sum"), incr=("incr_rev", "sum"))
    n = max(f.day.nunique(), 1)
    off = sc.groupby(["sku_id", "city_id"]).agg(offtake=("offtake_inr", "sum"), adu=("ad_units", "sum"), tot=("total_units", "sum"))
    osa3 = obs.window("sku_city_daily", 3).groupby(["sku_id", "city_id"]).osa.mean()
    opts = diag.options
    cur = opts[opts.step_pct == 0].set_index(["campaign_id", "keyword_id"]).pred_rev
    up = opts[opts.step_pct > 0].groupby(["campaign_id", "keyword_id"]).pred_rev.max()
    headroom_cells = ((up - cur.reindex(up.index).fillna(0)) > 1).groupby(level=0).sum()
    pacing = diag.pacing.set_index("campaign_id")
    rows = []
    for cid, c in camp.iterrows():
        s, city = c.sku_id, c.city_id
        sp = float(g.spend.get(cid, 0.0))
        o = off.loc[(s, city)] if (s, city) in off.index else None
        rows.append({
            "ref": f"R:{cid}", "campaign_id": cid, "sku_id": s, "city_id": city,
            "sub_category": prod.loc[s, "sub_category"], "asp": float(prod.loc[s, "asp_inr"]),
            "offtake_day": float(o.offtake) / n if o is not None else 0.0,
            "ad_unit_share": float(o.adu / o.tot) if o is not None and o.tot else 0.0,
            "spend_day": sp / n, "droas": float(g.rev.get(cid, 0.0)) / sp if sp else 0.0,
            "iroas": float(g.incr.get(cid, 0.0)) / sp if sp else 0.0,
            "budget": float(c.daily_budget_inr),
            "ran_out_7d": int(pacing.ran_out_days.get(cid, 0)) if cid in pacing.index else 0,
            "bid_headroom_cells": int(headroom_cells.get(cid, 0)),
            "osa_3d": float(osa3.get((s, city), 1.0)),
        })
    r = pd.DataFrame(rows)
    r["offtake_share"] = r.offtake_day / max(r.offtake_day.sum(), 1e-9)
    r["spend_share"] = r.spend_day / max(r.spend_day.sum(), 1e-9)
    med = float(r.iroas[r.spend_day > 0].median()) if (r.spend_day > 0).any() else 0.0

    def role(x):
        capped = x.ran_out_7d >= 2
        if capped:
            return "fund" if x.iroas >= med else "hold"
        if x.iroas >= med:
            return "scale" if x.bid_headroom_cells > 0 else "saturated"
        return "trim"
    r["role"] = r.apply(role, axis=1)
    r.attrs["iroas_median"] = med
    return r


def _subcat(obs: Observation, roles: pd.DataFrame, iota: dict) -> pd.DataFrame:
    f = obs.window("daily_facts", ROLE_WINDOW)
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    prod = obs.public["products"].set_index("sku_id")
    f = f.assign(keyword_type=f.keyword_id.map(kt), sub_category=f.sku_id.map(prod.sub_category))
    f["incr"] = f.ad_orders * [iota.get((s, t), 0.5) for s, t in zip(f.sku_id, f.keyword_type)] * f.sku_id.map(prod.asp_inr)
    g = f.groupby(["sub_category", "keyword_type"]).agg(spend=("spend_inr", "sum"), rev=("ad_revenue_inr", "sum"), incr=("incr", "sum"))
    n = max(f.day.nunique(), 1)
    g["spend_day"] = g.spend / n
    g["droas"] = g.rev / g.spend.replace(0, np.nan)
    g["iroas"] = g.incr / g.spend.replace(0, np.nan)
    g = g.reset_index()
    g["ref"] = "K:" + g.sub_category + ":" + g.keyword_type
    return g[["ref", "sub_category", "keyword_type", "spend_day", "droas", "iroas"]]


def _cells(obs: Observation, diag: Diagnostics, mk: pd.DataFrame, iota: dict) -> pd.DataFrame:
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    camp = obs.campaigns.set_index("campaign_id")
    v = diag.verdicts.set_index(["campaign_id", "keyword_id"])
    b = diag.bids.set_index(["campaign_id", "keyword_id"])
    o = diag.options.set_index(["campaign_id", "keyword_id", "step_pct"])
    s1 = mk.set_index(["campaign_id", "keyword_id"]).slot1_share_7d if len(mk) else pd.Series(dtype=float)
    rows = []
    for ck in obs.campaign_keywords.itertuples():
        key = (ck.campaign_id, ck.keyword_id)
        if not getattr(ck, "active", True):
            continue
        sku = camp.loc[ck.campaign_id, "sku_id"]
        t = kt.get(ck.keyword_id, "generic")
        mroas = np.nan
        if (*key, 0) in o.index and (*key, 20) in o.index:
            ds = o.loc[(*key, 20), "pred_spend"] - o.loc[(*key, 0), "pred_spend"]
            dr = o.loc[(*key, 20), "pred_rev"] - o.loc[(*key, 0), "pred_rev"]
            mroas = dr / ds if ds > 1 else np.nan
        rows.append({
            "ref": "C:" + _cell_id(*key), "campaign_id": ck.campaign_id, "keyword_id": ck.keyword_id,
            "sku_id": sku, "city_id": camp.loc[ck.campaign_id, "city_id"], "keyword_type": t,
            "verdict": v.verdict.get(key, "") if key in v.index else "",
            "tier": b.tier.get(key, "") if key in b.index else "",
            "bid": float(ck.bid_cpm_inr), "slot1_share": float(s1.get(key, 0.0)) if key in s1.index else 0.0,
            "droas": float(v.droas_shrunk.get(key, np.nan)) if key in v.index else np.nan,
            "goal": float(v.goal_droas.get(key, np.nan)) if key in v.index else np.nan,
            "spend_7d": float(v.spend_7d_avg.get(key, 0.0)) if key in v.index else 0.0,
            "mroas_up20": mroas, "iota": float(iota.get((sku, t), 0.5)),
        })
    return pd.DataFrame(rows)


def _markets(mk: pd.DataFrame) -> pd.DataFrame:
    if not len(mk):
        return pd.DataFrame(columns=["ref", "city_id", "keyword_id", "holder", "best", "gap", "near_tie"])
    rows = []
    for (city, kid), g in mk[mk.is_contested].groupby(["city_id", "keyword_id"]):
        g = g.sort_values("leader_score", ascending=False)
        holder = g.sort_values("slot1_share_7d", ascending=False).iloc[0]
        best, second = g.iloc[0], g.iloc[1]
        gap = (best.leader_score - second.leader_score) / best.leader_score if best.leader_score > 0 else 0.0
        rows.append({"ref": f"M:{city}:{kid}", "city_id": city, "keyword_id": kid,
                     "holder": f"{holder.sku_id}({holder.slot1_share_7d:.0%})",
                     "holder_sku": holder.sku_id, "best_sku": best.sku_id,
                     "best": f"{best.sku_id}(score {best.leader_score:.3f})",
                     "skus": " ".join(f"{r.sku_id}:{r.leader_score:.3f}" for r in g.itertuples()),
                     "gap": round(gap, 3), "near_tie": gap < NEAR_TIE,
                     "wrong_holder": holder.sku_id != best.sku_id and holder.slot1_share_7d >= 0.5})
    return pd.DataFrame(rows)


def _trends(obs: Observation) -> pd.DataFrame:
    """Slot-1-equivalent reach by city x keyword, last 7 days vs the 21 before, as % change."""
    f = obs.window("daily_facts", 28)
    view = obs.public["industry_rank_curve"].set_index("slot").view_rel
    f = f.assign(reach=f.impressions / f.slot.map(view))
    recent = f[f.day >= obs.day - 7].groupby(["city_id", "keyword_id"]).reach.sum() / 7
    base = f[f.day < obs.day - 7].groupby(["city_id", "keyword_id"]).reach.sum() / max(f[f.day < obs.day - 7].day.nunique(), 1)
    t = ((recent / base.replace(0, np.nan)) - 1).dropna().rename("reach_chg").reset_index()
    t["ref"] = "T:" + t.city_id + ":" + t.keyword_id
    return t.reindex(t.reach_chg.abs().sort_values(ascending=False).index)


def build_brief(obs: Observation, diag: Diagnostics, iota: dict, params: Params,
                own_action_days: dict | None = None, last_run: dict | None = None) -> Brief:
    """`last_run` (optional, from the policy's own state): {"allowance_used", "allowance_total"} of the previous run."""
    headroom = compute_headroom(obs, params)
    mk = markets(obs, diag.grid, iota)
    roles = _roles(obs, diag, iota)
    subcat = _subcat(obs, roles, iota)
    cells = _cells(obs, diag, mk, iota)
    # revision 2: incremental ROAS per cell, and which cells / campaigns the compiler protects from intent cuts
    cells["iroas"] = cells.droas * cells.iota
    fund = set(roles[roles.role == "fund"].campaign_id)
    cells["protected"] = [("fund" if c in fund else ("iota" if io >= 0.8 else "")) if v != "MISSES" else ""
                          for c, io, v in zip(cells.campaign_id, cells.iota, cells.verdict)]
    mkts = _markets(mk)
    sh = detect_shocks(obs, params, own_action_days=own_action_days)
    an = sh[sh.shock_reach | sh.shock_cpm | sh.shock_osa_drop].copy()
    an["ref"] = "A:" + an.campaign_id + "/" + an.keyword_id
    for c in ("z_reach", "z_cpm", "z_osa"):
        an[c] = an[c].clip(-10, 10)                    # a flat baseline gives z in the 100s; the sign and "big" are what matter
    an = an.reindex(an[["z_reach", "z_cpm", "z_osa"]].abs().max(axis=1).sort_values(ascending=False).index).head(12)
    trends = _trends(obs)
    portfolio = {"run": obs.run, "runs_left": 6 - obs.run + 1, "droas_to_date": headroom.droas_to_date,
                 "floor_with_margin": headroom.roas_floor, "headroom_inr_day": headroom.headroom_inr_day,
                 "allowance_inr_day": headroom.allowance_inr_day,
                 "spend_7d_day": float(obs.window("daily_facts", 7).spend_inr.sum() / 7),
                 "margin_above_floor": round(headroom.droas_to_date - obs.roas_floor, 3),
                 "last_run": last_run or {}}
    b = Brief(run=obs.run, portfolio=portfolio, roles=roles, subcat=subcat, cells=cells, markets=mkts,
              anomalies=an, trends=trends, headroom=headroom)
    b.text = render_brief(b)
    b.digest = hashlib.sha256(b.text.encode()).hexdigest()[:16]
    b.refs = set(roles.ref) | set(subcat.ref) | set(cells.ref) | set(mkts.ref) | set(an.ref) | set(trends.ref) | {"P"}
    return b


def _fmt(x, nd=2):
    if isinstance(x, (float, np.floating)):
        return "" if np.isnan(x) else f"{x:.{nd}f}"
    return str(x)


def _table(df: pd.DataFrame, cols: list[str], nd: dict | None = None) -> str:
    nd = nd or {}
    lines = [",".join(cols)]
    for r in df[cols].itertuples(index=False):
        lines.append(",".join(_fmt(v, nd.get(c, 2)) for c, v in zip(cols, r)))
    return "\n".join(lines)


def render_brief(b: Brief, max_trends: int = 12) -> str:
    p = b.portfolio
    levers = (f"bids: ₹{BID_FLOOR:.0f}-{BID_CEIL:.0f}, move ≤ ±{BID_STEP:.0%} per run; raises blocked on cells with ≥ {TOP_SLOT_SHARE:.0%} "
              f"slot-1 share or MISSES verdict (tier A/B); no increases when 3-day OSA < {OSA_MIN:.0%}. "
              f"budgets: +{BUDGET_UP:.0%} / -{BUDGET_DOWN:.0%} per run, min ₹{BUDGET_MIN:.0f}; a budget raise needs ≥ 2 run-out days of the last 7. "
              "dayparts: night, morning, afternoon, evening.")
    an = b.anomalies
    parts = [
        f"## P portfolio (run {p['run']} of 6)",
        f"droas_to_date={p['droas_to_date']}, floor_with_margin={p['floor_with_margin']}, "
        f"headroom_inr_day={p['headroom_inr_day']}, allowance_inr_day={p['allowance_inr_day']}, spend_7d_inr_day={p['spend_7d_day']:.0f}",
        f"margin_above_floor={p['margin_above_floor']} ROAS points. The floor only has to be met at the end of run 6: margin left then, "
        f"and allowance not spent in a run, are worth nothing."
        + (f" Last run you used ₹{p['last_run'].get('allowance_used', 0):.0f} of ₹{p['last_run'].get('allowance_total', 0):.0f}/day allowance."
           if p['last_run'] else ""),
        "## Levers and limits", levers,
        f"## R roles: SKU x city (last {ROLE_WINDOW} days; iroas = ad revenue counting only incremental orders / spend; "
        f"median iroas {b.roles.attrs.get('iroas_median', 0):.2f}; role: fund=capped+efficient, hold=capped+weak, scale=efficient+bid headroom, saturated, trim=weak)",
        _table(b.roles.sort_values("offtake_day", ascending=False),
               ["ref", "sub_category", "offtake_share", "spend_share", "droas", "iroas", "ad_unit_share", "budget", "ran_out_7d",
                "bid_headroom_cells", "osa_3d", "role"], {"offtake_share": 3, "spend_share": 3, "budget": 0}),
        "## K sub-category x keyword type",
        _table(b.subcat, ["ref", "spend_day", "droas", "iroas"], {"spend_day": 0}),
        "## C cells (bid in ₹ CPM; slot1_share last 7 days; droas shrunk vs goal; mroas_up20 = predicted revenue/spend of a +20% bid; "
        "iota = incremental share; iroas = droas x iota; protected = the compiler refuses cuts here (fund campaign, or iota >= 0.8 and clearing goal))",
        _table(b.cells, ["ref", "keyword_type", "verdict", "tier", "bid", "slot1_share", "droas", "goal", "iroas", "spend_7d", "mroas_up20", "iota", "protected"],
               {"bid": 0, "spend_7d": 0}),
        "## M contested markets (holder = sibling with most slot-1 share; best = highest incremental revenue per impression)",
        _table(b.markets, ["ref", "holder", "best", "skus", "gap", "near_tie", "wrong_holder"]) if len(b.markets) else "none",
        "## A anomalies (top 12; z vs prior 21 days, clipped to ±10; own_action_confound = this policy changed the cell recently)",
        _table(an, ["ref", "z_reach", "z_cpm", "z_osa", "direction", "own_action_confound"]) if len(an) else "none",
        f"## T reach trends by city x keyword (top {max_trends} by size; last 7 days vs 21 before)",
        _table(b.trends.head(max_trends), ["ref", "reach_chg"]) if len(b.trends) else "none",
    ]
    return "\n".join(parts)
