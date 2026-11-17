"""feasibility_analyst: effort for the minimum viable scope (from what rivals offer) vs the founder's hours
and budget; one rating."""
import re

from agents.base import Agent
from agents.m2_common import CLARIFICATION, COMPETITORS, FEASIBILITY, IDEA_CARD, founder_time, message, norm_rating


TOTAL_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*hours?\s*(?:in\s*)?total|total(?:ing|\s*of)?\s*(\d+(?:\.\d+)?)\s*hours?", re.I)


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
        return message(ctx, self.inputs + self.optional_inputs, {"founder_time": founder_time(ctx.brief)},
                       compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        data = norm_rating(data)
        t = founder_time(getattr(ctx, "brief", "")) or {}
        stated = [float(a or b) for a, b in TOTAL_HOURS.findall(str(data.get("reasoning", "")))]
        if t.get("total_hours") and any(abs(x - t["total_hours"]) > 0.15 * t["total_hours"] for x in stated):
            # qwen3:8b computed "8 hours per week for 3 months" as 24 hours. A rating built on wrong
            # arithmetic is not evidence: it becomes unknown (never upgraded).
            data["rating_before_check"], data["rating"] = data.get("rating"), "unknown"
            data["arithmetic_error"] = (f"reasoning states {stated} total hours; the brief gives "
                                        f"{t['total_hours']} ({t['hours_per_week']:g} h/week x {t['weeks']} weeks)")
        e = data.get("effort_hours_estimate")
        if isinstance(e, str) and e.strip().replace(".", "", 1).isdigit():
            e = float(e)
        data["effort_hours_estimate"] = e if isinstance(e, (int, float)) and not isinstance(e, bool) and e > 0 \
            else "unknown"
        if not ctx.store.has(COMPETITORS):
            data["limitation"] = "No competitor scan was available, so the minimum scope is an ASSUMPTION."
        return data
