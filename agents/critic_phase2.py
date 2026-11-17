"""critic_phase2: reviews the validation report; must_fix for unsupported facts or flattery."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P2_CRITIQUE, P2_REPORT, P2_RESULTS, P2_RISKS, P2_SCORECARD,
                              normalize_verdict)


class CriticPhase2(M3InputsMixin, Agent):
    name = "critic_phase2"
    phase = 2
    step = P2_CRITIQUE
    inputs = [P2_REPORT]
    optional_inputs = [P2_RESULTS, P2_RISKS, P2_SCORECARD]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        # The critic reviews the report itself; it does not need the previous critique.
        from agents.m3_common import inputs_message
        return inputs_message(ctx, list(self.inputs) + list(self.optional_inputs))

    def post_process(self, ctx, data: dict) -> dict:
        return normalize_verdict(data)
