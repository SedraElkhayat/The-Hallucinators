# OWNER: M4
"""compliance_reviewer_phase4 agent for Phase 4 Commercial Setup.

Scans offer packaging and policies for banned claims and missing legal review labels.
"""
from __future__ import annotations

import re

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
        docs = ctx.store.get("phase4_step3_policies").get("documents", []) if ctx.store.has("phase4_step3_policies") else []
        data = downgrade_legal_review_only(ctx, self.name, data, docs)
        data = normalize_critique(data, code_issues)
        data.pop("mocked", None)
        return data


# A finding that only asks for legal review is already handled when the document carries needs_legal_review: true
# (a real run held Gate 4 on "Privacy Policy document needs legal review"). Real legal or honesty problems stay must_fix.
_LEGAL_REVIEW_RX = re.compile(r"legal(?:ly)?\W+review|review(?:ed)?\W+by\W+(?:a\W+)?(?:lawyer|attorney|legal)|"
                              r"lawyer|attorney|legal\W+counsel|needs[_ ]legal[_ ]review", re.I)
_REAL_PROBLEM_RX = re.compile(
    r"promis|guarant|\bincome|\bearn|profit|\broi\b|success|fake|testimonial|reviews?\W+from|countdown|"
    r"complian|\bcomply|gdpr|ccpa|violat|illegal|unlawful|mislead|decept|\bfalse|inaccurate|"
    r"missing|\black|without|\bomit|does\W+not|doesn't|\bno\W+(?:refund|contact|mention)|"
    r"window|\bdays?\b|\bfees?\b|\bprice|\bbanned|impersonat|\bposes?\b|\bposing", re.I)
# "A policy without needs_legal_review: true": the flag said to be missing. Only false when code sees that EVERY
# document has the flag (a rerun held Gate 4 on three of these, since "without" counts as a real problem above).
_MISSING_FLAG_RX = re.compile(
    r"\b(?:without|missing|lacks?|lacking|no|not\W+(?:marked|flagged|labell?ed)(?:\W+(?:with|as))?)"
    r"\W+(?:(?:the|a|an)\W+)?needs[_ ]legal[_ ]review(?:\W+(?:set\W+to\W+)?true)?(?:\W+(?:flag|label|field))?|"
    r"needs[_ ]legal[_ ]review\W+(?:(?:flag|label|field)\W+)?(?:is\W+|=\W*)?"
    r"(?:false|missing|absent|not\W+(?:set|true|present))", re.I)


def downgrade_legal_review_only(ctx, agent: str, data: dict, documents: list) -> dict:
    flagged = {str(d.get("name", "")).strip().lower(): d.get("needs_legal_review") is True
               for d in documents if isinstance(d, dict) and d.get("name")}
    if not flagged:
        return data
    out = []
    for i in data.get("issues") or []:
        if isinstance(i, dict) and str(i.get("severity", "")).lower().replace("-", "_") == "must_fix":
            text = str(i.get("text", ""))
            all_flagged = all(flagged.values())
            missing_flag = all_flagged and bool(_MISSING_FLAG_RX.search(text))
            rest = _LEGAL_REVIEW_RX.sub(" ", _MISSING_FLAG_RX.sub(" ", text) if missing_flag else text)
            if _LEGAL_REVIEW_RX.search(text) and not _REAL_PROBLEM_RX.search(rest):
                hay = (text + " " + str(i.get("quote", ""))).lower()
                named = [n for n in flagged if n and (n in hay or n.replace(" ", "_") in hay)]
                docs_ok = all_flagged if missing_flag else (all(flagged[n] for n in named) if named else all_flagged)
                if docs_ok:
                    reason = ("says a policy lacks needs_legal_review, but every policy document has "
                              "needs_legal_review: true" if missing_flag else
                              "only asks for legal review, and the document already has needs_legal_review: true "
                              "(a lawyer reviews it before publishing)")
                    # normalize_critique keeps only severity/text/quote, so the reason goes in the text too.
                    i = {**i, "severity": "should_fix", "text": f"{text} [downgraded from must_fix: {reason}]"}
                    data.setdefault("downgraded", []).append({"issue": text, "reason": reason})
                    ctx.log.action(agent, "issue_downgraded", sources=[], reason=reason, issue=text[:200])
        out.append(i)
    data["issues"] = out
    if not any(isinstance(i, dict) and str(i.get("severity", "")).lower() == "must_fix" for i in out):
        data["verdict"] = "ok"
    return data
