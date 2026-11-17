# OWNER: M4
"""compliance_reviewer_phase5 agent for Phase 5 Launch.

Audits store page and launch post drafts for fake proof, timers, urgency, and unapproved releases.
"""
from __future__ import annotations

import re

from agents.m4_common import M4Agent
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
        issues = list(data.get("issues", [])) if isinstance(data.get("issues"), list) else []

        # Audit Store Page HTML if present
        html_file = ctx.out_dir / "phase5_step2_store_page.html"
        if html_file.exists():
            html_content = html_file.read_text(encoding="utf-8")
            if "<script" in html_content.lower():
                issues.append("Store page contains disallowed <script> tag")
            if re.search(r"\b(?:countdown|timer|only \d+ left)\b", html_content, re.I):
                issues.append("Store page contains disallowed timer or artificial scarcity counter")
            if "MOCKED checkout: no real payment" not in html_content:
                issues.append("Store page missing required 'MOCKED checkout: no real payment' button label")

        # Audit launch posts
        if ctx.store.has("phase5_step3_launch_posts"):
            posts_data = ctx.store.get("phase5_step3_launch_posts")
            for p in posts_data.get("posts", []):
                text = p.get("text", "")
                if p.get("posted"):
                    issues.append(f"Post for {p.get('channel')} marked posted; system must never auto-post")
                guard_res = check_output(text)
                if not guard_res.allowed:
                    issues.append(f"Post for {p.get('channel')} contains banned content: {guard_res.findings}")

        data["issues"] = issues
        data["verdict"] = "flagged" if issues else "pass"
        return data
