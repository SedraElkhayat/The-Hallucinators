# OWNER: M4
"""launch_post_drafter agent for Phase 5 Launch.

Drafts launch posts for founder review.
Each post is run through check_release and ctx.approvals.request("launch_post", ...).
Nothing is ever posted automatically.
"""
from __future__ import annotations

from agents.base import BLOCK_MARK
from agents.m4_common import M4Agent, launch_copy_violations
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

                # Code rules first: banned claims, counts, testimonials, income/time-saved numbers, founder signature.
                guard_res = check_release(raw_text)
                violations = launch_copy_violations(raw_text)
                if not guard_res.allowed or violations:
                    # Blocked drafts never reach the founder's approval queue and are never posted.
                    processed_posts.append({
                        "channel": channel,
                        "text": f"{BLOCK_MARK} {sorted(set(violations + guard_res.findings))}",
                        "status": "blocked",
                        "guard_findings": sorted(set(violations + guard_res.findings)),
                        "posted": False,
                    })
                    ctx.log.action(self.name, "launch_post_blocked", outcome="blocked",
                                   reasons=sorted(set(violations + guard_res.findings)))
                    continue
                release_text = guard_res.text

                # Founder approve/reject for each post draft; nothing is ever posted by the system.
                title = f"Launch post {idx} for {channel}"
                approved = ctx.approvals.request("launch_post", title, release_text, self.phase)
                if approved:
                    # Released = the founder may post it; the system itself never posts.
                    ctx.approvals.release("launch_post", title, release_text, self.phase)

                processed_posts.append({
                    "channel": channel,
                    "text": release_text,
                    "status": "approved" if approved else "rejected",
                    "guard_findings": [],
                    "posted": False,
                })

        if not processed_posts:
            # Fallback default draft
            default_text = "DRAFT: prepared for founder review\nSTUBBED fallback text (the model returned no posts). Announcing our new Notion workflow pack for freelance designers. Built for tracking revisions and invoices without complexity."
            approved = ctx.approvals.request("launch_post", "Default Launch Post", default_text, self.phase)
            processed_posts = [{
                "channel": "LinkedIn",
                "text": default_text,
                "status": "approved" if approved else "rejected",
                "guard_findings": [],
                "posted": False,
            }]

        data["posts"] = processed_posts
        data["posted"] = False  # nothing is ever posted by the system
        data.pop("mocked", None)
        return data
