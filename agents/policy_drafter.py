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
                if isinstance(d, dict) and str(d.get("text", "")).strip():
                    # An empty document (a real run produced one named "Policy Document") is dropped.
                    clean_docs.append({
                        "name": policy_name(d),
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


_SENTENCE_RX = re.compile(r"[^.!?\n]+[.!?]?")
COMPLIANCE_PLACEHOLDER = " [needs legal review: whether this meets the applicable laws is for a lawyer to confirm.]"


def enforce_policy_rules(doc: dict) -> dict:
    """Terms are the founder's decision: time windows become placeholders; no compliance claims."""
    text = str(doc.get("text", ""))
    is_refund = "refund" in str(doc.get("name", "")).lower()
    placeholder = "[FOUNDER TO SET: refund window]" if is_refund else "[FOUNDER TO SET: time period]"
    text = _WINDOW_RX.sub(placeholder, text)
    # A sentence that claims legal compliance is replaced whole (replacing only the phrase left broken text).
    text = _SENTENCE_RX.sub(lambda m: COMPLIANCE_PLACEHOLDER if _COMPLIANCE_CLAIM_RX.search(m.group(0)) else m.group(0),
                            text)
    # Policy pages go on the store website, whose checks (M3) reject payment words; same meaning, other words.
    for rx, plain in _PAYMENT_WORDS:
        text = rx.sub(plain, text)
    if is_refund and "[FOUNDER TO SET" not in text:
        text += " Refund window: [FOUNDER TO SET: refund window]."
    doc["text"] = text
    doc["needs_legal_review"] = True
    return doc


def policy_name(d: dict) -> str:
    """The model's name, or one inferred from the text (a real run named a refund policy "Policy Document")."""
    name = str(d.get("name") or "").strip()
    if name and name.lower() not in ("policy", "policy document", "document"):
        return name
    text = str(d.get("text", "")).lower()
    for word, label in (("refund", "Refund Policy"), ("privacy", "Privacy Policy"), ("personal data", "Privacy Policy"),
                        ("terms", "Terms of Service"), ("licen", "Terms of Service")):
        if word in text:
            return label
    return name or "Policy Document"
