"""The L0 intent compiler: the only place an L2′ intent becomes an action.

An intent names a verb and a scope; the compiler
    1. expands the scope to cells / campaigns (unknown ids or an empty scope are rejected),
    2. picks concrete values from the engine's own bid grid (`diag.options`) and the guardrail
       limits (G1 bid bounds, G2 ±50% step, G6 budget step),
    3. resolves conflicts (one action per lever, as G0 requires; the higher-confidence intent wins),
    4. merges with L0's own candidates (`augment`: intents override L0 on the same lever, `hold`
       removes L0 candidates in scope) or uses intents alone (`native`),
    5. drops anything `harness.tools.precheck` says a guardrail would block,
    6. funds increases from the headroom allowance plus the slack freed by this run's cuts,
       highest incremental ratio first (intents before L0), via the guardrail's own projection.

Revision 2 (2026-10-04, after X8 replicate 0): protected cells and campaigns (no intent cuts on
highly incremental cells that clear goal, or on "fund" campaigns), share-curve pricing for raises the
grid prices at zero, and campaign-level holds that block only the budget lever.

Nothing the LLM writes reaches the market without passing through this module and then
`gpc.guardrails`. Every emitted action carries `reason = "L2P:<intent id>: ..."`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gpc.guardrails import BID_CEIL, BID_FLOOR, BID_STEP, BUDGET_DOWN, BUDGET_MIN, BUDGET_UP
from gpc.observation import Observation

from harness.tools.features import Diagnostics
from harness.tools.precheck import filter_precheck, precheck
from harness.tools.sizing import project_candidates

from .brief import Brief
from .intents import DAYPARTS, Intent, IntentPlan

ACTION_COLS = ["campaign_id", "keyword_id", "action_type", "new_value", "reason"]
SIZE_BID = {"small": 0.10, "medium": 0.20, "large": 0.40}
SIZE_BUDGET_UP = {"small": 0.15, "medium": 0.30, "large": 0.50}
SIZE_BUDGET_DOWN = {"small": 0.10, "medium": 0.20, "large": 0.30}
MAX_CELLS_PER_INTENT = 20
MAX_PAUSES_PER_RUN = 8
PROTECT_IOTA = 0.8          # intent cuts are refused on cells at least this incremental that clear goal
SHARE_FULL_AT = 0.40        # share-curve pricing: a +40% bid is assumed to win slot 1 outright (X3.1: share reaches ~1.0 at +30-50%)
INCREASES = ("increase_cpm", "increase_budget")


@dataclass
class CompileResult:
    actions: pd.DataFrame
    report: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    l0_overridden: int = 0
    l0_held: int = 0
    allowance_used: float = 0.0
    allowance_total: float = 0.0


def _lever(action_type: str, cid: str, kid: str) -> tuple:
    if action_type in ("increase_cpm", "reduce_cpm", "pause_keyword"):
        return (cid, kid, "bid")
    return (cid, "", "budget" if "budget" in action_type else "dayparts")


class _Ctx:
    def __init__(self, obs: Observation, diag: Diagnostics, brief: Brief, iota: dict):
        self.obs, self.diag, self.brief, self.iota = obs, diag, brief, iota
        self.camp = obs.campaigns.set_index("campaign_id")
        ck = obs.campaign_keywords
        self.ck = ck[ck.active.astype(bool)] if "active" in ck else ck
        self.live = self.ck.set_index(["campaign_id", "keyword_id"]).bid_cpm_inr
        self.kt = obs.public["keywords"].set_index("keyword_id").keyword_type
        self.subcat = obs.public["products"].set_index("sku_id").sub_category
        self.opts = diag.options
        cells = brief.cells.set_index(["campaign_id", "keyword_id"]) if len(brief.cells) else None
        self.s1 = cells.slot1_share if cells is not None else pd.Series(dtype=float)
        self.verdict = diag.verdicts.set_index(["campaign_id", "keyword_id"]).verdict
        self.role = brief.roles.set_index("campaign_id").role if len(brief.roles) else pd.Series(dtype=str)

    def protected(self, cid: str, kid: str, action_type: str) -> str:
        """Why an intent cut on this lever is refused, or "" if it is allowed."""
        misses = kid and self.verdict.get((cid, kid), "") == "MISSES"
        if self.role.get(cid, "") == "fund" and not misses:
            return f"protected: fund campaign {cid} (capped and efficient); raise it instead"
        if kid and not misses and self.cell_iota(cid, kid) >= PROTECT_IOTA:
            return f"protected: highly incremental cell (iota {self.cell_iota(cid, kid):.2f}) that clears goal"
        return ""

    # ── scope ────────────────────────────────────────────────────────────────
    def campaigns_in(self, sc) -> tuple[list[str], str]:
        c = self.camp
        if sc.campaign_id and sc.campaign_id not in c.index:
            # a common slip: "C-S4" for SKU S4, or a campaign id that disagrees with the sku/city also given
            import re
            m = re.fullmatch(r"C-(S\d+)", sc.campaign_id)
            if m or sc.sku_id or sc.city_id:
                sc = sc.model_copy(update={"campaign_id": None, "sku_id": sc.sku_id or (m.group(1) if m else None)})
            else:
                return [], f"unknown campaign {sc.campaign_id}"
        if sc.campaign_id:
            return [sc.campaign_id], ""
        m = pd.Series(True, index=c.index)
        if sc.sku_id:
            if sc.sku_id not in set(c.sku_id):
                return [], f"unknown sku {sc.sku_id}"
            m &= c.sku_id == sc.sku_id
        if sc.city_id:
            if sc.city_id not in set(c.city_id):
                return [], f"unknown city {sc.city_id}"
            m &= c.city_id == sc.city_id
        if sc.sub_category:
            if sc.sub_category not in set(self.subcat):
                return [], f"unknown sub-category {sc.sub_category}"
            m &= c.sku_id.map(self.subcat) == sc.sub_category
        return list(c.index[m]), ""

    def cells_in(self, sc) -> tuple[list[tuple[str, str]], str]:
        camps, why = self.campaigns_in(sc)
        if why:
            return [], why
        cells = self.ck[self.ck.campaign_id.isin(camps)]
        if sc.keyword_id:
            if sc.keyword_id not in set(self.kt.index):
                return [], f"unknown keyword {sc.keyword_id}"
            cells = cells[cells.keyword_id == sc.keyword_id]
        if sc.keyword_type:
            if sc.keyword_type not in set(self.kt):
                return [], f"unknown keyword type {sc.keyword_type}"
            cells = cells[cells.keyword_id.map(self.kt) == sc.keyword_type]
        out = list(zip(cells.campaign_id, cells.keyword_id))
        if not out:
            return [], "scope matches no active cell"
        if len(out) > MAX_CELLS_PER_INTENT:
            return [], f"scope too broad ({len(out)} cells > {MAX_CELLS_PER_INTENT})"
        return out, ""

    # ── values ───────────────────────────────────────────────────────────────
    def bid(self, cid: str, kid: str, direction: int, size: str, target_slot: int | None) -> float:
        live = float(self.live[(cid, kid)])
        new = None
        if direction > 0 and target_slot:
            o = self.opts[(self.opts.campaign_id == cid) & (self.opts.keyword_id == kid) & (self.opts.step_pct > 0)]
            for r in o.sort_values("step_pct").itertuples():
                slots = [int(s) for s in str(r.slots).split("/") if s.isdigit()]
                if slots and max(slots) <= target_slot:
                    new = float(r.bid)
                    break
        if new is None:
            new = live * (1 + direction * SIZE_BID[size])
        new = float(np.clip(new, BID_FLOOR, BID_CEIL))
        new = float(np.clip(new, live * (1 - BID_STEP), live * (1 + BID_STEP)))
        return round(new / 5) * 5.0

    def cell_iota(self, cid: str, kid: str) -> float:
        sku = self.camp.loc[cid, "sku_id"]
        return float(self.iota.get((sku, self.kt.get(kid, "generic")), 0.5))

    def campaign_iota(self, cid: str) -> float:
        cells = self.ck[self.ck.campaign_id == cid]
        return float(np.mean([self.cell_iota(cid, k) for k in cells.keyword_id])) if len(cells) else 0.5


def _row(cid, kid, at, value, it: Intent, note: str) -> dict:
    return {"campaign_id": cid, "keyword_id": kid, "action_type": at, "new_value": value,
            "reason": f"L2P:{it.id}: {note}"[:200], "intent_id": it.id}


def _expand(it: Intent, x: _Ctx) -> tuple[list[dict], set, str]:
    """Returns (action rows, held levers, rejection reason)."""
    sc, v = it.scope, it.verb
    if sc.is_empty():
        return [], set(), "empty scope"
    cell_level = v in ("raise_bid", "cut_bid", "pause") or (v == "hold" and bool(sc.keyword_id or sc.keyword_type))
    if cell_level:
        cells, why = x.cells_in(sc)
        if why:
            return [], set(), why
        if v == "hold":
            return [], {(c, k, "bid") for c, k in cells}, ""
        rows = []
        for c, k in cells:
            if v == "pause":
                rows.append(_row(c, k, "pause_keyword", 0.0, it, "pause"))
                continue
            d = 1 if v == "raise_bid" else -1
            nv = x.bid(c, k, d, it.size, it.target_slot)
            live = float(x.live[(c, k)])
            if (d > 0 and nv > live) or (d < 0 and nv < live):
                rows.append(_row(c, k, "increase_cpm" if d > 0 else "reduce_cpm", nv, it, f"{v} {it.size} ₹{live:.0f}→₹{nv:.0f}"))
        return rows, set(), "" if rows else "no value change possible within limits"
    camps, why = x.campaigns_in(sc)
    if why:
        return [], set(), why
    if v == "hold":
        # a campaign hold blocks its budget raise only; to block bid moves the intent must name cells
        return [], {(c, "", "budget") for c in camps}, ""
    if v in ("raise_budget", "cut_budget"):
        rows = []
        for c in camps:
            cur = float(x.camp.loc[c, "daily_budget_inr"])
            if v == "raise_budget":
                nv = min(cur * (1 + SIZE_BUDGET_UP[it.size]), cur * (1 + BUDGET_UP))
                rows.append(_row(c, "", "increase_budget", round(nv, 0), it, f"budget {it.size} ₹{cur:.0f}→₹{nv:.0f}"))
            else:
                nv = max(cur * (1 - SIZE_BUDGET_DOWN[it.size]), cur * (1 - BUDGET_DOWN), BUDGET_MIN)
                if nv < cur:
                    rows.append(_row(c, "", "reduce_budget", round(nv, 0), it, f"budget cut {it.size} ₹{cur:.0f}→₹{nv:.0f}"))
        return rows, set(), "" if rows else "no budget change possible"
    if v == "set_dayparts":
        dps = [d for d in DAYPARTS if d in it.dayparts]
        if not dps:
            return [], set(), "set_dayparts needs at least one valid daypart"
        rows = []
        for c in camps:
            cur = [d for d in DAYPARTS if bool(x.camp.loc[c, f"on_{d}"])]
            if cur != dps:
                rows.append(_row(c, "", "set_dayparts", ",".join(dps), it, f"dayparts {','.join(cur)}→{','.join(dps)}"))
        return rows, set(), "" if rows else "dayparts already set"
    if v in ("lead_market", "yield_market"):
        if not (sc.sku_id and sc.city_id and sc.keyword_id):
            return [], set(), f"{v} needs sku_id, city_id and keyword_id"
        mcells = x.ck[(x.ck.keyword_id == sc.keyword_id) & (x.ck.campaign_id.map(x.camp.city_id) == sc.city_id)]
        mine = [c for c in mcells.campaign_id if x.camp.loc[c, "sku_id"] == sc.sku_id]
        if not mine:
            return [], set(), f"{sc.sku_id} does not bid on {sc.keyword_id} in {sc.city_id}"
        me, others = mine[0], [c for c in mcells.campaign_id if c != mine[0]]
        rows, held = [], set()
        if v == "lead_market":
            my_s1 = float(x.s1.get((me, sc.keyword_id), 0.0))
            if my_s1 < 0.8:
                nv = x.bid(me, sc.keyword_id, 1, it.size, 1)
                raise_row = _row(me, sc.keyword_id, "increase_cpm", nv, it, f"lead {sc.city_id}/{sc.keyword_id}")
                ok, why = precheck(x.obs, x.diag.verdicts, x.diag.pacing, raise_row)
                if not ok or nv <= float(x.live[(me, sc.keyword_id)]):
                    # cutting the current holder when the leader cannot step up only loses the market
                    return [], set(), f"leader {sc.sku_id} cannot take slot 1 ({why or 'no higher bid available'})"
                rows.append(raise_row)
            for o in others:
                held.add((o, sc.keyword_id, "bid"))
                if float(x.s1.get((o, sc.keyword_id), 0.0)) >= 0.3:
                    nv = x.bid(o, sc.keyword_id, -1, "small", None)   # step back gently; the leader's raise takes the slot
                    r = _row(o, sc.keyword_id, "reduce_cpm", nv, it, f"yield {sc.city_id}/{sc.keyword_id} to {sc.sku_id}")
                    r["market_switch"] = True                # part of a switch: the leader's raise keeps the market
                    rows.append(r)
        else:
            nv = x.bid(me, sc.keyword_id, -1, it.size, None)
            rows.append(_row(me, sc.keyword_id, "reduce_cpm", nv, it, f"yield {sc.city_id}/{sc.keyword_id}"))
            held.add((me, sc.keyword_id, "bid"))
        return rows, held, "" if (rows or held) else "nothing to change"
    return [], set(), f"unsupported verb/scope {v}"


def _share_curve(allc: pd.DataFrame, x: _Ctx) -> pd.DataFrame:
    """The grid assumes slot 1 is already won at the live bid (X3.1), so it prices a raise on a cell that
    holds only part of slot 1 at zero. For intent raises in that case, price the missing share instead:
    share(bid) rises linearly from the observed 7-day slot-1 share to 1.0 at +SHARE_FULL_AT, and the
    gain is that extra share of the grid's slot-1 spend and revenue (scaled by budget absorption)."""
    if not len(allc):
        return allc
    allc = allc.copy()
    allc["priced_by"] = "grid"
    g1 = x.diag.grid[x.diag.grid.slot == 1].groupby(["campaign_id", "keyword_id"])[["spend_day", "revenue_day"]].sum()
    pacing = x.diag.pacing.set_index("campaign_id")
    m = (allc.source == "intent") & (allc.action_type == "increase_cpm") & (allc.pred_delta_spend <= 1)
    for idx, r in allc[m].iterrows():
        key = (r.campaign_id, r.keyword_id)
        s1 = float(x.s1.get(key, 0.0))
        if s1 >= 0.8 or key not in g1.index:
            continue
        pct = float(r.new_value) / float(x.live[key]) - 1
        new_share = min(1.0, s1 + (1 - s1) * max(pct, 0) / SHARE_FULL_AT)
        absorb = float(pacing.absorption.get(r.campaign_id, 1.0)) if bool(pacing.budget_bound.get(r.campaign_id, False)) else 1.0
        d = (new_share - s1) * absorb
        allc.loc[idx, ["pred_delta_spend", "pred_delta_rev", "priced_by"]] = [
            round(d * g1.loc[key, "spend_day"], 2), round(d * g1.loc[key, "revenue_day"], 2), "share_curve"]
    return allc


