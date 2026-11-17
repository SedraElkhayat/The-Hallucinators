# OWNER: M4
"""offer_packager agent for Phase 4 Commercial Setup.

Structures honest tiers and positioning without income promises.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
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
        raw_tiers = data.get("tiers")
        clean_tiers = []
        if isinstance(raw_tiers, list):
            for t in raw_tiers:
                if isinstance(t, dict):
                    clean_tiers.append({
                        "name": str(t.get("name", "Standard Tier")),
                        "price_usd": float(t.get("price_usd", 29.0)),
                        "includes": list(t.get("includes", [])) if isinstance(t.get("includes"), list) else [str(t.get("includes", ""))],
                    })
        if not clean_tiers:
            clean_tiers = [{
                "name": "Standard Tier",
                "price_usd": 29.0,
                "includes": ["Digital template pack", "Quickstart documentation"],
            }]
        data["tiers"] = clean_tiers
        data["positioning"] = str(data.get("positioning", "Streamlined workflow toolkit for freelance designers."))
        return data
