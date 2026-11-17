"""spec_writer: MVP spec of a small static product with acceptance tests that code can run."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_CLARIFICATION, P1_IDEA_CARD, P2_CANVAS, P2_PLAN,
                              P2_REPORT, P3_SPEC, safe_rel_path)

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
        data["acceptance_tests"] = normalize_acceptance_tests(data.get("acceptance_tests"))
        return data
