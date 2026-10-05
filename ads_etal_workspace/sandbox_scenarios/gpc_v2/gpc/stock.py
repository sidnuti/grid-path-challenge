"""Module C (sim v2): finite stock for ephemeral SKUs (S6 gift pack).

Design: `design/02_simulator_v2_design.md` §4.2. Each unit sold (ad or organic) depletes city stock. At
zero, availability (OSA) is 0, so the SKU's ads stop serving through the existing OSA gating. Units still
on hand when the SKU's live window ends are salvaged at `salvage_frac` × ASP (the scorer counts that
value). State lives on the Market instance, so the policy run and the ads-off run each keep their own.
"""
from __future__ import annotations


class Stock:
    def __init__(self, ephemeral_skus: list[dict]):
        self.spec = {s["id"]: s for s in ephemeral_skus}
        self.left = {(s["id"], c): float(q) for s in ephemeral_skus for c, q in s["stock_by_city"].items()}

    def tracks(self, sku: str) -> bool:
        return sku in self.spec

    def available(self, sku: str, city: str) -> bool:
        return self.left.get((sku, city), 1.0) > 0

    def fulfil(self, sku: str, city: str, ad_units: int, organic_units: int) -> tuple[int, int, float, float]:
        """Cap sales at stock (ad orders are filled first: they were paid for). Returns
        (ad filled, organic filled, stock before, stock after)."""
        before = self.left[(sku, city)]
        ad = int(min(ad_units, before))
        org = int(min(organic_units, before - ad))
        self.left[(sku, city)] = before - ad - org
        return ad, org, before, self.left[(sku, city)]
