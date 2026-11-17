# OWNER: M4
"""channel_planner agent for Phase 5 Launch.

Selects 2 to 3 organic launch channels tied to upstream evidence.
"""
from __future__ import annotations

from agents.m4_common import ARTIFACT_STEM_RX, M4Agent, is_paid_channel
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
                        "evidence": str(c.get("evidence") or "ASSUMPTION (no evidence given)"),
                        "first_actions": list(c.get("first_actions", [])) if isinstance(c.get("first_actions"), list) else [str(c.get("first_actions", ""))],
                    })
        if not clean_channels:
            clean_channels = [
                {
                    "name": "Design Freelancer Communities",
                    "evidence": "ASSUMPTION (STUBBED: the model returned no channels; no source)",
                    "first_actions": ["Share template preview", "Collect feedback on invoice tracker"],
                },
                {
                    "name": "LinkedIn Organic Content",
                    "evidence": "ASSUMPTION (STUBBED: the model returned no channels; no source)",
                    "first_actions": ["Post short breakdown of invoice management", "Link to project dashboard"],
                },
            ]
        free, dropped = [], []
        for c in clean_channels:
            blob = " ".join([c["name"]] + [str(a) for a in c["first_actions"]])
            if is_paid_channel(blob):
                dropped.append({"name": c["name"], "reason": "paid channel (ads, sponsored posts or bought followers)"})
                continue
            if not ARTIFACT_STEM_RX.search(c["evidence"]):
                c["evidence"] = "ASSUMPTION (no source artifact named): " + c["evidence"]
            free.append(c)
        data["channels"] = free[:3]
        if dropped:
            data["dropped_channels"] = dropped
        return data
