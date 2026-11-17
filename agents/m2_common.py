"""Shared helpers for the Phase 1 agents (owner: M2).

This module defines no registered Agent (the research base class has an empty ``name``), so
auto-discovery registers nothing from it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from agents.base import BLOCK_MARK, PROMPT_DIR, Agent, _set_path, _walk_strings

# ---------------------------------------------------------------- artifact stems (CONTEXT.md section 5)
SCOPE = "phase1_step1_scope"
CLARIFICATION = "phase1_step2_clarification"
OPTIONS = "phase1_step2_options"
IDEA_CANDIDATES = "phase1_step3_idea_candidates"
IDEA_CHOICE = "phase1_step3_idea_choice"
IDEA_CARD = "phase1_step4_idea_card"
OPPORTUNITIES = "phase1_step5_opportunities"
MARKET = "phase1_step5_market"
DEMAND = "phase1_step5_demand_signals"
COMPETITORS = "phase1_step5_competitors"
FOUNDER_FIT = "phase1_step5_founder_fit"
INTERVIEW_SCRIPT = "phase1_step5_interview_script"
FEASIBILITY = "phase1_step6_feasibility"
INTERVIEWS = "phase1_step6_interview_findings"
SCORES = "phase1_step7_opportunity_scores"
SKEPTIC = "phase1_step8_skeptic"
REPORT = "phase1_step9_discover_report"
CRITIQUE = "phase1_step9_critique"
PIVOT_NOTES = "pivot_notes"

EVIDENCE_STEPS = (OPPORTUNITIES, MARKET, DEMAND, COMPETITORS)
RATINGS = ("strong", "adequate", "weak", "unknown")
MAX_ARTIFACT_CHARS = 3000
MAX_PAGE_CHARS = 1800

UNKNOWN_ANSWERS = {"", "unknown", "i don't know", "i dont know", "idk", "don't know", "dont know", "not sure",
                   "n/a", "none", "?", "لا أعرف", "لا اعرف", "مش عارف", "مش عارفة", "غير معروف"}


# ---------------------------------------------------------------- artifacts and messages

def get_artifact(ctx, step: str) -> Optional[dict]:
    try:
        if not ctx.store.has(step):
            return None
        data = ctx.store.get(step)
    except (KeyError, FileNotFoundError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clean(obj: Any) -> Any:
    """Drop private keys (``_meta``, ``_marker``) and the ``mocked`` flag before sending to a model."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not str(k).startswith("_") and k != "mocked"}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def clip(obj: Any, limit: int = MAX_ARTIFACT_CHARS) -> Any:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return obj if len(text) <= limit else text[:limit] + " ...[truncated]"


def digest(stem: str, art: dict) -> Any:
    """Compact view of an artifact for the aggregating agents (keeps small local models within context)."""
    art = clean(art)
    if stem in EVIDENCE_STEPS:
        out = {"insufficient_evidence": art.get("insufficient_evidence"),
               "claims": [{"claim": str(c.get("claim", ""))[:240], "verified": c.get("verified") is True}
                          for c in (art.get("claims") or [])[:8] if isinstance(c, dict)]}
        for k in ("market_definition", "price_signals", "alternatives"):
            if k in art:
                out[k] = clip(art[k], 800)
        if "competitors" in art:
            out["competitors"] = [{k: str(c.get(k, ""))[:120] for k in ("name", "pricing", "positioning")}
                                  for c in (art.get("competitors") or [])[:6] if isinstance(c, dict)]
        return out
    if stem in (CLARIFICATION, OPTIONS):
        fields = {f: v.get("value") for f, v in (art.get("fields") or {}).items() if isinstance(v, dict)}
        out = {"fields": fields}
        if art.get("idea"):
            out["idea"] = art["idea"]
        return out
    if stem == PIVOT_NOTES:
        return clip(art, 1500)
    if stem in (FOUNDER_FIT, FEASIBILITY):
        return {k: clip(art.get(k), 400) for k in ("rating", "reasoning", "evidence_refs", "effort_hours_estimate")
                if k in art}
    if stem == INTERVIEWS:
        return {k: clip(art.get(k), 800) for k in ("provenance", "findings", "pain_points", "current_solutions",
                                                     "commitment_signals", "weak_evidence") if k in art}
    return clip(art, 1500)


def message(ctx, stems: Iterable[str], extra: Optional[dict] = None, brief: bool = True,
            compact: bool = False) -> str:
    """User message: the brief, the available input artifacts and extras, as JSON inside <data> tags."""
    payload: dict = {}
    if brief:
        payload["brief"] = clip(ctx.brief or "", 3000)
    payload["inputs"] = {}
    for stem in stems:
        art = get_artifact(ctx, stem)
        if art is not None:
            payload["inputs"][stem] = digest(stem, art) if compact else clip(clean(art))
    for k, v in (extra or {}).items():
        if v is not None:
            payload[k] = v
    body = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    return f"<data>\n{body}\n</data>\nAnswer with the JSON object described in your instructions."


