# OWNER: M4
"""launch_post_drafter agent for Phase 5 Launch.

Drafts launch posts for founder review.
Each post is run through check_release and ctx.approvals.request("launch_post", ...).
Nothing is ever posted automatically.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context
from core.guardrails import check_release


class LaunchPostDrafter(M4Agent):
    name = "launch_post_drafter"
    phase = 5
    step = "phase5_step3_launch_posts"
    inputs = ["phase5_step1_channel_plan", "phase4_step2_offer"]
    tools = []
    required_keys = ["posts"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        raw_posts = data.get("posts")
        processed_posts = []

        if isinstance(raw_posts, list):
            for idx, p in enumerate(raw_posts, 1):
                if not isinstance(p, dict):
                    continue
                channel = str(p.get("channel", "Community"))
                raw_text = str(p.get("text", ""))

                # Pass through check_release
                guard_res = check_release(raw_text)
                release_text = guard_res.text

                # Request founder approval for each post draft
                approved = ctx.approvals.request(
                    "launch_post",
                    f"Launch post {idx} for {channel}",
                    release_text,
                    self.phase
                )

                processed_posts.append({
                    "channel": channel,
                    "text": release_text,
                    "status": "approved" if approved else "rejected",
                    "guard_findings": guard_res.findings,
                    "posted": False,  # Nothing is ever posted
                })

        if not processed_posts:
            # Fallback default draft
            default_text = "DRAFT: prepared for founder review\nAnnouncing our new Notion workflow pack for freelance designers. Built for tracking revisions and invoices without complexity."
            approved = ctx.approvals.request("launch_post", "Default Launch Post", default_text, self.phase)
            processed_posts = [{
                "channel": "LinkedIn",
                "text": default_text,
                "status": "approved" if approved else "rejected",
                "guard_findings": [],
                "posted": False,
            }]

        data["posts"] = processed_posts
        data["mocked"] = True
        return data
