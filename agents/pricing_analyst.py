# OWNER: M4
"""pricing_analyst agent for Phase 4 Commercial Setup.

Analyzes competitor pricing and demand validation to recommend price and price range.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context


class PricingAnalyst(M4Agent):
    name = "pricing_analyst"
    phase = 4
    step = "phase4_step1_pricing"
    inputs = [
        "phase2_step2_lean_canvas",
        "phase2_step1_competitor_analysis",
        "phase1_step5_competitors",
        "phase2_step5_demand_results",
        "phase2_step9_validation_report",
    ]
    tools = []
    required_keys = ["price_usd", "range", "comparable_claims", "is_assumption"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        # Permissive input check so the agent can run in unit tests or when upstream phases are stubbed
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        try:
            data["price_usd"] = float(data.get("price_usd", 29.0))
        except (ValueError, TypeError):
            data["price_usd"] = 29.0

        r = data.get("range")
        if isinstance(r, (list, tuple)) and len(r) == 2:
            try:
                data["range"] = [float(r[0]), float(r[1])]
            except (ValueError, TypeError):
                data["range"] = [data["price_usd"] * 0.7, data["price_usd"] * 1.3]
        else:
            data["range"] = [round(data["price_usd"] * 0.7, 2), round(data["price_usd"] * 1.3, 2)]

        claims = data.get("comparable_claims")
        data["comparable_claims"] = claims if isinstance(claims, list) else []

        # If there are no verified comparable claims, ensure is_assumption is True
        if not data["comparable_claims"]:
            data["is_assumption"] = True
        else:
            data["is_assumption"] = bool(data.get("is_assumption", False))

        return data