_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\s*(?:per|a|/|each)\s*week", re.I)
_SPAN = re.compile(r"(\d+(?:\.\d+)?)\s*(months?|weeks?)", re.I)


def founder_time(brief: str) -> Optional[dict]:
    """Founder time budget computed in code (small models get this arithmetic wrong).
    "8 hours per week for 3 months" -> 8 h/week, 13 weeks, about 104 hours."""
    h = _HOURS.search(brief or "")
    if not h:
        return None
    per_week = float(h.group(1))
    out: dict = {"hours_per_week": per_week}
    rest = (brief or "")[h.end():h.end() + 80]
    sp = _SPAN.search(rest)
    if sp:
        n = float(sp.group(1))
        weeks = round(n * 52 / 12) if sp.group(2).lower().startswith("month") else n
        out.update({"weeks": weeks, "total_hours": round(per_week * weeks)})
    out["note"] = "Computed in code from the brief. Use these numbers; do not redo the arithmetic."
    return out


def load_prompt(name: str) -> str:
    own = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    common = PROMPT_DIR / "_common.md"
    return own + ("\n\n" + common.read_text(encoding="utf-8") if common.exists() else "")


def is_unknown(answer: Optional[str]) -> bool:
    a = (answer or "").strip().strip(".!").lower()
    return a in UNKNOWN_ANSWERS or a.startswith("unknown")


# ---------------------------------------------------------------- guardrails

def redact_input(text: str) -> tuple[str, list[str]]:
    """Founder text passes core.guardrails.check_input: card numbers and secrets are redacted."""
    try:
        from core.guardrails import check_input
        res = check_input(text or "")
        return str(getattr(res, "text", text) or ""), list(getattr(res, "findings", []) or [])
    except Exception:  # noqa: BLE001 - guardrails unavailable: keep the text, report nothing
        return text or "", []


def untrusted(text: str) -> str:
    """Wrap web text as untrusted data (core.guardrails.wrap_untrusted when it exists)."""
    try:
        from core.guardrails import wrap_untrusted
        return wrap_untrusted(text)
    except Exception:  # noqa: BLE001
        safe = re.sub(r"<\s*/?\s*data\b", "&lt;data", text or "", flags=re.I)
        return f'<data untrusted="true">\n{safe}\n</data>'


def guard_data(ctx, agent: str, data: dict) -> dict:
    """Replace every string that core.guardrails.check_output blocks with the block mark, and log it.

    Used by founder-kind agents that make their own model calls (the base class does this for llm kind)."""
    from core.guardrails import check_output
    blocked = []
    for path, s in list(_walk_strings(data)):
        res = check_output(s)
        if not res.allowed:
            blocked.append((path, ", ".join(map(str, res.findings)) or "blocked"))
    for path, reason in blocked:
        _set_path(data, path, f"{BLOCK_MARK} {reason}")
    if blocked:
        ctx.log.action(agent, "guardrail_drop", reasons=sorted({r for _, r in blocked}), outcome="dropped")
    return data


def blocked(s: Any) -> bool:
    return isinstance(s, str) and s.startswith(BLOCK_MARK)


# ---------------------------------------------------------------- model calls for founder-kind agents

def ask_model(agent: Agent, ctx, user: str, keys: list[str], prompt_name: Optional[str] = None,
              llm_agent: Optional[str] = None) -> tuple[dict, str, float, dict]:
    """One JSON model call with two retries on invalid JSON or missing keys; output passes the guardrails.

    Returns (data, model, cost, tokens)."""
    system = load_prompt(prompt_name or agent.name)
    who = llm_agent or agent.name
    cost, last_err = 0.0, None
    tokens = {"tokens_in": 0, "tokens_out": 0}
    for _ in range(3):
        msg = user if last_err is None else (
            f"{user}\n\nYour previous answer was invalid: {last_err}. Reply with valid JSON only, "
            f"containing the keys {keys}.")
        resp = ctx.llm.chat(system, msg, agent=who, json_mode=True)
        cost += resp.cost
        tokens["tokens_in"] += resp.tokens_in
        tokens["tokens_out"] += resp.tokens_out
        if resp.data is None:
            last_err = "not valid JSON"
            continue
        missing = [k for k in keys if k not in resp.data]
        if missing:
            last_err = f"missing keys {missing}"
            continue
        data = guard_data(ctx, agent.name, dict(resp.data))
        return data, resp.model, cost, tokens
    raise ValueError(f"{agent.name}: model output invalid after retries ({last_err})")


