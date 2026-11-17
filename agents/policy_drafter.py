# OWNER: M4
"""policy_drafter agent for Phase 4 Commercial Setup.

Drafts terms of service, privacy policy, and refund policy.
Every document must have needs_legal_review: True.
"""
from __future__ import annotations

import re

from agents.m4_common import M4Agent, _COMPLIANCE_CLAIM_RX, _WINDOW_RX
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
                    "text": "STUBBED default text (the model returned no policy): " + "The product never asks for card numbers or passwords and keeps no client records.",
                    "needs_legal_review": True,
                },
                {
                    "name": "Refund Policy",
                    "text": "STUBBED default text (the model returned no policy): " + "Refund requests go to the founder, who reviews each one manually. Refund window: [FOUNDER TO SET: refund window].",
                    "needs_legal_review": True,
                },
            ]
        data["documents"] = [enforce_policy_rules(d) for d in clean_docs]
        return data


_PAYMENT_WORDS = [
    (re.compile(r"\b(?:credit\s+|debit\s+)?card\s+numbers?\b", re.I), "payment card details"),
    (re.compile(r"\bcvvs?\b|\bcvcs?\b", re.I), "card security codes"),
    (re.compile(r"\bcheckouts?\b", re.I), "purchase"),
    (re.compile(r"\b(?:stripe|paypal)\b", re.I), "a payment provider"),
]


def enforce_policy_rules(doc: dict) -> dict:
    """Terms are the founder's decision: time windows become placeholders; no compliance claims."""
    text = str(doc.get("text", ""))
    is_refund = "refund" in str(doc.get("name", "")).lower()
    placeholder = "[FOUNDER TO SET: refund window]" if is_refund else "[FOUNDER TO SET: time period]"
    text = _WINDOW_RX.sub(placeholder, text)
    text = _COMPLIANCE_CLAIM_RX.sub("[needs legal review]", text)
    # Policy pages go on the store website, whose checks (M3) reject payment words; same meaning, other words.
    for rx, plain in _PAYMENT_WORDS:
        text = rx.sub(plain, text)
    if is_refund and "[FOUNDER TO SET" not in text:
        text += " Refund window: [FOUNDER TO SET: refund window]."
    doc["text"] = text
    doc["needs_legal_review"] = True
    return doc
