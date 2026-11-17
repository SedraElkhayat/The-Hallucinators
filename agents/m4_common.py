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


def founder_input(ctx: Context, key: str, prompt: str) -> str:
    """Ask the founder for an input; return "" when none is available (never invent one)."""
    try:
        value = ctx.founder.provide(key, prompt)
    except Exception:
        return ""
    return "" if value is None else str(value)


def provenance_of(text: str) -> str:
    """Label founder-provided data: SAMPLE/MOCKED when the text says so, else FOUNDER-PROVIDED."""
    up = (text or "").upper()
    if "MOCKED" in up:
        return "MOCKED"
    if "SAMPLE" in up or "SCRIPTED" in up:
        return "SAMPLE"
    return "FOUNDER-PROVIDED (unverified)"


def price_from_pricing(ctx: Context):
    """Price chosen by pricing_analyst, or None when unavailable."""
    try:
        if ctx.store.has("phase4_step1_pricing"):
            return float(ctx.store.get("phase4_step1_pricing").get("price_usd"))
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
