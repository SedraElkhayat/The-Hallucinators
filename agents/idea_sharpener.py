"""idea_sharpener: restate the chosen idea as an Idea Card (customer, problem, solution, value proposition)
with testable hypotheses. After a pivot it reads ``pivot_notes`` and builds the card around the next-best
alternative."""
from agents.base import Agent
from agents.m2_common import (CLARIFICATION, IDEA_CARD, IDEA_CHOICE, OPTIONS, PIVOT_NOTES, as_list, message)


class IdeaSharpener(Agent):
    name = "idea_sharpener"
    phase = 1
    step = IDEA_CARD
    inputs = [CLARIFICATION]
    optional_inputs = [OPTIONS, IDEA_CHOICE, PIVOT_NOTES]
    tools: list = []
    required_keys = ["customer", "problem", "solution", "value_proposition", "hypotheses"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        extra = {"critique": ctx.extra.get("critique")} if ctx.extra.get("critique") else {}
        return message(ctx, self.inputs + self.optional_inputs, extra)

    def post_process(self, ctx, data: dict) -> dict:
        hyps = []
        for i, h in enumerate(as_list(data.get("hypotheses")), 1):
            if isinstance(h, str):
                h = {"text": h, "test": "unknown"}
            if isinstance(h, dict) and str(h.get("text", "")).strip():
                h["id"] = str(h.get("id") or f"H{i}")
                h.setdefault("test", "unknown")
                hyps.append(h)
        data["hypotheses"] = hyps
        for k in ("customer", "problem", "solution", "value_proposition"):
            data[k] = str(data.get(k) or "unknown")
        if ctx.store.has(PIVOT_NOTES):
            data["pivoted"] = True
        return data
