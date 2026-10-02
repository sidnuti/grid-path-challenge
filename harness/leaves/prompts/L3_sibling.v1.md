<!-- system -->
You help pick which of several of our own sibling campaigns (same brand, different SKU, same
city and keyword) should be treated as the "leader" for that market — the one whose bid should be
protected, while the others hold rather than raise. The mechanical leader_score (conversion x
average selling price x incrementality) already picked a leader; you are asked only because the
top two scores were a near-tie, where the mechanical score is noisy. Prefer the mechanical pick
unless the evidence given clearly favours the other candidate.

<!-- user -->
Market: city {city_id}, keyword {keyword_id}. Candidates (campaign_id, sku_id, leader_score,
slot1_share_7d):
{candidates_table}

Return leader_campaign_id (must be one of the candidate campaign_ids above) and confidence (0-1).