# ---------------------------------------------------------------- normalizers

def as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def truthy(v) -> bool:
    """True for real booleans and for the strings small models write instead ("true", "yes")."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "y", "1", "نعم")


def to_number(v):
    """First number in a value: 7, "7", "7/10", "score 6.5" -> float; else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else None


def id_list(v) -> list[str]:
    """Claim ids as a list, also when the model writes one string such as "C1, C2"."""
    out = []
    for x in as_list(v):
        out += [p.strip() for p in re.split(r"[,;\s]+", str(x)) if p.strip()]
    return out


def norm_severity(v) -> str:
    s = re.sub(r"[\s\-]+", "_", str(v or "").strip().lower())
    return "must_fix" if s in ("must_fix", "mustfix", "critical", "blocker", "high") else "should_fix"


def norm_rating(data: dict) -> dict:
    """A rating outside the allowed set, or a rating without evidence_refs, becomes 'unknown' (honesty rule)."""
    r = str(data.get("rating", "unknown")).strip().strip(".").lower()
    refs = [str(x) for x in as_list(data.get("evidence_refs")) if str(x).strip()]
    data["evidence_refs"] = refs
    if r not in RATINGS:
        r = "unknown"
    if r != "unknown" and not refs:
        data["rating_downgraded"] = f"'{r}' had no evidence_refs, so it counts as unknown"
        r = "unknown"
    data["rating"] = r
    return data


def norm_claims(claims) -> list[dict]:
    out = []
    for c in as_list(claims):
        if isinstance(c, str):
            c = {"claim": c, "source_url": "", "quote": "", "verified": None, "assumption": True}
        if not isinstance(c, dict) or not str(c.get("claim", "")).strip():
            continue
        c.setdefault("source_url", "")
        c.setdefault("quote", "")
        c.setdefault("verified", None)
        c["assumption"] = bool(c.get("assumption")) or c.get("verified") is not True
        out.append(c)
    return out


SPECULATION = re.compile(r"\b(might|may|could|possibly|potentially|perhaps|likely|assumption)\b|قد |ربما", re.I)


def norm_risks(data: dict) -> dict:
    risks = []
    for r in as_list(data.get("risks")):
        if isinstance(r, str):
            r = {"text": r, "severity": "medium"}
        if isinstance(r, dict) and r.get("text"):
            sev = str(r.get("severity", "medium")).lower()
            r["severity"] = sev if sev in ("high", "medium", "low") else "medium"
            risks.append(r)
    data["risks"] = risks
    kills = []
    for k in as_list(data.get("kill_criteria")):
        if isinstance(k, str):
            k = {"text": k, "triggered": False}
        if isinstance(k, dict) and k.get("text"):
            trig = truthy(k.get("triggered"))
            ev = str(k.get("evidence", "")).strip()
            if trig and not ev:
                # Honesty rule in code: a criterion only counts as triggered when the evidence is named.
                k["triggered_without_evidence"] = True
                trig = False
            elif trig and SPECULATION.search(ev):
                # "might be insufficient" is a risk, not evidence that the criterion is met.
                k["triggered_on_speculation"] = True
                trig = False
            k["triggered"] = trig
            kills.append(k)
    data["kill_criteria"] = kills
    wcm = data.get("would_change_mind")
    data["would_change_mind"] = [wcm] if isinstance(wcm, str) else [str(x) for x in as_list(wcm)]
    return data


def claims_index(ctx) -> list[dict]:
    """Numbered list of every claim in the Phase 1 evidence artifacts: C1, C2, ... (stable order)."""
    out, n = [], 0
    for step in EVIDENCE_STEPS:
        art = get_artifact(ctx, step)
        for c in (art or {}).get("claims", []) or []:
            if not isinstance(c, dict):
                continue
            n += 1
            out.append({"id": f"C{n}", "artifact": step, "claim": c.get("claim"), "source_url": c.get("source_url"),
                        "verified": c.get("verified") is True})
    return out


# ---------------------------------------------------------------- research agents (search + fetch)

STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "who", "whom", "that",
              "which", "they", "their", "them", "it", "its", "is", "are", "was", "be", "as", "from", "into", "one",
              "two", "three", "more", "most", "very", "this", "these", "those", "without", "via", "per", "lose",
              "track", "mocked", "في", "من", "على", "إلى", "الى", "عن", "مع", "و", "أو"}


def short(text: Any, words: int = 5) -> str:
    """Search keywords from a sentence: punctuation and filler words removed, first ``words`` kept."""
    toks = re.sub(r"[^\w\s\-؀-ۿ]", " ", str(text or "")).split()
    keep = [t for t in toks if t.lower() not in STOPWORDS and not t.isdigit()]
    return " ".join(keep[:words])


