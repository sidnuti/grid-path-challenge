"""What a policy is allowed to see at decision time."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .world import START_DATE


@dataclass
class Observation:
    run: int                              # 1-based run number
    day: int                              # day index the actions take effect from
    public: dict[str, pd.DataFrame]       # base tables + the plan (never the market's truth)
    campaigns: pd.DataFrame               # current budgets + daypart schedule
    campaign_keywords: pd.DataFrame       # current bids + active flags
    daily_facts: pd.DataFrame             # campaign × keyword × daypart × day, all days < `day`
    campaign_daily: pd.DataFrame          # campaign pacing, all days < `day`
    sku_city_daily: pd.DataFrame          # SKU × city offtake (ad + organic), all days < `day`
    roas_floor: float                     # portfolio direct ROAS to hold (warm-up level − 2%)
    warmup_droas: float                   # portfolio direct ROAS over the 28-day warm-up
    extra: dict = field(default_factory=dict)   # sim v2 public tables (pub_stock_daily, category_share_weekly, …), days < `day`

    @property
    def date(self) -> date:
        return START_DATE + timedelta(days=self.day)

    def window(self, frame: str, days: int) -> pd.DataFrame:
        df = getattr(self, frame)
        return df[df.day >= self.day - days]
