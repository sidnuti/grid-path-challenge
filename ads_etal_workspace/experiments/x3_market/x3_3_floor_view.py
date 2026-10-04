"""X3.3 floor view: the marginal direct ROAS of each action type (true within-week Δad revenue / Δspend) set
against the portfolio's ROAS floor. Spend removed below the floor *raises* portfolio ROAS (buys margin);
spend added below the floor dilutes it. Reads `results/x3_3_action_effects.csv` (no simulation).

    PYTHONPATH=grid-path-challenge:. python -m experiments.x3_market.x3_3_floor_view
"""

from __future__ import annotations

import pandas as pd

from experiments.lib.report import RESULTS, md_table, save
from experiments.lib.runs import load_latest
from gpc.score import summarize


def main():
    d = pd.read_csv(RESULTS / "x3_3_action_effects.csv")
    floors = [summarize(load_latest("l0", s)[0])["roas_floor"] for s in sorted(d.seed.unique())]
    floor = sum(floors) / len(floors)
    g = d.groupby("action_type").agg(n=("seed", "count"), d_spend=("true_dspend", "sum"), d_ad_rev=("true_drev", "sum"),
                                     d_offtake=("true_dofftake", "sum")).reset_index()
    g["marginal_droas"] = g.d_ad_rev / g.d_spend
    g["vs_floor"] = g.marginal_droas - floor
    g["effect_on_portfolio_roas"] = ["raises" if (sp < 0 and m < floor) or (sp > 0 and m > floor) else "dilutes"
                                     for sp, m in zip(g.d_spend, g.marginal_droas)]
    md = (f"## X3.3 floor view (mean ROAS floor of the {len(floors)} seeds = {floor:.2f})\n\n"
          "Marginal direct ROAS of each action type, within-week, vs the floor.\n\n" + md_table(g, "{:,.2f}"))
    print(md)
    save("x3_3_floor_view", {"floor": floor, "rows": g.to_dict("records")}, md)
    (RESULTS / "x3_3_floor_view.md").write_text(md)


if __name__ == "__main__":
    main()
