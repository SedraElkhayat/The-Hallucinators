"""feasibility_analyst: effort for the minimum viable scope (from what rivals offer) vs the founder's hours
and budget; one rating."""
from agents.base import Agent
from agents.m2_common import CLARIFICATION, COMPETITORS, FEASIBILITY, IDEA_CARD, message, norm_rating


class FeasibilityAnalyst(Agent):
    name = "feasibility_analyst"
    phase = 1
    step = FEASIBILITY
    inputs = [IDEA_CARD, CLARIFICATION]
    optional_inputs = [COMPETITORS]
    tools: list = []
    required_keys = ["rating", "reasoning", "evidence_refs", "effort_hours_estimate"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs + self.optional_inputs)

    def post_process(self, ctx, data: dict) -> dict:
        data = norm_rating(data)
        e = data.get("effort_hours_estimate")
        if isinstance(e, str) and e.strip().replace(".", "", 1).isdigit():
            e = float(e)
        data["effort_hours_estimate"] = e if isinstance(e, (int, float)) and not isinstance(e, bool) and e > 0 \
            else "unknown"
        if not ctx.store.has(COMPETITORS):
            data["limitation"] = "No competitor scan was available, so the minimum scope is an ASSUMPTION."
        return data
