"""skeptic: challenge the ranking and the leading option: risks, kill criteria, what would change the verdict.
A kill criterion counts as triggered only when it names the evidence that meets it (checked in code)."""
from agents.base import Agent
from agents.m2_common import (COMPETITORS, DEMAND, FEASIBILITY, FOUNDER_FIT, IDEA_CARD, INTERVIEWS, MARKET,
                              OPPORTUNITIES, SCOPE, SCORES, SKEPTIC, message, norm_risks)


class Skeptic(Agent):
    name = "skeptic"
    phase = 1
    step = SKEPTIC
    inputs = [SCORES]
    optional_inputs = [IDEA_CARD, SCOPE, OPPORTUNITIES, MARKET, DEMAND, COMPETITORS, FOUNDER_FIT, FEASIBILITY,
                       INTERVIEWS]
    tools: list = []
    required_keys = ["risks", "kill_criteria", "would_change_mind"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs + self.optional_inputs, brief=False, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        return norm_risks(data)