def compile_plan(obs: Observation, diag: Diagnostics, brief: Brief, iota: dict, plan: IntentPlan,
                 mode: str = "augment", l0: dict | None = None) -> CompileResult:
    assert mode in ("augment", "native")
    x = _Ctx(obs, diag, brief, iota)
    report, rejected = [], []
    by_lever: dict[tuple, dict] = {}
    held: set = set()
    n_pauses = 0
    for it in sorted(plan.intents, key=lambda i: -i.confidence):
        rows, h, why = _expand(it, x)
        held |= h
        rep = {"id": it.id, "verb": it.verb, "scope": it.scope.model_dump(exclude_none=True), "size": it.size,
               "rows": len(rows), "held": len(h), "kept": 0, "rejected": Counter()}
        if why:
            rep["rejected"][why] += 1
            rejected.append({"intent_id": it.id, "reason": why})
        for r in rows:
            if r["action_type"] in ("reduce_cpm", "pause_keyword", "reduce_budget") and not r.pop("market_switch", False):
                why_p = x.protected(r["campaign_id"], r["keyword_id"], r["action_type"])
                if why_p:
                    rep["rejected"][why_p] += 1
                    rejected.append({"intent_id": it.id, "cell": f"{r['campaign_id']}/{r['keyword_id']}", "reason": why_p})
                    continue
            r.pop("market_switch", None)
            lv = _lever(r["action_type"], r["campaign_id"], r["keyword_id"])
            if lv in by_lever:
                rep["rejected"]["conflict with a higher-confidence intent"] += 1
                continue
            if r["action_type"] == "pause_keyword":
                if n_pauses >= MAX_PAUSES_PER_RUN:
                    rep["rejected"][f"pause cap {MAX_PAUSES_PER_RUN}/run"] += 1
                    continue
                n_pauses += 1
            by_lever[lv] = r
        report.append(rep)
    intent_rows = pd.DataFrame(list(by_lever.values()), columns=ACTION_COLS + ["intent_id"])

    l0_rows = pd.DataFrame(columns=ACTION_COLS + ["iota"])
    overridden = l0_held = 0
    if mode == "augment" and l0:
        parts = [df for df in (l0.get("raises"), l0.get("cuts")) if df is not None and len(df)]
        if parts:
            l0_rows = pd.concat(parts, ignore_index=True)
            lv = [_lever(a, c, k) for a, c, k in zip(l0_rows.action_type, l0_rows.campaign_id, l0_rows.keyword_id.fillna(""))]
            in_intents = np.array([l in by_lever for l in lv])
            in_held = np.array([l in held for l in lv]) & ~in_intents
            overridden, l0_held = int(in_intents.sum()), int(in_held.sum())
            l0_rows = l0_rows[~(in_intents | in_held)]

    # precheck the intent rows (L0 rows were prechecked upstream)
    kept_i, dropped_i = filter_precheck(obs, diag.verdicts, diag.pacing, intent_rows) if len(intent_rows) else (intent_rows, intent_rows)
    for r in dropped_i.to_dict("records") if len(dropped_i) else []:
        rejected.append({"intent_id": r["intent_id"], "cell": f"{r['campaign_id']}/{r['keyword_id']}", "reason": r["precheck_reason"]})
        for rep in report:
            if rep["id"] == r["intent_id"]:
                rep["rejected"][r["precheck_reason"]] += 1

    kept_i = kept_i.copy()
    kept_i["iota"] = [x.cell_iota(c, k) if k else x.campaign_iota(c) for c, k in zip(kept_i.campaign_id, kept_i.keyword_id)] if len(kept_i) else []
    kept_i["source"] = "intent"
    l0_rows = l0_rows.copy()
    l0_rows["source"] = "l0"
    l0_rows["intent_id"] = ""
    allc = pd.concat([d for d in (kept_i, l0_rows) if len(d)], ignore_index=True) if (len(kept_i) or len(l0_rows)) else kept_i
    if not len(allc):
        return CompileResult(pd.DataFrame(columns=ACTION_COLS), report, rejected, overridden, l0_held, 0.0,
                             brief.headroom.allowance_inr_day)
    allc = allc.drop(columns=[c for c in ("pred_delta_spend", "pred_delta_rev") if c in allc.columns])
    allc = project_candidates(obs, diag.grid, diag.pacing, allc.reset_index(drop=True))

    allc = _share_curve(allc, x)
    inc = allc[allc.action_type.isin(INCREASES)].copy()
    dec = allc[~allc.action_type.isin(INCREASES)].copy()
    floor = max(brief.headroom.roas_floor, 1e-9)
    di = dec[dec.source == "intent"] if len(dec) else dec          # only intent cuts earn extra room; L0 alone stays L0
    freed = float(((di.pred_delta_rev - floor * di.pred_delta_spend) / floor).clip(lower=0).sum()) if len(di) else 0.0
    allowance = brief.headroom.allowance_inr_day + freed
    inc["_ratio"] = inc.iota * inc.pred_delta_rev / inc.pred_delta_spend.clip(lower=1e-9)
    inc = inc[(inc.pred_delta_spend > 1) & (inc._ratio > 0)] if len(inc) else inc
    picked, used = [], 0.0
    for src in ("intent", "l0"):
        for idx, r in inc[inc.source == src].sort_values("_ratio", ascending=False).iterrows():
            if used + r.pred_delta_spend <= allowance:
                picked.append(idx)
                used += r.pred_delta_spend
            elif src == "l0":
                break                                              # L0's own rule (select_raises): a prefix by ratio
            else:
                rejected.append({"intent_id": r.intent_id, "cell": f"{r.campaign_id}/{r.keyword_id}",
                                 "reason": f"over allowance (₹{allowance - used:.0f}/day left, needs ₹{r.pred_delta_spend:.0f})"})
    no_gain = allc[allc.action_type.isin(INCREASES) & (allc.source == "intent") & ~allc.index.isin(inc.index)]
    for r in no_gain.itertuples():
        rejected.append({"intent_id": r.intent_id, "cell": f"{r.campaign_id}/{r.keyword_id}", "reason": "no predicted gain from this raise"})
    final = pd.concat([inc.loc[picked], dec], ignore_index=True)
    for rep in report:
        rep["kept"] = int((final.intent_id == rep["id"]).sum()) if len(final) else 0
        rep["rejected"] = dict(rep["rejected"])
    out = final[ACTION_COLS].copy() if len(final) else pd.DataFrame(columns=ACTION_COLS)
    return CompileResult(out.reset_index(drop=True), report, rejected, overridden, l0_held, round(used, 2), round(allowance, 2))
