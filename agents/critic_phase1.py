"""critic_phase1: review the Discover report for unsupported claims, flattery and missing risks.
must_fix for any unsupported factual statement or flattery. Code adds must_fix issues for praise words and
for unsupported confidence; any must_fix forces verdict "revise" (up to 2 revision rounds)."""
import re

from agents.base import Agent
from agents.m2_common import (COMPETITORS, CRITIQUE, DEMAND, MARKET, OPPORTUNITIES, REPORT, SKEPTIC, as_list, claims_index,
                              get_artifact, message)

PRAISE = re.compile(r"\b(excellent|amazing|fantastic|brilliant|incredible|huge potential|massive opportunity|"
                    r"perfect fit|can't miss|will definitely|outstanding|exceptional|"
                    r"very promising|highly promising)\b", re.I)


class CriticPhase1(Agent):
    name = "critic_phase1"
    phase = 1
    step = CRITIQUE
    inputs = [REPORT]
    optional_inputs = [OPPORTUNITIES, MARKET, DEMAND, COMPETITORS, SKEPTIC]
    tools: list = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        return message(ctx, self.inputs + self.optional_inputs, {"claims_index": claims_index(ctx)},
                       brief=False, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        issues = []
        for i in as_list(data.get("issues")):
            if isinstance(i, str):
                i = {"severity": "should_fix", "text": i}
            if isinstance(i, dict) and str(i.get("text", "")).strip():
                i["severity"] = "must_fix" if i.get("severity") == "must_fix" else "should_fix"
                issues.append(i)
        report = get_artifact(ctx, REPORT) or {}
        texts = [str(report.get("summary", ""))] + [str(f.get("text", "")) for f in report.get("findings") or []
                                                     if isinstance(f, dict)]
        for t in texts:
            m = PRAISE.search(t)
            if m:
                issues.append({"severity": "must_fix", "found_in_code": True,
                               "text": f"Praise without evidence: '{m.group(0)}' in \"{t[:120]}\""})
        verified = sum(1 for c in claims_index(ctx) if c["verified"])
        if report.get("confidence") == "high" and verified < 5:
            issues.append({"severity": "must_fix", "found_in_code": True,
                           "text": f"Confidence 'high' with only {verified} verified claims."})
        data["issues"] = issues
        v = str(data.get("verdict", "ok")).lower()
        data["verdict"] = "revise" if any(i["severity"] == "must_fix" for i in issues) else (
            v if v in ("ok", "revise") else "ok")
        return data
