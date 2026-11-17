# OWNER: M4
"""compliance_reviewer_phase5 agent for Phase 5 Launch.

Audits store page and launch post drafts for fake proof, timers, urgency, and unapproved releases.
"""
from __future__ import annotations

import re

from agents.m4_common import M4Agent, launch_copy_violations, normalize_critique
from core.contracts import Context
from core.guardrails import check_output


class ComplianceReviewerPhase5(M4Agent):
    name = "compliance_reviewer_phase5"
    phase = 5
    step = "phase5_step4_launch_review"
    inputs = ["phase5_step2_store_page", "phase5_step3_launch_posts"]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        code_issues: list[str] = []
        html_file = ctx.out_dir / "phase5_step2_store_page.html"
        if html_file.exists():
            page = html_file.read_text(encoding="utf-8")
            if "<script" in page.lower():
                code_issues.append("store page: contains a <script> tag")
            if re.search(r"\b(?:countdown|timer|only \d+ left)\b", page, re.I):
                code_issues.append("store page: timer or scarcity counter")
            if "MOCKED checkout: no real payment" not in page:
                code_issues.append("store page: buy button must say 'MOCKED checkout: no real payment'")
        if ctx.store.has("phase5_step2_store_page"):
            sp = ctx.store.get("phase5_step2_store_page")
            sc = (sp.get("site") or {}).get("site_checks")
            if isinstance(sc, dict) and not sc.get("passed"):
                code_issues += [f"store site: {f}" for f in sc.get("failures") or ["site checks failed"]]
            for t in [sp.get("title", ""), sp.get("description", "")] + list(sp.get("bullets") or []):
                v = launch_copy_violations(str(t))
                if v:
                    code_issues.append(f"store page: {v} in '{str(t)[:60]}'")
        if ctx.store.has("phase5_step3_launch_posts"):
            for p in ctx.store.get("phase5_step3_launch_posts").get("posts", []):
                ch = p.get("channel")
                if p.get("posted"):
                    code_issues.append(f"post for {ch}: marked posted; the system never posts")
                if p.get("status") == "approved":
                    v = launch_copy_violations(str(p.get("text", "")))
                    if v:
                        code_issues.append(f"post for {ch}: {v}")
        data = normalize_critique(data, code_issues)
        data.pop("mocked", None)
        return data
