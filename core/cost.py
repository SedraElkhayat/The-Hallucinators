# OWNER: M1
"""Cost per call from token counts. Local open-weight models cost $0."""
from __future__ import annotations

import os
import threading

# USD per 1M tokens (in, out). Local models are free.
PRICES = {"default": (0.0, 0.0)}

_totals = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "calls": 0}
_lock = threading.Lock()


def price_for(model: str) -> tuple[float, float]:
    env_in, env_out = os.getenv("LLM_PRICE_IN_PER_M"), os.getenv("LLM_PRICE_OUT_PER_M")
    if env_in and env_out:
        return float(env_in), float(env_out)
    return PRICES.get(model, PRICES["default"])


def compute(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = price_for(model)
    cost = (tokens_in * pin + tokens_out * pout) / 1_000_000
    with _lock:
        _totals["tokens_in"] += tokens_in
        _totals["tokens_out"] += tokens_out
        _totals["cost"] += cost
        _totals["calls"] += 1
    return cost


def totals() -> dict:
    with _lock:
        return dict(_totals)


def reset() -> None:
    with _lock:
        _totals.update(tokens_in=0, tokens_out=0, cost=0.0, calls=0)


def _entries(log) -> list:
    return log.entries() if hasattr(log, "entries") else list(log or [])


def cost_per_run(log) -> float:
    """Sum of 'cost' over every decision-log entry (a DecisionLog or a list of entries)."""
    return round(sum(float(e.get("cost") or 0) for e in _entries(log)), 6)


def tokens_per_run(log) -> dict:
    ents = _entries(log)
    tin = sum(int(e.get("tokens_in") or 0) for e in ents)
    tout = sum(int(e.get("tokens_out") or 0) for e in ents)
    return {"tokens_in": tin, "tokens_out": tout, "total": tin + tout}
