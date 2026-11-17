"""skeptic: challenge the ranking and the leading option: risks, kill criteria, what would change the verdict.
A kill criterion counts as triggered only when it names the evidence that meets it (checked in code)."""
import re

from agents.base import Agent
from agents.m2_common import (COMPETITORS, DEMAND, FEASIBILITY, FOUNDER_FIT, IDEA_CARD, INTERVIEWS, MARKET,
                              OPPORTUNITIES, SCOPE, SCORES, SKEPTIC, founder_time, message, norm_risks)


TIME_WORDS = re.compile(r"\b(time|hours?)\b", re.I)
HOURS_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?hours?", re.I)


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
        return message(ctx, self.inputs + self.optional_inputs, {"founder_time": founder_time(ctx.brief)},
                       brief=False, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        data = norm_risks(data)
        t = founder_time(ctx.brief) or {}
        total, per_week = t.get("total_hours"), t.get("hours_per_week")
        for k in data["kill_criteria"]:
            if not (k["triggered"] and total and TIME_WORDS.search(f"{k['text']} {k.get('evidence', '')}")):
                continue
            needed = [float(n) for n in HOURS_NUM.findall(str(k.get("evidence", "")))
                      if float(n) not in (float(total), float(per_week or -1))]
            if needed and max(needed) <= total:
                # The model's own numbers say the time is enough (e.g. 104 hours available, 40 needed).
                k["triggered"], k["triggered_contradicted"] = False, f"{total} hours available >= {max(needed):g} needed"
        return data
