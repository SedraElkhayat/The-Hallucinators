# OWNER: M4
"""compliance_reviewer_phase4 agent for Phase 4 Commercial Setup.

Scans offer packaging and policies for banned claims and missing legal review labels.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context
from core.guardrails import check_output


class ComplianceReviewerPhase4(M4Agent):
    name = "compliance_reviewer_phase4"
    phase = 4
    step = "phase4_step4_compliance_review"
    inputs = ["phase4_step2_offer", "phase4_step3_policies"]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        issues = list(data.get("issues", [])) if isinstance(data.get("issues"), list) else []

        # Code-enforced check on policy documents
        if ctx.store.has("phase4_step3_policies"):
            pdata = ctx.store.get("phase4_step3_policies")
            docs = pdata.get("documents", [])
            for doc in docs:
                if not doc.get("needs_legal_review"):
                    issues.append(f"Document {doc.get('name')} missing needs_legal_review flag")
                guard_res = check_output(doc.get("text", ""))
                if not guard_res.allowed:
                    issues.append(f"Document {doc.get('name')} contains banned output: {guard_res.findings}")

        # Code-enforced check on offer
        if ctx.store.has("phase4_step2_offer"):
            odata = ctx.store.get("phase4_step2_offer")
            guard_pos = check_output(odata.get("positioning", ""))
            if not guard_pos.allowed:
                issues.append(f"Offer positioning contains banned output: {guard_pos.findings}")

        data["issues"] = issues
        data["verdict"] = "flagged" if issues else "pass"
        return data
