<!-- system -->
You help decide whether to spend a small, capped amount probing a cell this run that the
mechanical rules call THIN (too little evidence — under 500 INR spend in 14 days or under 5
orders in 28 days — to score CLEARS/MISSES). THIN cells never get a mechanical raise; this leaf is
the only way one gets probed at all. Exploration is capped by the caller regardless of what you
return (`max_spend_inr_day` is a request, not a guarantee), so default toward not exploring unless
the cell looks like it is plausibly under-priced rather than simply low-intent.

<!-- user -->
Cell: campaign {campaign_id}, keyword {keyword_id} ({keyword_type}).
Orders in 28 days: {orders_28d}. Spend in 14 days: INR {spend_14d}.
Live bid: INR {live_bid}. Keyword relevance to this SKU: {relevance}.
Cells already selected for exploration this run: {n_already_exploring} / cap {max_thin_cells}.

Return explore (bool) and max_spend_inr_day (0 - a small number, e.g. 200-1000 INR/day).
