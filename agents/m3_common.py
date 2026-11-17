"""Shared helpers for the Phase 2 and Phase 3 agents (owner: M3).

This module defines no Agent subclass, so auto-discovery registers nothing from it.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
SITE_DIRNAME = "phase3_step3_site"  # outputs/ folder of the founder website (phase<N>_step<M>_<name>/)
MAX_ARTIFACT_CHARS = 3500  # per input artifact in a model message; small local models and 8k tokens/min caps

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
P3_PUBLISH_GUIDE = "phase3_step7_publish_guide"

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


TRUNCATED = " [truncated]"
# Claim-checker bookkeeping that the model does not need (the verified/assumption flags themselves are kept).
_NOISE_KEYS = {"check", "fetch_error", "duplicate"}


def _slim(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _slim(v) for k, v in obj.items() if not str(k).startswith("_") and k not in _NOISE_KEYS}
    if isinstance(obj, list):
        return [_slim(v) for v in obj]
    return obj


def _clip(obj: Any, limit: int = MAX_ARTIFACT_CHARS) -> Any:
    """The object itself if its compact JSON fits the limit, else the START of that JSON plus " [truncated]"."""
    text = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= limit:
        return obj
    return text[:limit] + TRUNCATED


def inputs_message(ctx, stems: Iterable[str], extra: Optional[dict] = None) -> str:
    """Brief plus the available input artifacts (and extras) as JSON wrapped in <data> tags."""
    payload: dict = {"brief": _clip(getattr(ctx, "brief", "") or "", 3000), "inputs": {}}
    for stem in stems:
        art = get_artifact(ctx, stem)
        if art is not None:
            art = _slim({k: v for k, v in art.items() if k != "mocked"})
            payload["inputs"][stem] = _clip(art)
    for key, value in (extra or {}).items():
        if value is not None:
            payload[key] = _clip(value)
    body = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
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


# Honesty and safety patterns checked in code for pages and the founder website.
BLOCK_MARK = "[BLOCKED by guardrails]"  # what agents/base.py writes in place of a blocked string

# Markup and tracking markers: always a violation, even after "no" (a <script> tag is a script).
_MARKUP_SUBSTRINGS = {
    BLOCK_MARK.lower(): "blocked by guardrails",
    "<script": "script tag",
    "<iframe": "iframe",
    "javascript:": "javascript URL",
    "googletagmanager": "tracking",
    "google-analytics": "tracking",
    "facebook.com/tr": "tracking pixel",
    "\u2605": "star rating",
}
_MARKUP_REGEXES = [
    (re.compile(r"<[^>]*\son[a-z]+\s*=", re.I), "inline event handler"),
    (re.compile(r"<img[^>]+(width|height)\s*=\s*[\"']?[01][\"'\s>]", re.I), "tracking pixel"),
    (re.compile(r"<(img|link|video|audio|source|embed|object|script)[^>]+(src|href)\s*=\s*[\"']?(https?:)?//", re.I),
     "external resource"),
]
# Words and phrases: whole-word matches only, and skipped when a negation ("no", "not", "without",
# "never") appears within the 30 characters before them in the same sentence ("no checkout",
# "without testimonials").
_WORD_PATTERNS = [
    (r"card\s+numbers?", "payment word: card number"),
    (r"cvv", "payment word: cvv"),
    (r"checkouts?", "payment word: checkout"),
    (r"stripe", "payment word: stripe"),
    (r"paypal", "payment word: paypal"),
    (r"tracking\s+pixels?", "tracking pixel"),
    (r"testimonials?", "testimonial"),
    (r"5-star", "rating"),
    (r"five-star", "rating"),
    (r"countdowns?", "countdown"),
    (r"customers\s+love", "invented praise"),
    (r"trusted\s+by", "invented social proof"),
    (r"(only|just)\s+\d+\s+(spots?|seats?|copies|left)", "scarcity"),
    (r"(join|joined|used\s+by|loved\s+by)\s+\d[\d,.]*\+?(\s*k)?", "invented count"),
    (r"\d[\d,.]*\+?\s+(happy\s+)?(customers|users|designers|people|sign-?ups|buyers)\s+(already|have|love|use|joined)",
     "invented count"),
]
_WORD_REGEXES = [(re.compile(r"(?<![\w-])(?:" + p + r")(?![\w-])", re.I), label) for p, label in _WORD_PATTERNS]
_NEGATION = re.compile(r"\b(no|not|without|never)\b", re.I)
NEGATION_WINDOW = 30

# Real network calls only (scripts and forms are honesty violations, not deployment).
_NETWORK_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"\bfetch\s*\(", r"XMLHttpRequest", r"new\s+WebSocket", r"navigator\.sendBeacon",
        r"\bimport\s+(requests|urllib|socket|http\.client)", r"\bfrom\s+(requests|urllib|socket|http\.client)\b",
        r"\brequests\.(get|post|put|patch|delete)\(", r"urllib\.request", r"\bsocket\.socket\(",
        r"\bcurl\s+-", r"\bwget\s+https?://",
    )
]


_SENTENCE_END = re.compile(r"[.!?;\n]")


def _negated(text: str, start: int) -> bool:
    """A negation within the 30 characters before the match, in the same sentence."""
    window = text[max(0, start - NEGATION_WINDOW):start]
    window = _SENTENCE_END.split(window)[-1]
    return bool(_NEGATION.search(window))


SIMULATED_LABEL = "SIMULATED, not real users"
DEMO_FORM_LABEL = "Demo only: nothing is sent or stored"
SIMULATED_WINDOW = 100


def _simulated(text: str, start: int, end: int) -> bool:
    """A count is allowed when it is labeled SIMULATED within 100 characters around it."""
    around = text[max(0, start - SIMULATED_WINDOW):end + SIMULATED_WINDOW]
    return SIMULATED_LABEL.lower() in " ".join(around.split()).lower()


def content_violations(text: str) -> list[str]:
    """Code-found honesty/safety violations in a piece of page or build content."""
    text = text or ""
    low = text.lower()
    found = [label for needle, label in _MARKUP_SUBSTRINGS.items() if needle in low]
    found += [label for rx, label in _MARKUP_REGEXES if rx.search(text)]
    for rx, label in _WORD_REGEXES:
        for m in rx.finditer(text):
            if _negated(text, m.start()):
                continue
            if label == "invented count" and _simulated(text, m.start(), m.end()):
                continue
            found.append(label)
            break
    if "<form" in low or "</form" in low:
        if form_problems(text):
            found.append("form element")
    return sorted(set(found))


# ---------------------------------------------------------------- the one allowed form (demo sign-up box)

_SENSITIVE_INPUT = re.compile(r"card|cc-|cc_|ccnum|cvc|cvv|password|passwd|iban|\bpin\b|security.?code|expir", re.I)


class _FormScan(HTMLParser):
    """Collects every form (attributes, controls, visible text) in a piece of HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.current = None
        self.depth = 0
        self.stray: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            if self.current is not None:
                self.current["nested"] = True
                return
            self.current = {"attrs": a, "controls": [], "text": []}
            self.forms.append(self.current)
            return
        if tag in ("button", "input", "select", "textarea"):
            if self.current is None:
                self.stray.append(tag)
            else:
                self.current["controls"].append((tag, a))

    def handle_endtag(self, tag):
        if tag == "form":
            if self.current is not None:
                self.current["closed"] = True
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)


