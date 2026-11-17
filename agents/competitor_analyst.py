"""competitor_analyst: deep analysis of Phase 1's verified competitor evidence; no new claims."""
import re

from agents.base import Agent
from agents.m2_common import founder_budget
from agents.m3_common import (M3InputsMixin, P1_COMPETITORS, P1_DEMAND_SIGNALS, P1_IDEA_CARD,
                              P1_MARKET, P2_COMPETITOR_ANALYSIS, get_artifact)

_FORCES = ("rivalry", "new_entrants", "substitutes", "buyer_power", "supplier_power")


def _budget_rx(brief: str):
    """Pattern for the brief's budget written as money ("USD 100", "$100", "100 dollars"), or None."""
    b = founder_budget(brief or "")
    if not b:
        return None
    amt = re.escape(str(b["amount"]).replace(",", ""))
    return re.compile(rf"(?:usd|us\$|\$)\s?{amt}(?![\d.])|(?<![\d.]){amt}\s?(?:usd|dollars|\$)", re.I)


def remove_budget_as_price(brief: str, data: dict) -> dict:
    """The brief's budget is what the founder can spend, not a price or what customers will pay (a real run
    used "USD 100" as willingness to pay). Pricing gaps built on it are dropped; force and differentiation
    reasons built on it become unknown. Everything removed is recorded in ``budget_not_price``."""
    rx = _budget_rx(brief)
    if rx is None:
        return data
    removed = []
    gaps = []
    for g in data.get("pricing_gaps") or []:
        (removed if rx.search(str(g)) else gaps).append(g)
    data["pricing_gaps"] = gaps
    forces = data.get("five_forces") if isinstance(data.get("five_forces"), dict) else {}
    for name, v in forces.items():
        if isinstance(v, dict) and rx.search(str(v.get("reason", ""))):
            removed.append(f"{name}: {v.get('reason')}")
            forces[name] = {"level": "unknown", "reason": "ASSUMPTION: no evidence; the brief's budget is not a price."}
    if rx.search(str(data.get("differentiation_reason", ""))):
        removed.append(f"differentiation_reason: {data.get('differentiation_reason')}")
        data["differentiation_reason"] = "ASSUMPTION: no evidence; the brief's budget is not a price."
    if removed:
        data["budget_not_price"] = removed
    return data


class CompetitorAnalyst(M3InputsMixin, Agent):
    name = "competitor_analyst"
    phase = 2
    step = P2_COMPETITOR_ANALYSIS
    inputs = [P1_IDEA_CARD, P1_COMPETITORS, P1_MARKET, P1_DEMAND_SIGNALS]
    tools = []
    required_keys = ["positioning", "pricing_gaps", "five_forces", "differentiation_possible", "claim_refs"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        """Keep only claim references that match a Phase 1 claim (by text or source URL) and normalize the
        yes/no/unknown fields."""
        # Index the Phase 1 claims; only refs that match an existing claim are kept.
        known = []
        for stem in (P1_COMPETITORS, P1_MARKET, P1_DEMAND_SIGNALS):
            for c in (get_artifact(ctx, stem) or {}).get("claims") or []:
                if isinstance(c, dict) and c.get("claim"):
                    known.append(c)
        by_text = {str(c["claim"]).strip().lower(): c for c in known}
        by_url = {}
        for c in known:
            by_url.setdefault(str(c.get("source_url", "")).strip(), c)

        kept, matched, dropped = [], [], []
        for ref in data.get("claim_refs") or []:
            if isinstance(ref, str):
                ref = {"claim": ref, "source_url": ""}
            if not isinstance(ref, dict):
                continue
            c = by_text.get(str(ref.get("claim", "")).strip().lower()) or by_url.get(str(ref.get("source_url", "")).strip())
            if c is None:
                dropped.append(ref)
                continue
            kept.append({"claim": c["claim"], "source_url": c.get("source_url", "")})
            if c not in matched:
                matched.append(c)
        data["claim_refs"] = kept
        if dropped:
            data["dropped_claim_refs"] = dropped
        # "claims" re-cites the matched Phase 1 claims verbatim (no new claims are added).
        data["claims"] = [dict(c) for c in matched]
        verified = [c for c in matched if c.get("verified") is True]
        data["insufficient_evidence"] = len(verified) < 2

        forces = data.get("five_forces") if isinstance(data.get("five_forces"), dict) else {}
        for f in _FORCES:
            v = forces.get(f)
            if not isinstance(v, dict):
                v = {"level": "unknown", "reason": str(v) if v else "no evidence ASSUMPTION"}
            if v.get("level") not in ("low", "medium", "high", "unknown"):
                v["level"] = "unknown"
            forces[f] = v
        data["five_forces"] = forces
        remove_budget_as_price(getattr(ctx, "brief", "") or "", data)
        dp = str(data.get("differentiation_possible", "unknown")).lower()
        data["differentiation_possible"] = {"true": "yes", "false": "no"}.get(dp, dp if dp in ("yes", "no", "unknown") else "unknown")
        if not kept:
            data["differentiation_possible"] = "unknown"
        return data
