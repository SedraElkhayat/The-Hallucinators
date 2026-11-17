# OWNER: M4
"""Phase 4: Commercial Setup (pricing, offer packaging, policies, compliance review).

Founder keys used in this phase: None (fully automated commercial setup drafting).
"""
from __future__ import annotations

import re
from pathlib import Path

from core.contracts import Context
from agents.m4_common import count_must_fix
from core.guardrails import check_output
from gates import Check

PHASE = 4
STAGES: list[list[str]] = [
    ["pricing_analyst"],
    ["offer_packager"],
    ["policy_drafter"],
    ["compliance_reviewer_phase4"],
]
REVISE = None
PIVOT_TO = 2

PAYMENT_SDKS = ("stripe", "paypal", "paymob", "braintree", "square", "paddle", "checkout_sdk")


def gate_checks(ctx: Context) -> list[Check]:
    return [
        Check("chk_p4_price", "price_sourced_or_labeled", ">=", 1.0, "pivot"),
        Check("chk_p4_policies", "policies_labeled", ">=", 1.0, "repeat"),
        Check("chk_p4_claims", "banned_claims", "<=", 0.0, "repeat"),
        Check("chk_p4_no_payment_sdk", "payment_code_present", "<=", 0.0, "stop"),
        Check("chk_p4_compliance", "compliance_must_fix", "<=", 0.0, "repeat"),
    ]


def measure(ctx: Context) -> dict:
    price_ok = 0
    if ctx.store.has("phase4_step1_pricing"):
        pdata = ctx.store.get("phase4_step1_pricing")
        claims = pdata.get("comparable_claims", [])
        is_assump = pdata.get("is_assumption", False)
        if claims or is_assump:
            price_ok = 1

    policies_ok = 0
    banned_claims = 0
    if ctx.store.has("phase4_step3_policies"):
        pol_data = ctx.store.get("phase4_step3_policies")
        docs = pol_data.get("documents", [])
        if docs and all(d.get("needs_legal_review") is True for d in docs):
            policies_ok = 1
        for d in docs:
            gres = check_output(d.get("text", ""))
            if not gres.allowed:
                banned_claims += len(gres.findings)

    if ctx.store.has("phase4_step2_offer"):
        off_data = ctx.store.get("phase4_step2_offer")
        gres = check_output(off_data.get("positioning", ""))
        if not gres.allowed:
            banned_claims += len(gres.findings)
        for t in off_data.get("tiers", []):
            for inc in t.get("includes", []):
                gres = check_output(inc)
                if not gres.allowed:
                    banned_claims += len(gres.findings)

    # Check for payment SDKs in requirements.txt or source imports
    payment_code_present = 0
    req_file = Path("requirements.txt")
    if req_file.exists():
        req_text = req_file.read_text(encoding="utf-8").lower()
        for sdk in PAYMENT_SDKS:
            if re.search(r"\b" + re.escape(sdk) + r"\b", req_text):
                payment_code_present += 1

    # compliance_reviewer_phase4 critique: any must_fix issue sends the phase back (repeat)
    compliance_must_fix = 0
    if ctx.store.has("phase4_step4_compliance_review"):
        compliance_must_fix = count_must_fix(ctx.store.get("phase4_step4_compliance_review"))

    return {
        "compliance_must_fix": compliance_must_fix,
        "price_sourced_or_labeled": price_ok,
        "policies_labeled": policies_ok,
        "banned_claims": banned_claims,
        "payment_code_present": payment_code_present,
    }
