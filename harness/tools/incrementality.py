"""Incrementality: how many organic units an extra ad order displaces, by keyword type (E1).

`organic_units` lives in `sku_city_daily` (public/observed, never the hidden `truth`). We regress
it on same-day ad orders split by keyword type, with SKU x city and day-of-week fixed effects:

    organic_units[s,c,d] = FE(s,c) + FE(dow) + sum_t beta_t * ad_orders[s,c,d,t] + e

beta_t < 0 means ad orders of type t cannibalise organic sales. Incrementality ι_t = clip(1 + beta_t,
0, 1): the fraction of an ad order on type t that is *not* offset by a lost organic sale. A second
pass regresses per SKU (its own FE, same type regressors) and shrinks that SKU's beta toward the
pooled type beta with weight orders / (orders + SHRINK_ORDERS), the same shrinkage convention
`gpc.engine.grid`/`loop` use elsewhere in this codebase.

Deferred (not in this pass): using organic_rank (`keyword_sku.organic_rank`, public) as an
explicit prior on ι for thin SKUs (E8) — the type-level shrinkage above already pulls a thin SKU
toward its type's pooled beta, which is directional in the same way; a rank-specific prior can
sharpen SKUs we don't yet have a strong read on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gpc.observation import Observation

SHRINK_ORDERS = 25.0
MIN_DAYS_FOR_SKU_FIT = 14


def _panel(obs: Observation, window: int) -> tuple[pd.DataFrame, list[str]]:
    """Day-level panel: one row per (sku_id, city_id, day) with organic_units and one
    ad_orders_<type> column per keyword type."""
    f = obs.window("daily_facts", window)
    s = obs.window("sku_city_daily", window)
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    types = sorted(kt.unique())
    if len(f):
        f = f.assign(keyword_type=f.keyword_id.map(kt))
        wide = (f.groupby(["sku_id", "city_id", "day", "keyword_type"]).ad_orders.sum()
                 .unstack("keyword_type").reindex(columns=types).fillna(0.0))
        wide.columns = [f"ad_orders_{t}" for t in wide.columns]
        wide = wide.reset_index()
    else:
        wide = pd.DataFrame(columns=["sku_id", "city_id", "day"] + [f"ad_orders_{t}" for t in types])
    panel = s[["sku_id", "city_id", "day", "organic_units"]].merge(wide, on=["sku_id", "city_id", "day"], how="left")
    for t in types:
        panel[f"ad_orders_{t}"] = panel[f"ad_orders_{t}"].fillna(0.0)
    panel["dow"] = panel.day % 7
    panel["sku_city"] = panel.sku_id.astype(str) + "x" + panel.city_id.astype(str)
    return panel, types


def _fit_ols(panel: pd.DataFrame, types: list[str], fe_cols: list[str]) -> dict[str, float] | None:
    """lstsq fit with one-hot FE columns (first level of each dropped to avoid collinearity) plus
    the type ad_orders regressors. Returns {type: beta} or None if under-determined."""
    n = len(panel)
    if n < len(types) + 3:
        return None
    pieces = [np.ones((n, 1))]
    for col in fe_cols:
        levels = sorted(panel[col].unique())[1:]
        for lv in levels:
            pieces.append((panel[col] == lv).to_numpy(dtype=float).reshape(-1, 1))
    reg_cols = [f"ad_orders_{t}" for t in types]
    X = np.hstack(pieces + [panel[reg_cols].to_numpy(dtype=float)])
    y = panel.organic_units.to_numpy(dtype=float)
    if X.shape[0] <= X.shape[1]:
        return None
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return {t: float(coef[-len(types) + i]) for i, t in enumerate(types)}


def fit_type_incrementality(obs: Observation, window: int = 84) -> pd.DataFrame:
    """Pooled beta/iota per keyword type, across all SKUs and cities."""
    panel, types = _panel(obs, window)
    betas = _fit_ols(panel, types, fe_cols=["sku_city", "dow"]) if len(panel) else None
    rows = []
    for t in types:
        b = (betas or {}).get(t, 0.0)
        rows.append({"keyword_type": t, "beta": round(b, 4), "iota": round(float(np.clip(1 + b, 0.0, 1.0)), 4),
                     "n_obs": len(panel)})
    return pd.DataFrame(rows)


def fit_sku_incrementality(obs: Observation, window: int = 84) -> pd.DataFrame:
    """Per-SKU x type beta/iota, shrunk toward the pooled type beta by ad-order volume."""
    panel, types = _panel(obs, window)
    pooled = fit_type_incrementality(obs, window).set_index("keyword_type").beta.to_dict()
    rows = []
    for sku, g in panel.groupby("sku_id") if len(panel) else []:
        betas = _fit_ols(g, types, fe_cols=["city_id", "dow"]) if len(g) >= MIN_DAYS_FOR_SKU_FIT else None
        for t in types:
            orders = float(g[f"ad_orders_{t}"].sum())
            raw = (betas or {}).get(t, pooled.get(t, 0.0))
            w = orders / (orders + SHRINK_ORDERS)
            beta = w * raw + (1 - w) * pooled.get(t, 0.0)
            rows.append({"sku_id": sku, "keyword_type": t, "beta": round(beta, 4),
                         "iota": round(float(np.clip(1 + beta, 0.0, 1.0)), 4),
                         "orders": round(orders, 1), "weight_on_own_fit": round(w, 3)})
    cols = ["sku_id", "keyword_type", "beta", "iota", "orders", "weight_on_own_fit"]
    return pd.DataFrame(rows, columns=cols)


def iota_lookup(obs: Observation, window: int = 84) -> dict[tuple[str, str], float]:
    """(sku_id, keyword_type) -> ι, for use by sizing. Falls back to the pooled type ι for a
    SKU x type with no data."""
    sku_df = fit_sku_incrementality(obs, window)
    pooled = fit_type_incrementality(obs, window).set_index("keyword_type").iota.to_dict()
    out = {(r.sku_id, r.keyword_type): r.iota for r in sku_df.itertuples()}
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    for sku in obs.public["products"].sku_id:
        for t in pooled:
            out.setdefault((sku, t), pooled[t])
    return out
