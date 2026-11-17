"""assumption_auditor: every assumption, whether it was tested, and the cheapest test."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_IDEA_CARD, P1_REPORT, P2_ASSUMPTIONS, P2_CANVAS,
                              P2_COMPETITOR_ANALYSIS, P2_PLAN, P2_RESULTS, get_artifact)


class AssumptionAuditor(M3InputsMixin, Agent):
    name = "assumption_auditor"
    phase = 2
    step = P2_ASSUMPTIONS
    inputs = [P2_CANVAS, P2_PLAN, P2_RESULTS, P2_COMPETITOR_ANALYSIS]
    optional_inputs = [P1_REPORT, P1_IDEA_CARD]
    tools = []
    required_keys = ["assumptions", "untested_high_impact_count"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        results = get_artifact(ctx, P2_RESULTS) or {}
        mocked = results.get("provenance") != "REAL"
        cleaned = []
        for n, a in enumerate(data.get("assumptions") or [], 1):
            if isinstance(a, str):
                a = {"text": a}
            if not isinstance(a, dict) or not a.get("text"):
                continue
            a.setdefault("id", f"A{n}")
            a["tested"] = a.get("tested") is True
            # A MOCKED demand result tests nothing.
            if mocked and "demand_results" in str(a.get("source", "")):
                a["tested"] = False
            impact = str(a.get("impact", "high")).lower()
            a["impact"] = impact if impact in ("high", "medium", "low") else "high"
            a.setdefault("cheapest_test", "unknown")
            cleaned.append(a)
        data["assumptions"] = cleaned
        # Counted in code, not trusted from the model.
        data["untested_high_impact_count"] = sum(1 for a in cleaned if not a["tested"] and a["impact"] == "high")
        return data
