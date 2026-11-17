"""opportunity_scorer: score the founder's idea and each alternative (0-10) on need, market, fit and effort,
using all Phase 1 evidence. The ranking is kept as pivot targets. ``chosen`` is the idea being validated (the
founder's); ``switch_suggested`` says when an alternative scores clearly higher."""
from agents.base import Agent
from agents.m2_common import (COMPETITORS, DEMAND, FEASIBILITY, FOUNDER_FIT, IDEA_CARD, INTERVIEWS, MARKET,
                              OPPORTUNITIES, SCORES, as_list, message)


class OpportunityScorer(Agent):
    name = "opportunity_scorer"
    phase = 1
    step = SCORES
    inputs = [IDEA_CARD]
    optional_inputs = [OPPORTUNITIES, MARKET, DEMAND, COMPETITORS, FOUNDER_FIT, FEASIBILITY, INTERVIEWS]
    tools: list = []
    required_keys = ["ranked", "chosen"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs + self.optional_inputs, brief=False, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        ranked = []
        for r in as_list(data.get("ranked")):
            if not isinstance(r, dict) or not str(r.get("name", "")).strip():
                continue
            try:
                s = float(r.get("score"))
            except (TypeError, ValueError):
                s = 0.0
            r["score"] = max(0.0, min(10.0, s))
            r["reasons"] = [str(x) for x in as_list(r.get("reasons"))]
            r["is_founder_idea"] = r.get("is_founder_idea") is True
            ranked.append(r)
        ranked.sort(key=lambda r: -r["score"])
        data["ranked"] = ranked
        names = [r["name"] for r in ranked]
        own = next((r for r in ranked if r["is_founder_idea"]), None)
        chosen = own["name"] if own else (data.get("chosen") if data.get("chosen") in names else
                                          (names[0] if names else None))
        data["chosen"] = chosen
        top = ranked[0] if ranked else None
        chosen_score = next((r["score"] for r in ranked if r["name"] == chosen), None)
        data["top_scored"] = top["name"] if top else None
        data["switch_suggested"] = bool(top and chosen_score is not None and top["score"] - chosen_score >= 2)
        return data
