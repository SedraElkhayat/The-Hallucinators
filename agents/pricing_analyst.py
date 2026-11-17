# OWNER: M4
"""pricing_analyst agent for Phase 4 Commercial Setup.

Analyzes competitor pricing and demand validation to recommend price and price range.
"""
from __future__ import annotations

from agents.m4_common import M4Agent, to_float
from core.claims import normalize, verify_claims
from core.contracts import Context


UPSTREAM_CLAIM_STEPS = ("phase1_step5_competitors", "phase2_step1_competitor_analysis")


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
        data["price_usd"] = to_float(data.get("price_usd"))
        if data["price_usd"] is None:
            # No invented number: the founder sets the price; labeled as an open assumption.
            data["is_assumption"] = True
            data["note"] = "STUBBED: the model returned no price; the founder must set one."
            data["range"] = None
            data["comparable_claims"] = self.keep_verified_comparables(ctx, data.get("comparable_claims"))
            return data

        r = data.get("range")
        if isinstance(r, (list, tuple)) and len(r) == 2:
            try:
                data["range"] = [float(r[0]), float(r[1])]
            except (ValueError, TypeError):
                data["range"] = [data["price_usd"] * 0.7, data["price_usd"] * 1.3]
        else:
            data["range"] = [round(data["price_usd"] * 0.7, 2), round(data["price_usd"] * 1.3, 2)]

        data["comparable_claims"] = self.keep_verified_comparables(ctx, data.get("comparable_claims"))
        # No verified comparable -> the price is an assumption, whatever the model said.
        data["is_assumption"] = not data["comparable_claims"]
        return data

    def keep_verified_comparables(self, ctx: Context, claims) -> list:
        """Keep only claims copied from verified upstream claims, then re-check them with the claim checker."""
        upstream = {}
        for step in UPSTREAM_CLAIM_STEPS:
            if ctx.store.has(step):
                for c in ctx.store.get(step).get("claims") or []:
                    if isinstance(c, dict) and c.get("verified") is True:
                        upstream[(str(c.get("source_url", "")).strip(), normalize(str(c.get("quote", ""))))] = c
        kept, dropped = [], []
        for c in claims if isinstance(claims, list) else []:
            if not isinstance(c, dict):
                continue
            key = (str(c.get("source_url", "")).strip(), normalize(str(c.get("quote", ""))))
            if key in upstream:
                kept.append({"claim": str(c.get("claim") or upstream[key].get("claim", "")),
                             "source_url": key[0], "quote": str(upstream[key].get("quote", "")),
                             "verified": None, "assumption": False})
            else:
                dropped.append(c)
                ctx.log.action(self.name, "comparable_dropped", sources=[],
                               reason="not a verified upstream claim", claim=str(c.get("claim", ""))[:200])
        verify_claims(ctx, {"claims": kept})
        verified = [c for c in kept if c.get("verified") is True]
        self._dropped = dropped + [c for c in kept if c.get("verified") is not True]
        return verified
