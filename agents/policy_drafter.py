# OWNER: M4
"""policy_drafter agent for Phase 4 Commercial Setup.

Drafts terms of service, privacy policy, and refund policy.
Every document must have needs_legal_review: True.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context


class PolicyDrafter(M4Agent):
    name = "policy_drafter"
    phase = 4
    step = "phase4_step3_policies"
    inputs = ["phase4_step2_offer"]
    tools = []
    required_keys = ["documents"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        docs = data.get("documents")
        clean_docs = []
        if isinstance(docs, list):
            for d in docs:
                if isinstance(d, dict):
                    clean_docs.append({
                        "name": str(d.get("name", "Policy Document")),
                        "text": str(d.get("text", "")),
                        "needs_legal_review": True,
                    })
        if not clean_docs:
            clean_docs = [
                {
                    "name": "Terms of Service",
                    "text": "STUBBED default text (the model returned no policy): " + "Single user license for digital template. Redistribution is prohibited.",
                    "needs_legal_review": True,
                },
                {
                    "name": "Privacy Policy",
                    "text": "STUBBED default text (the model returned no policy): " + "We do not store passwords, card numbers or client records.",
                    "needs_legal_review": True,
                },
                {
                    "name": "Refund Policy",
                    "text": "STUBBED default text (the model returned no policy): " + "Refund requests go to the founder, who reviews each one manually.",
                    "needs_legal_review": True,
                },
            ]
        data["documents"] = clean_docs
        return data
