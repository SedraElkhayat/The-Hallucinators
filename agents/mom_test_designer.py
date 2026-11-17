"""mom_test_designer: interview script about the customer's past behaviour, not about the idea."""
from agents.base import Agent
from agents.m2_common import IDEA_CARD, INTERVIEW_SCRIPT, as_list, message

PITCH_WORDS = ("would you buy", "would you pay", "would you use", "do you like", "is this a good idea",
               "what do you think of my", "would you be interested")


class MomTestDesigner(Agent):
    name = "mom_test_designer"
    phase = 1
    step = INTERVIEW_SCRIPT
    inputs = [IDEA_CARD]
    tools: list = []
    required_keys = ["questions", "rules", "avoid_list"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs, brief=False)

    def post_process(self, ctx, data: dict) -> dict:
        qs, dropped = [], []
        for q in as_list(data.get("questions")):
            if isinstance(q, str):
                q = {"text": q, "why": ""}
            if not isinstance(q, dict) or not str(q.get("text", "")).strip():
                continue
            # Code check: hypothetical or pitching questions break the Mom Test, so they are removed.
            if any(w in q["text"].lower() for w in PITCH_WORDS):
                dropped.append(q["text"])
                continue
            qs.append(q)
        data["questions"] = qs
        data["dropped_questions"] = dropped
        data["rules"] = [str(r) for r in as_list(data.get("rules"))]
        data["avoid_list"] = [str(r) for r in as_list(data.get("avoid_list"))]
        return data
