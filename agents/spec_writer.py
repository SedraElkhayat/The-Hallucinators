"""spec_writer: MVP spec of the founder website.

The acceptance tests are STRUCTURAL and set in code (M1 review, Tuesday 14:54): the page file exists, every required
section exists, and the demo sign-up label is shown. Exact marketing sentences and literal HTML from the model were
brittle (a real run passed 0 of 5), so the model's own tests are recorded in ``dropped_tests`` and never run.
"""
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_CLARIFICATION, P1_IDEA_CARD, P2_CANVAS, P2_PLAN,
                              P2_REPORT, P3_SPEC, safe_rel_path)
from agents.m3_site import DEMO_FORM_LABEL, PHASE3_POLICIES, PHASE3_PRICE, REQUIRED_SECTIONS

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
_LATER_PHASE = re.compile(r"[$\u20ac\u00a3]|\b(usd|egp|eur|gbp|dollars?|price|prices|pricing|privacy|terms|refund|"
                          r"refunds|policy|policies)\b", re.I)


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


STRUCTURAL_REASON = "replaced by the structural checks set in code (exact marketing text is brittle)"
SECTION_NAMES = {"value-proposition": "value proposition", "features": "features", "evidence": "evidence",
                 "price": "price", "faq": "FAQ", "policies": "policy links", "signup": "sign-up box"}


def structural_acceptance_tests() -> list:
    """The page exists, each required section exists (by its id in the template), the demo label is visible."""
    tests = [{"id": "AT1", "description": "The website page exists",
              "check": {"type": "file_exists", "path": "index.html", "text": ""}}]
    for n, sid in enumerate(REQUIRED_SECTIONS, 2):
        tests.append({"id": f"AT{n}", "description": f"The page has the {SECTION_NAMES.get(sid, sid)} section",
                      "check": {"type": "text_contains", "path": "index.html", "text": f'id="{sid}"'}})
    tests.append({"id": f"AT{len(tests) + 1}", "description": "The sign-up box shows the demo label",
                  "check": {"type": "text_contains", "path": "index.html", "text": DEMO_FORM_LABEL}})
    return tests


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
        dropped += [{"id": t.get("id"), "text": (t.get("check") or {}).get("text") or (t.get("check") or {}).get("path", ""),
                     "reason": STRUCTURAL_REASON} for t in kept]
        data["acceptance_tests"] = structural_acceptance_tests()
        data["dropped_tests"] = dropped
        return data
