# OWNER: M4
"""Shared base class and utilities for Member 4 agents."""
from __future__ import annotations

import json
from agents.base import Agent
from core.contracts import Context


class M4Agent(Agent):
    name: str = ""

    def build_user_message(self, ctx: Context) -> str:
        payload = {
            "brief": ctx.brief,
            "inputs": {s: ctx.store.get(s) for s in self.inputs if ctx.store.has(s)},
        }
        if ctx.extra:
            payload["extra"] = {
                k: v for k, v in ctx.extra.items()
                if not str(k).startswith("_") and k != "halt_phase"
            }
        return "<data>\n" + json.dumps(payload, ensure_ascii=False, indent=1, default=str) + "\n</data>"
