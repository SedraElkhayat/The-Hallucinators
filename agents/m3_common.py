"""Shared helpers for the Phase 2 and Phase 3 agents (owner: M3).

This module defines no Agent subclass, so auto-discovery registers nothing from it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
BUILD_DIRNAME = "phase3_build"
MAX_ARTIFACT_CHARS = 6000

# Artifact stems used by Phase 2 and 3 (CONTEXT.md section 5).
P1_CLARIFICATION = "phase1_step2_clarification"
P1_IDEA_CARD = "phase1_step4_idea_card"
P1_MARKET = "phase1_step5_market"
P1_DEMAND_SIGNALS = "phase1_step5_demand_signals"
P1_COMPETITORS = "phase1_step5_competitors"
P1_FOUNDER_FIT = "phase1_step5_founder_fit"
P1_FEASIBILITY = "phase1_step6_feasibility"
P1_INTERVIEWS = "phase1_step6_interview_findings"
P1_SKEPTIC = "phase1_step8_skeptic"
P1_REPORT = "phase1_step9_discover_report"

P2_COMPETITOR_ANALYSIS = "phase2_step1_competitor_analysis"
P2_CANVAS = "phase2_step2_lean_canvas"
P2_PLAN = "phase2_step3_demand_test_plan"
P2_LANDING = "phase2_step4_landing_page"
P2_RESULTS = "phase2_step5_demand_results"
P2_ASSUMPTIONS = "phase2_step6_assumptions"
P2_RISKS = "phase2_step7_risks"
P2_SCORECARD = "phase2_step8_scorecard"
P2_REPORT = "phase2_step9_validation_report"
P2_CRITIQUE = "phase2_step9_critique"

P3_SPEC = "phase3_step1_spec"
P3_COPY = "phase3_step2_page_copy"
P3_BUILD = "phase3_step3_build"
P3_DOCS = "phase3_step4_user_docs"
P3_QA = "phase3_step5_qa_report"
P3_REVIEW = "phase3_step6_content_review"

DEFAULT_TARGET = 100
DEFAULT_WINDOW_DAYS = 14


# ---------------------------------------------------------------- artifacts

def get_artifact(ctx, step: str) -> Optional[dict]:
    """Return the artifact dict, or None if it does not exist."""
    try:
        if hasattr(ctx.store, "has") and not ctx.store.has(step):
            return None
        data = ctx.store.get(step)
    except (KeyError, FileNotFoundError):
        return None
    return data if isinstance(data, dict) else None


def _clip(obj: Any, limit: int = MAX_ARTIFACT_CHARS) -> Any:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return obj
    return text[:limit] + " ...[truncated]"


def inputs_message(ctx, stems: Iterable[str], extra: Optional[dict] = None) -> str:
    """JSON of the available input artifacts (plus extras) wrapped in <data> tags."""
    payload: dict = {}
    for stem in stems:
        art = get_artifact(ctx, stem)
        if art is not None:
            payload[stem] = _clip(art)
    for key, value in (extra or {}).items():
        if value is not None:
            payload[key] = _clip(value)
    body = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    return f"<data>\n{body}\n</data>\nAnswer with the JSON object described in your instructions."


class M3InputsMixin:
    """build_user_message over required inputs plus optional_inputs that exist.

    Only ctx.extra["critique"] is forwarded (on revision rounds), which keeps messages short.
    """

    optional_inputs: list = []

    def build_user_message(self, ctx) -> str:  # noqa: D401
        stems = list(getattr(self, "inputs", [])) + list(self.optional_inputs)
        extra = {}
        crit = (getattr(ctx, "extra", None) or {}).get("critique")
        if crit:
            extra["critique"] = crit
        extra.update(self.extra_payload(ctx))
        return inputs_message(ctx, stems, extra)

    def extra_payload(self, ctx) -> dict:
        return {}


def load_system_prompt(name: str) -> str:
    parts = []
    for fname in (f"{name}.md", "_common.md"):
        p = PROMPTS_DIR / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- logging

def log_action(ctx, agent: str, action: str, sources=(), model=None, cost: float = 0.0,
               approved_by=None, **extra) -> None:
    ctx.log.action(agent, action, sources=list(sources), model=model, cost=cost,
                   approved_by=approved_by, **extra)


# ---------------------------------------------------------------- guardrails

def guardrail_findings(text: str) -> list[str]:
    """Run core.guardrails.check_output; return findings (empty list = allowed)."""
    try:
        from core.guardrails import check_output
    except Exception:  # pragma: no cover - guardrails module missing
        return []
    try:
        res = check_output(text)
    except TypeError:
        res = check_output(text, "m3")
    if isinstance(res, bool):
        return [] if res else ["blocked by guardrails"]
    if isinstance(res, tuple):
        allowed = bool(res[0])
        findings = list(res[1]) if len(res) > 1 and isinstance(res[1], (list, tuple)) else []
    elif isinstance(res, dict):
        allowed = bool(res.get("allowed", True))
        findings = list(res.get("findings") or [])
    else:
        allowed = bool(getattr(res, "allowed", True))
        findings = list(getattr(res, "findings", None) or [])
    if allowed:
        return []
    return [str(f) for f in findings] or ["blocked by guardrails"]


# Honesty and safety patterns checked in code for pages and built files.
_BANNED_SUBSTRINGS = {
    "<script": "script tag",
    "<form": "form element",
    "<iframe": "iframe",
    "javascript:": "javascript URL",
    "card number": "payment word: card number",
    "cvv": "payment word: cvv",
    "checkout": "payment word: checkout",
    "stripe": "payment word: stripe",
    "paypal": "payment word: paypal",
    "googletagmanager": "tracking",
    "google-analytics": "tracking",
    "facebook.com/tr": "tracking pixel",
    "tracking pixel": "tracking pixel",
    "testimonial": "testimonial",
    "5-star": "rating",
    "five-star": "rating",
    "★": "star rating",
    "countdown": "countdown",
    "customers love": "invented praise",
    "trusted by": "invented social proof",
}
_BANNED_REGEXES = [
    (re.compile(r"\son[a-z]+\s*=", re.I), "inline event handler"),
    (re.compile(r"<img[^>]+(width|height)\s*=\s*[\"']?[01][\"'\s>]", re.I), "tracking pixel"),
    (re.compile(r"<(img|link|video|audio|source|embed|object)[^>]+(src|href)\s*=\s*[\"']?(https?:)?//", re.I),
     "external resource"),
    (re.compile(r"\b(only|just)\s+\d+\s+(spots?|seats?|copies|left)\b", re.I), "scarcity"),
    (re.compile(r"\b(join|joined|used by|loved by)\s+[\d,.]+\+?\s*(k\b)?", re.I), "invented count"),
    (re.compile(r"\b[\d,.]+\+?\s+(happy\s+)?(customers|users|designers|people|sign-?ups|buyers)\s+(already|have|love|use|joined)",
                re.I), "invented count"),
]
_NETWORK_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"<script", r"\bfetch\s*\(", r"XMLHttpRequest", r"new\s+WebSocket", r"navigator\.sendBeacon",
        r"\bimport\s+(requests|urllib|socket|http\.client)", r"\brequests\.(get|post|put)\(",
        r"urllib\.request", r"\bsocket\.socket\(", r"<form",
    )
]


def content_violations(text: str) -> list[str]:
    """Code-found honesty/safety violations in a piece of page or build content."""
    low = (text or "").lower()
    found = [label for needle, label in _BANNED_SUBSTRINGS.items() if needle in low]
    found += [label for rx, label in _BANNED_REGEXES if rx.search(text or "")]
    return sorted(set(found))


def network_code_present(text: str) -> bool:
    return any(rx.search(text or "") for rx in _NETWORK_PATTERNS)


# ---------------------------------------------------------------- misc

def count_must_fix(critique: Optional[dict]) -> int:
    if not critique:
        return 0
    return sum(1 for i in critique.get("issues") or []
               if isinstance(i, dict) and str(i.get("severity", "")).lower() == "must_fix")


def normalize_verdict(data: dict) -> dict:
    """A critique with any must_fix issue has verdict 'revise'; verdict is 'ok' or 'revise'."""
    issues = []
    for i in data.get("issues") or []:
        if isinstance(i, str):
            i = {"severity": "should_fix", "text": i}
        if isinstance(i, dict):
            sev = str(i.get("severity", "should_fix")).lower().replace("-", "_").replace(" ", "_")
            i["severity"] = "must_fix" if sev == "must_fix" else "should_fix"
            issues.append(i)
    data["issues"] = issues
    verdict = str(data.get("verdict", "ok")).lower()
    if count_must_fix(data) > 0:
        verdict = "revise"
    data["verdict"] = verdict if verdict in ("ok", "revise") else "ok"
    return data


def positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return int(value.strip())
    return None


def plan_target(ctx) -> tuple[int, int]:
    plan = get_artifact(ctx, P2_PLAN) or {}
    return (positive_int(plan.get("target")) or DEFAULT_TARGET,
            positive_int(plan.get("window_days")) or DEFAULT_WINDOW_DAYS)


def build_dir(ctx) -> Path:
    return Path(ctx.out_dir) / BUILD_DIRNAME


def safe_rel_path(path: Any) -> Optional[str]:
    """Normalized relative path inside the build folder, or None if unsafe."""
    if not isinstance(path, str):
        return None
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith(BUILD_DIRNAME + "/"):
        p = p[len(BUILD_DIRNAME) + 1:]
    if not p or p.startswith("/") or re.match(r"^[a-zA-Z]:", p) or "\x00" in p:
        return None
    parts = p.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return p


def read_build_files(ctx, limit_each: int = 4000) -> dict:
    """Contents of the built files (for reviewers), truncated."""
    out = {}
    root = build_dir(ctx)
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            text = f.read_text(encoding="utf-8", errors="replace")
            out[rel] = text if len(text) <= limit_each else text[:limit_each] + " ...[truncated]"
    return out
