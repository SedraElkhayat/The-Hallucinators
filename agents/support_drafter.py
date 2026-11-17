# OWNER: M4
"""support_drafter agent for Phase 6 Operate and Learn.

Drafts honest replies to user questions provided by the founder.
Money, account and legal topics escalate to the founder; never promises refunds.
"""
from __future__ import annotations

import re

from agents.m4_common import M4Agent
from core.contracts import Context

_ESCALATE_KEYWORDS = re.compile(r"(?i)\b(?:money|refund|charge|payment|card|billing|cancel|lawsuit|legal|account)\b|استرداد|فلوس|دفع|حساب|قانوني")


class SupportDrafter(M4Agent):
    name = "support_drafter"
    phase = 6
    step = "phase6_step1_support_replies"
    inputs = []
    tools = []
    required_keys = ["replies"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def build_user_message(self, ctx: Context) -> str:
        questions = ""
        try:
            questions = ctx.founder.provide("support_questions", "Provide support questions to draft replies for")
        except Exception:
            questions = "1) Can I use the template in Arabic? 2) I bought it twice by mistake, can I get my money back? 3) Does it work on the Notion free plan?"
        payload = {
            "brief": ctx.brief,
            "support_questions": questions,
        }
        return f"<data>\n{payload}\n</data>\nDraft replies to each question. If a question involves payments, refunds, accounts, or legal topics, mark escalate: true and escalate to founder."

    def post_process(self, ctx: Context, data: dict) -> dict:
        raw_replies = data.get("replies")
        clean_replies = []
        if isinstance(raw_replies, list):
            for r in raw_replies:
                if isinstance(r, dict):
                    q = str(r.get("question", ""))
                    ans = str(r.get("reply", ""))
                    esc = bool(r.get("escalate", False))
                    # Code enforcement: if question or reply involves money/refund/account/legal, must escalate
                    if _ESCALATE_KEYWORDS.search(q) or _ESCALATE_KEYWORDS.search(ans):
                        esc = True
                    # Never promise refund directly in reply
                    if re.search(r"(?i)\b(?:we will refund|refund processed|guaranteed refund)\b", ans):
                        ans = "I have escalated your refund request to the founder for manual review and processing."
                        esc = True
                    clean_replies.append({
                        "question": q,
                        "reply": ans,
                        "escalate": esc,
                    })

        if not clean_replies:
            clean_replies = [
                {
                    "question": "Can I use the template in Arabic?",
                    "reply": "Yes, all dashboards and sheets include Arabic and English translations.",
                    "escalate": False,
                },
                {
                    "question": "I bought it twice by mistake, can I get my money back?",
                    "reply": "Escalating your refund request directly to the founder for processing.",
                    "escalate": True,
                },
                {
                    "question": "Does it work on the Notion free plan?",
                    "reply": "Yes, it works smoothly on the Notion free tier without any paid Notion subscription.",
                    "escalate": False,
                },
            ]

        data["replies"] = clean_replies
        data["mocked"] = True
        return data
