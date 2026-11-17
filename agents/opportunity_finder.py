"""opportunity_finder: alternative ideas in the same space, with sourced claims (pivot targets)."""
from agents.m2_common import CLARIFICATION, OPPORTUNITIES, ResearchAgent, as_list, topic_queries


class OpportunityFinder(ResearchAgent):
    name = "opportunity_finder"
    phase = 1
    step = OPPORTUNITIES
    optional_inputs = [CLARIFICATION]
    required_keys = ["alternatives", "claims", "insufficient_evidence"]

    def queries(self, ctx, card):
        t = topic_queries(card)
        return [f"{t['cust']} {t['prob']}", f"{t['cust']} tools {t['prob']}", f"{t['prod']} {t['cust']}"]

    def post_process(self, ctx, data):
        data = super().post_process(ctx, data)
        alts = []
        for a in as_list(data.get("alternatives")):
            if isinstance(a, str):
                a = {"name": a, "why": "unknown"}
            if isinstance(a, dict) and str(a.get("name", "")).strip():
                a.setdefault("why", "unknown")
                alts.append(a)
        data["alternatives"] = alts[:5]
        return data
