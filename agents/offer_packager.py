# OWNER: M4
"""offer_packager agent for Phase 4 Commercial Setup.

Structures honest tiers and positioning without income promises.
"""
from __future__ import annotations

from agents.m4_common import M4Agent, price_from_pricing, to_float
from core.contracts import Context


class OfferPackager(M4Agent):
    name = "offer_packager"
    phase = 4
    step = "phase4_step2_offer"
    inputs = ["phase4_step1_pricing"]
    tools = []
    required_keys = ["tiers", "positioning"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        default_price = price_from_pricing(ctx)
        raw_tiers = data.get("tiers")
        clean_tiers = []
        if isinstance(raw_tiers, list):
            for t in raw_tiers:
                if isinstance(t, dict):
                    inc = t.get("includes", [])
                    clean_tiers.append({
                        "name": str(t.get("name", "Standard")),
                        "price_usd": to_float(t.get("price_usd"), default_price),
                        "includes": [str(i) for i in inc] if isinstance(inc, list) else [str(inc)],
                    })
        if not clean_tiers:
            clean_tiers = [{
                "name": "Standard",
                "price_usd": default_price,
                "includes": ["STUBBED: the model returned no tier contents; the founder fills this in."],
            }]
            data["stubbed"] = "Tiers filled by a code fallback."
        data["tiers"] = clean_tiers
        data["positioning"] = str(data.get("positioning") or "STUBBED: no positioning was generated.")
        return data