def scan_forms(html_text: str) -> list[dict]:
    p = _FormScan()
    try:
        p.feed(html_text or "")
        p.close()
    except Exception:  # noqa: BLE001 - unparsable markup is reported by the caller
        return [{"attrs": {}, "controls": [], "text": [], "unparsable": True}]
    return p.forms


def form_problems(html_text: str) -> list[str]:
    """Problems with the forms in this HTML. Exactly one labeled demo form is allowed:
    no action or method, no submit control (buttons are type="button" or disabled), no password, card or
    CVC fields, the visible label "Demo only: nothing is sent or stored". Anything else is a problem."""
    forms = scan_forms(html_text)
    problems = []
    if len(forms) > 1:
        problems.append(f"{len(forms)} forms found; only one demo sign-up form is allowed")
    for n, f in enumerate(forms, 1):
        tag = f"form {n}"
        if f.get("unparsable"):
            problems.append(f"{tag}: markup could not be parsed")
            continue
        attrs = f["attrs"]
        for bad in ("action", "method", "target", "enctype"):
            if bad in attrs:
                problems.append(f"{tag}: has the {bad} attribute")
        if f.get("nested"):
            problems.append(f"{tag}: nested form")
        if not f.get("closed"):
            problems.append(f"{tag}: not closed")
        text = " ".join("".join(f["text"]).split())
        if DEMO_FORM_LABEL.lower() not in text.lower():
            problems.append(f'{tag}: missing the visible label "{DEMO_FORM_LABEL}"')
        for ctag, a in f["controls"]:
            ctype = a.get("type", "").strip().lower()
            if "formaction" in a or "formmethod" in a:
                problems.append(f"{tag}: {ctag} with formaction or formmethod")
            if ctag == "button":
                if ctype == "submit" or ctype == "reset":
                    problems.append(f'{tag}: button of type="{ctype}"')
                elif ctype != "button" and "disabled" not in a:
                    problems.append(f'{tag}: button without type="button" or disabled (it would submit)')
            if ctag == "input":
                if ctype in ("submit", "image", "reset"):
                    problems.append(f'{tag}: input of type="{ctype}"')
                if ctype in ("password", "file", "hidden"):
                    problems.append(f'{tag}: {ctype} input')
                if ctype not in ("button", "submit", "image", "reset") and "disabled" not in a \
                        and "readonly" not in a:
                    # Pressing Enter in a live field would submit the form to the page's own address.
                    problems.append(f"{tag}: input that can be filled in (it must be disabled or readonly)")
            ident = " ".join(a.get(k, "") for k in ("name", "id", "autocomplete", "placeholder", "aria-label"))
            if _SENSITIVE_INPUT.search(ident):
                problems.append(f"{tag}: password or payment field ({ident.strip()})")
    return problems


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


def site_dir(ctx) -> Path:
    return Path(ctx.out_dir) / SITE_DIRNAME


def safe_rel_path(path: Any) -> Optional[str]:
    """Normalized relative path inside the site folder, or None if unsafe."""
    if not isinstance(path, str):
        return None
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith(SITE_DIRNAME + "/"):
        p = p[len(SITE_DIRNAME) + 1:]
    if not p or p.startswith("/") or re.match(r"^[a-zA-Z]:", p) or "\x00" in p:
        return None
    parts = p.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return p


def read_site_files(ctx, limit_each: int = 4000) -> dict:
    """Contents of the website files (for reviewers), truncated."""
    out = {}
    root = site_dir(ctx)
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            text = f.read_text(encoding="utf-8", errors="replace")
            out[rel] = text if len(text) <= limit_each else text[:limit_each] + " ...[truncated]"
    return out
