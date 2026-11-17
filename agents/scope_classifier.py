"""scope_classifier: is the product digital and allowed? (Phase 1, step 1)

Excluded: physical goods; financial, investment or crypto products; health or legal advice products.
A vague brief is "undetermined" (the clarifier asks), never rejected early. A hard "false" halts the phase.
"""
from agents.base import Agent
from agents.m2_common import CLARIFICATION, OPTIONS, SCOPE, message, redact_input

EXCLUDED = {"physical_goods", "financial_or_crypto", "health_or_legal_advice"}


def classify_text(ctx) -> list[str]:
    """Code flags from core.guardrails.check_input (out-of-scope patterns) on the brief."""
    _, findings = redact_input(ctx.brief or "")
    return [f for f in findings if f == "out_of_scope"]


def normalize_scope(data: dict) -> dict:
    v = data.get("is_digital")
    if isinstance(v, str):
        s = v.strip().lower()
        v = True if s in ("true", "yes") else False if s in ("false", "no") else "undetermined"
    if v not in (True, False):
        v = "undetermined"
    data["is_digital"] = v
    reason = data.get("excluded_reason")
    if isinstance(reason, str) and reason.strip().lower() in ("", "null", "none"):
        reason = None
    if reason is not None:
        r = str(reason).strip().lower()
        reason = r if r in EXCLUDED else f"other: {reason}"
        data["is_digital"] = False  # an excluded product is never in scope
    data["excluded_reason"] = reason
    data["product_type"] = str(data.get("product_type") or "unknown")
    data["reasoning"] = str(data.get("reasoning") or "")
    return data


class ScopeClassifier(Agent):
    name = "scope_classifier"
    phase = 1
    step = SCOPE
    inputs: list = []
    tools: list = []
    required_keys = ["is_digital", "product_type", "excluded_reason", "reasoning"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, [CLARIFICATION, OPTIONS])

    def post_process(self, ctx, data: dict) -> dict:
        data = normalize_scope(data)
        flags = classify_text(ctx)
        data["code_flags"] = flags
        if flags and data["is_digital"] is True and not ctx.store.has(CLARIFICATION):
            # First pass only: a keyword hit sends the brief to the clarifier instead of passing silently.
            data["is_digital"] = "undetermined"
            data["reasoning"] += " (Code check: the brief matches an out-of-scope pattern; the founder is asked.)"
        if data["is_digital"] is False:
            ctx.extra["halt_phase"] = f"product is out of scope ({data['excluded_reason'] or 'not digital'})"
        return data
