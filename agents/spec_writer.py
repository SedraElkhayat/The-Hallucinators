"""spec_writer: MVP spec of a small static product with acceptance tests that code can run."""
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_CLARIFICATION, P1_IDEA_CARD, P2_CANVAS, P2_PLAN,
                              P2_REPORT, P3_SPEC, safe_rel_path)
from agents.m3_site import PHASE3_POLICIES, PHASE3_PRICE

CHECK_TYPES = ("file_exists", "text_contains")


def normalize_acceptance_tests(tests) -> list:
    out, seen = [], set()
    for n, t in enumerate(tests or [], 1):
        if not isinstance(t, dict):
            continue
        check = t.get("check") if isinstance(t.get("check"), dict) else {}
        tid = str(t.get("id") or f"AT{n}")
        while tid in seen:
            tid += "b"
        seen.add(tid)
        ctype = str(check.get("type", "")).strip()
        raw_path = check.get("path", "")
        path = safe_rel_path(raw_path)
        out.append({
            "id": tid,
            "description": str(t.get("description", "")),
            # Unsafe paths and unknown types are kept as written, so QA reports them as failures.
            "check": {"type": ctype, "path": path if path else str(raw_path), "text": str(check.get("text") or "")},
        })
    return out


# Price and policies only appear from Phase 4 and 5 (CONTEXT 4b), so a Phase 3 page can never pass a test for them.
_LATER_PHASE = re.compile(r"[$\u20ac\u00a3]|\b(usd|egp|eur|gbp|dollars?|price|prices|pricing|privacy|terms|refund|refunds|policy|policies)\b", re.I)


def drop_later_phase_tests(tests) -> tuple:
    """Split acceptance tests into (kept, dropped). Only text_contains tests can be dropped."""
    kept, dropped = [], []
    for t in tests or []:
        check = t.get("check") or {}
        text = str(check.get("text") or "")
        # The Phase 3 page does show the two placeholders ("Price: set in Phase 4", "Policies drafted in Phase 4").
        on_page = any(" ".join(text.lower().split()) in p.lower() for p in (PHASE3_PRICE, PHASE3_POLICIES))
        if check.get("type") == "text_contains" and _LATER_PHASE.search(text) and not on_page:
            dropped.append({"id": t.get("id"), "text": text,
                            "reason": "price or policy text appears only from Phase 4 and 5, so Phase 3 cannot pass it"})
        else:
            kept.append(t)
    return kept, dropped


class SpecWriter(M3InputsMixin, Agent):
    name = "spec_writer"
    phase = 3
    step = P3_SPEC
    inputs = [P2_CANVAS, P2_REPORT, P2_PLAN, P1_IDEA_CARD, P1_CLARIFICATION]
    tools = []
    required_keys = ["mvp_scope", "user_stories", "acceptance_tests", "out_of_scope"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        for k in ("mvp_scope", "user_stories", "out_of_scope"):
            v = data.get(k)
            data[k] = [v] if isinstance(v, str) else [str(x) for x in (v or [])]
        kept, dropped = drop_later_phase_tests(normalize_acceptance_tests(data.get("acceptance_tests")))
        data["acceptance_tests"] = kept
        data["dropped_tests"] = dropped
        return data
