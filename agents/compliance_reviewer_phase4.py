# OWNER: M4
"""compliance_reviewer_phase4 agent for Phase 4 Commercial Setup.

Scans offer packaging and policies for banned claims and missing legal review labels.
"""
from __future__ import annotations

from agents.m4_common import (M4Agent, draft_strings, normalize_critique, verify_model_issues,
                              _COMPLIANCE_CLAIM_RX, _WINDOW_RX)
from core.contracts import Context
from core.guardrails import check_output


class ComplianceReviewerPhase4(M4Agent):
    name = "compliance_reviewer_phase4"
    phase = 4
    step = "phase4_step4_compliance_review"
    inputs = ["phase4_step1_pricing", "phase4_step2_offer", "phase4_step3_policies"]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        code_issues: list[str] = []
        if ctx.store.has("phase4_step3_policies"):
            for doc in ctx.store.get("phase4_step3_policies").get("documents", []):
                name = doc.get("name")
                text = str(doc.get("text", ""))
                if doc.get("needs_legal_review") is not True:
                    code_issues.append(f"{name}: needs_legal_review must be true")
                res = check_output(text)
                if not res.allowed:
                    code_issues.append(f"{name}: banned content {res.findings}")
                if _COMPLIANCE_CLAIM_RX.search(text):
                    code_issues.append(f"{name}: claims legal compliance; only a lawyer can confirm that")
                if "refund" in str(name).lower() and _WINDOW_RX.search(text):
                    code_issues.append(f"{name}: states a refund window; the founder sets it ([FOUNDER TO SET: refund window])")
        else:
            code_issues.append("phase4_step3_policies is missing")
        if ctx.store.has("phase4_step2_offer"):
            offer = ctx.store.get("phase4_step2_offer")
            texts = [str(offer.get("positioning", ""))]
            texts += [str(i) for t in offer.get("tiers", []) for i in (t.get("includes") or [])]
            for t in texts:
                res = check_output(t)
                if not res.allowed:
                    code_issues.append(f"phase4_step2_offer: banned content {res.findings} in '{t[:60]}'")
        if ctx.store.has("phase4_step1_pricing"):
            pr = ctx.store.get("phase4_step1_pricing")
            if not pr.get("comparable_claims") and pr.get("is_assumption") is not True:
                code_issues.append("phase4_step1_pricing: price has no verified comparable and is not labeled an assumption")
        data = verify_model_issues(data, draft_strings(ctx, *self.inputs))
        data = normalize_critique(data, code_issues)
        data.pop("mocked", None)
        return data
