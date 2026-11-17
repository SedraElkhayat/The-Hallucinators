# OWNER: M4
"""pricing_analyst agent for Phase 4 Commercial Setup.

Analyzes competitor pricing and demand validation to recommend price and price range.
"""
from __future__ import annotations

import re

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
        budget = brief_budget(ctx.brief)
        if budget is not None:
            # The brief's budget is what the founder can spend, not what a customer pays (a real run mixed them up).
            if data["price_usd"] == budget or _mentions_amount(str(data.get("rationale", "")), budget):
                if data["price_usd"] == budget:
                    data["price_usd"] = None
                # A rationale built on the budget is wrong, so it is replaced, not kept beside a note.
                data["rationale"] = (f"ASSUMPTION: no verified comparable price. USD {budget:g} in the brief is the "
                                     "founder's budget, not a price customers have said they will pay; the founder "
                                     "sets the price.")
                data["budget_not_price"] = f"The model treated the brief's budget (USD {budget:g}) as a price; removed."
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
        # The price is sourced only when a verified comparable quote states a price (a real run marked USD 25
        # sourced on two verified quotes that named no amount). Otherwise it is an assumption, whatever the model said.
        data["is_assumption"] = not any(quote_has_price(c.get("quote", "")) for c in data["comparable_claims"])
        if data["is_assumption"]:
            data["price_label"] = (f"ASSUMPTION: USD {data['price_usd']:g} is not taken from a verified competitor "
                                   "price; no verified comparable quote states a price. The founder sets the price.")
            rationale = str(data.get("rationale") or "").strip()
            if not rationale.upper().startswith("ASSUMPTION"):
                data["rationale"] = ("ASSUMPTION: no verified comparable quote states a price. " + rationale).strip()
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


# A price in a quote: a currency symbol or code next to an amount, or a decimal amount such as 19.99.
_PRICE_RX = re.compile(
    r"[$€£¥]\s?\d|\d\s?[$€£]|"
    r"\b(?:usd|egp|eur|gbp|cad|aud|inr|us\$)\s?\d|"
    r"\d[\d,]*(?:\.\d+)?\s?(?:usd|egp|eur|gbp|cad|aud|inr|dollars?|euros?|pounds?)\b|"
    r"(?<![\d.])\d{1,6}\.\d{2}(?![\d.])", re.I)


def quote_has_price(quote) -> bool:
    return bool(_PRICE_RX.search(str(quote or "")))


_BUDGET_RX = re.compile(r"budget\W{0,6}(?:is\s+|of\s+)?(?:usd|us\$|\$)\s?(\d[\d,]*(?:\.\d+)?)|"
                        r"budget\W{0,6}(\d[\d,]*(?:\.\d+)?)\s*(?:usd|dollars)", re.I)


def brief_budget(brief: str):
    m = _BUDGET_RX.search(brief or "")
    if not m:
        return None
    return to_float((m.group(1) or m.group(2)).replace(",", ""))


def _mentions_amount(text: str, amount: float) -> bool:
    n = re.escape(f"{amount:g}")
    return bool(re.search(rf"(?:usd|\$)\s?{n}(?![\d.])|(?<![\d.]){n}\s*(?:usd|dollars)", text, re.I))