PRODUCT_NOUNS = {"template", "templates", "course", "ebook", "e-book", "checklist", "planner", "tracker", "spreadsheet",
                 "toolkit", "guide", "prompts", "plugin", "app", "dashboard", "workbook", "kit", "newsletter",
                 "قالب", "قوالب", "دورة", "كتاب", "دليل"}


def product_terms(card: dict, words: int = 4) -> str:
    """Search words for the product itself: tool names (capitalized words after the first) and product nouns
    from the solution, e.g. "Notion Google Sheets template". Falls back to the solution's first keywords."""
    toks = re.sub(r"[^\w\s\-؀-ۿ]", " ", str(card.get("solution") or "")).split()
    names: list[str] = []
    nouns: list[str] = []
    for i, t in enumerate(toks):
        low = t.lower()
        if low in STOPWORDS:
            continue
        bucket = nouns if low in PRODUCT_NOUNS else names if (i > 0 and t[:1].isupper()) else None
        if bucket is not None and low.rstrip("s") not in {k.lower().rstrip("s") for k in names + nouns}:
            bucket.append(t)
    keep = names[: max(1, words - len(nouns[:1]))] + nouns[:1]
    return " ".join(keep[:words]) or short(card.get("solution"), 3)


def topic_queries(card: dict) -> dict:
    """Shared keyword pieces for the research agents' searches."""
    return {"prod": product_terms(card), "cust": short(card.get("customer"), 2),
            "prob": short(card.get("problem"), 3)}


class ResearchAgent(Agent):
    """Base for the web research agents. Searches, fetches a few pages, hands them to the model as
    untrusted data, and asks for claims with exact quotes that core.claims re-checks.

    ``name`` stays empty here, so the registry never registers this base class."""

    tools = ["search", "fetch"]
    inputs = [IDEA_CARD]
    optional_inputs: list[str] = []
    max_searches = 3
    max_fetches = 3

    def queries(self, ctx, card: dict) -> list[str]:
        raise NotImplementedError

    def gather(self, ctx) -> tuple[list[dict], list[dict]]:
        card = get_artifact(ctx, IDEA_CARD) or {}
        results, pages, seen = [], [], set()
        for q in [q for q in self.queries(ctx, card) if q.strip()][: self.max_searches]:
            try:
                found = ctx.tools.search(self.name, q)
                if not found:  # an empty search (or a blocked one) must be visible in the decision log
                    ctx.log.action(self.name, "search_empty", query=q)
                for r in found:
                    if r.get("url") and r["url"] not in seen:
                        seen.add(r["url"])
                        results.append({"title": r.get("title", ""), "url": r["url"], "snippet": r.get("snippet", "")})
            except Exception as e:  # noqa: BLE001 - search failure means less evidence, not a crash
                ctx.log.action(self.name, "search_failed", query=q, error=str(e)[:200])
        for r in results[: self.max_fetches]:
            try:
                text = ctx.tools.fetch(self.name, r["url"])
            except Exception as e:  # noqa: BLE001
                ctx.log.action(self.name, "fetch_failed", sources=[r["url"]], error=str(e)[:200])
                continue
            pages.append({"url": r["url"], "text": untrusted((text or "")[:MAX_PAGE_CHARS])})
        self.result_urls = [r["url"] for r in results]  # what the agent really saw (post_process checks URLs)
        return results, pages

    def build_user_message(self, ctx) -> str:
        results, pages = self.gather(ctx)
        extra = {
            "search_results": [dict(r, snippet=str(r.get("snippet", ""))[:200]) for r in results[:6]],
            "fetched_pages": pages,
            "note": "Quotes must be copied exactly from fetched_pages text. Anything else is an ASSUMPTION.",
        }
        crit = ctx.extra.get("critique")
        if crit:
            extra["critique"] = crit
        return message(ctx, list(self.inputs) + list(self.optional_inputs), extra)

    def post_process(self, ctx, data: dict) -> dict:
        data["claims"] = norm_claims(data.get("claims"))
        if any("verified" not in c for c in data["claims"]):
            from core.claims import verify_claims
            data = verify_claims(ctx, data)
        verified = [c for c in data["claims"] if c.get("verified") is True]
        # Computed in code: the model's own opinion of the evidence does not count.
        data["insufficient_evidence"] = len(verified) == 0
        data["verified_claim_count"] = len(verified)
        return data


MOCK_BANNER = "> **MOCKED**: produced offline by MockLLM or a mock component, not by a real model run.\n\n"


def is_mocked(ctx, model) -> bool:
    return bool(getattr(ctx, "mock", False) or model == "mock-llm")


def banner(mocked: bool) -> str:
    return MOCK_BANNER if mocked else ""
