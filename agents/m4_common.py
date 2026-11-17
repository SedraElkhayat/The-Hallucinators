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


# ---------------------------------------------------------------- critique shape (CONTEXT.md section 5)

def normalize_critique(data: dict, code_issues: list[str]) -> dict:
    """{"issues": [{"severity": "must_fix"|"should_fix", "text": str}], "verdict": "ok"|"revise"}.

    Issues found by code are always must_fix. Any must_fix means verdict "revise".
    """
    issues = []
    for i in data.get("issues") or []:
        if isinstance(i, str):
            i = {"severity": "should_fix", "text": i}
        if not isinstance(i, dict):
            continue
        sev = str(i.get("severity", "should_fix")).lower().replace("-", "_").replace(" ", "_")
        issues.append({"severity": "must_fix" if sev == "must_fix" else "should_fix",
                       "text": str(i.get("text", ""))})
    issues += [{"severity": "must_fix", "text": t} for t in code_issues]
    verdict = str(data.get("verdict", "ok")).lower()
    if any(i["severity"] == "must_fix" for i in issues):
        verdict = "revise"
    data["issues"] = issues
    data["verdict"] = verdict if verdict in ("ok", "revise") else "ok"
    return data


def count_must_fix(data: dict) -> int:
    return sum(1 for i in (data or {}).get("issues") or []
               if isinstance(i, dict) and i.get("severity") == "must_fix")


# ---------------------------------------------------------------- launch copy rules

import re as _re

_COUNT_RX = _re.compile(
    r"\b\d[\d,.]*\s*\+?\s*k?\s+(?:\w+\s+)?(?:users|customers|sales|downloads|designers|freelancers|people|buyers|"
    r"clients|members|subscribers|sign[- ]?ups|orders|copies\s+sold|students)\b", _re.I)
_TIME_SAVED_RX = _re.compile(
    r"\bsav(?:e|es|ed|ing)\s+(?:you\s+|them\s+)?(?:up\s+to\s+|over\s+|about\s+)?\d[\d,.]*\s*\+?\s*(?:hours?|hrs?|minutes?|mins?|days?|%|percent)"
    r"|\b\d[\d,.]*\s*(?:hours?|hrs?|minutes?)\s+(?:a|per|each|every)\s+(?:week|month|day)"
    r"|\b\d[\d,.]*\s*%\s+(?:faster|more|less|fewer|increase|boost|higher)", _re.I)
_INCOME_NUM_RX = _re.compile(
    r"\b(?:earn|make|income|revenue|profit|get\s+paid)\w*\s+(?:of\s+|up\s+to\s+|over\s+|an?\s+extra\s+)?(?:\$|usd\s?|egp\s?)\s?\d", _re.I)
_FOUNDER_SIGN_RX = _re.compile(
    r"\bi'?m\s+(?:the\s+)?(?:founder|ceo)\b|\bfounder\s+of\b|\bas\s+the\s+founder\b|[-—–]\s*\w+[^\n]{0,30}?\b(?:founder|co-?founder|ceo)\b"
    r"|\b(?:sincerely|best\s+regards|kind\s+regards|warm\s+regards)\b|المؤسس|مؤسس\s", _re.I | _re.M)
_TESTIMONIAL_RX = _re.compile(r"\btestimonials?\b|\breviews?\s+from\b|\bwhat\s+(?:our\s+)?(?:customers|users)\s+say\b", _re.I)


def launch_copy_violations(text: str) -> list[str]:
    """Rules for store page and launch post text: no counts, testimonials, income or time-saved numbers,
    and never signed as the founder."""
    from core.guardrails import check_output
    from core.guardrails import is_negated
    t = text or ""
    found = []
    for name, rx in (("user_or_sales_count", _COUNT_RX), ("time_saved_number", _TIME_SAVED_RX),
                     ("income_number", _INCOME_NUM_RX), ("signed_as_founder", _FOUNDER_SIGN_RX),
                     ("testimonial", _TESTIMONIAL_RX)):
        for m in rx.finditer(t):
            if name == "testimonial" and is_negated(t, m.start()):
                continue
            found.append(name)
            break
    found += [f for f in check_output(t).findings if f not in found]
    return found


# ---------------------------------------------------------------- source artifacts and channels

ARTIFACT_STEM_RX = _re.compile(r"\bphase\d_(?:step\d+_[a-z0-9_]+|gate_[a-z0-9_]+)", _re.I)
_PAID_RX = _re.compile(
    r"\bpaid\b|\bsponsor\w*|\bboost(?:ed)?\s+posts?\b|\bads?\b|\badvertis\w*|\bppc\b|\bcpc\b|\bpromoted\s+posts?\b"
    r"|\bbuy(?:ing)?\s+(?:followers|likes|traffic|subscribers|views)|\bbought\s+(?:followers|likes)"
    r"|\binfluencer\s+(?:fee|payment|deal|campaign)|\bad\s+spend\b|\bإعلان\w*|\bاعلان\w*|ممول", _re.I)


def is_paid_channel(text: str) -> bool:
    from core.guardrails import is_negated
    for m in _PAID_RX.finditer(text or ""):
        if not is_negated(text, m.start()):
            return True
    return False


# ---------------------------------------------------------------- policy terms

_WINDOW_RX = _re.compile(r"\b\d+\s*[- ]?\s*(?:business\s+|calendar\s+|working\s+)?(?:days?|weeks?|months?|hours?)\b", _re.I)
_PRICE_RX = _re.compile(r"(?:\$|usd\s?|egp\s?)\s?(\d[\d,.]*)|(\d[\d,.]*)\s*(?:usd|egp|dollars|pounds|جنيه|دولار)", _re.I)
_COMPLIANCE_CLAIM_RX = _re.compile(
    r"\b(?:fully\s+compliant|(?:gdpr|ccpa|legally)\s+compliant|complies\s+with|in\s+compliance\s+with|legally\s+binding|"
    r"meets\s+all\s+legal|approved\s+by\s+(?:a\s+)?lawyers?|lawyer[- ]approved)\b", _re.I)


def unsupported_terms(reply: str, reference_text: str) -> list[str]:
    """Time windows and prices in reply that do not appear in reference_text."""
    ref = (reference_text or "").lower()
    bad = []
    for m in _WINDOW_RX.finditer(reply or ""):
        num = _re.match(r"\d+", m.group(0)).group(0)
        unit = _re.search(r"(day|week|month|hour)", m.group(0), _re.I).group(1).lower()
        if not _re.search(rf"\b{num}\s*[- ]?\s*(?:\w+\s+)?{unit}", ref):
            bad.append(m.group(0))
    for m in _PRICE_RX.finditer(reply or ""):
        num = (m.group(1) or m.group(2) or "").rstrip(".,")
        if num and not _re.search(rf"(?<![\d.]){_re.escape(num)}(?![\d])", ref):
            bad.append(m.group(0))
    return bad


def artifact_text(ctx: Context, *steps: str) -> str:
    import json as _json
    parts = []
    for s in steps:
        if ctx.store.has(s):
            parts.append(_json.dumps(ctx.store.get(s), ensure_ascii=False, default=str))
    return "\n".join(parts)
