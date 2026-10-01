"""A deliberately naive policy, to show the guardrail layer at work.

Every run it raises every bid by 30% and every budget by 40%. Most of that is blocked or trimmed:
bids already at slot 1 (G3), budgets that never run out (G5), cells missing goal (G7), and the
portfolio ROAS floor (G8). Read runs/…/guardrail_log.csv after running it.

    python -m gpc.runner --policy examples.naive_scaler:NaiveScaler
"""

import pandas as pd

from gpc.observation import Observation
from gpc.policy import Policy


class NaiveScaler(Policy):
    name = "naive_scaler"

    def recommend(self, obs: Observation) -> pd.DataFrame:
        rows = []
        for r in obs.campaign_keywords[obs.campaign_keywords.active].itertuples():
            rows.append({"campaign_id": r.campaign_id, "keyword_id": r.keyword_id, "action_type": "increase_cpm",
                         "new_value": r.bid_cpm_inr * 1.30, "reason": "scale everything"})
        for c in obs.campaigns.itertuples():
            rows.append({"campaign_id": c.campaign_id, "keyword_id": "", "action_type": "increase_budget",
                         "new_value": c.daily_budget_inr * 1.40, "reason": "scale everything"})
        self.last_trace = None
        return pd.DataFrame(rows)
