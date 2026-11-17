"""founder_fit: compare the idea with the founder's skills, time, budget and values; one rating."""
from agents.base import Agent
from agents.m2_common import CLARIFICATION, FOUNDER_FIT, IDEA_CARD, message, norm_rating


class FounderFit(Agent):
    name = "founder_fit"
    phase = 1
    step = FOUNDER_FIT
    inputs = [IDEA_CARD, CLARIFICATION]
    tools: list = []
    required_keys = ["rating", "reasoning", "evidence_refs"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        return norm_rating(data)
