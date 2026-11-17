"""lean_canvas_drafter: nine Lean Canvas boxes, each sourced or labeled ASSUMPTION."""
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_DEMAND_SIGNALS, P1_FEASIBILITY, P1_FOUNDER_FIT,
                              P1_IDEA_CARD, P1_INTERVIEWS, P1_MARKET, P1_REPORT,
                              P2_CANVAS, P2_COMPETITOR_ANALYSIS)

BOXES = ("customer_segments", "problem", "unique_value_proposition", "solution", "channels",
         "revenue_streams", "cost_structure", "key_metrics", "unfair_advantage")
_SOURCED = re.compile(r"(https?://|\bphase[1-6]_step\d+_[a-z_]+|\(source:)", re.I)


class LeanCanvasDrafter(M3InputsMixin, Agent):
    name = "lean_canvas_drafter"
    phase = 2
    step = P2_CANVAS
    inputs = [P1_IDEA_CARD, P2_COMPETITOR_ANALYSIS, P1_MARKET, P1_DEMAND_SIGNALS, P1_INTERVIEWS,
              P1_FOUNDER_FIT, P1_FEASIBILITY, P1_REPORT]
    tools = []
    required_keys = ["boxes"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        raw = data.get("boxes") if isinstance(data.get("boxes"), dict) else {}
        boxes = {}
        for key in BOXES:
            v = raw.get(key, "")
            if isinstance(v, (list, tuple)):
                v = "; ".join(str(x) for x in v)
            text = str(v or "").strip() or "unknown"
            # Every statement is sourced or ends with ASSUMPTION (enforced in code).
            if not _SOURCED.search(text) and "ASSUMPTION" not in text:
                text = text.rstrip(". ") + " ASSUMPTION"
            boxes[key] = text
        data["boxes"] = boxes
        return data
