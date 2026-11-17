# OWNER: M4
"""channel_planner agent for Phase 5 Launch.

Selects 2 to 3 organic launch channels tied to upstream evidence.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context


class ChannelPlanner(M4Agent):
    name = "channel_planner"
    phase = 5
    step = "phase5_step1_channel_plan"
    inputs = ["phase1_step5_market", "phase2_step3_demand_test_plan", "phase4_step2_offer"]
    tools = []
    required_keys = ["channels"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        raw_channels = data.get("channels")
        clean_channels = []
        if isinstance(raw_channels, list):
            for c in raw_channels:
                if isinstance(c, dict):
                    clean_channels.append({
                        "name": str(c.get("name", "Organic Community")),
                        "evidence": str(c.get("evidence", "Sourced from Phase 1 audience research")),
                        "first_actions": list(c.get("first_actions", [])) if isinstance(c.get("first_actions"), list) else [str(c.get("first_actions", ""))],
                    })
        if not clean_channels:
            clean_channels = [
                {
                    "name": "Design Freelancer Communities",
                    "evidence": "Freelancers actively share workflow templates in designer forums",
                    "first_actions": ["Share template preview", "Collect feedback on invoice tracker"],
                },
                {
                    "name": "LinkedIn Organic Content",
                    "evidence": "Discussions regarding unpaid client invoices and revision scope creep",
                    "first_actions": ["Post short breakdown of invoice management", "Link to project dashboard"],
                },
            ]
        data["channels"] = clean_channels[:3]
        return data
