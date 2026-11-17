"""risk_analyst: adversarial risks, kill criteria (marked triggered when the evidence meets them)."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_SKEPTIC, P2_ASSUMPTIONS, P2_CANVAS,
                              P2_COMPETITOR_ANALYSIS, P2_PLAN, P2_RESULTS, P2_RISKS, get_artifact)


class RiskAnalyst(M3InputsMixin, Agent):
    name = "risk_analyst"
    phase = 2
    step = P2_RISKS
    inputs = [P2_RESULTS, P2_PLAN, P2_CANVAS, P2_COMPETITOR_ANALYSIS, P2_ASSUMPTIONS]
    optional_inputs = [P1_SKEPTIC]
    tools = []
    required_keys = ["risks", "kill_criteria", "would_change_mind"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        risks = []
        for r in data.get("risks") or []:
            if isinstance(r, str):
                r = {"text": r, "severity": "medium"}
            if isinstance(r, dict) and r.get("text"):
                sev = str(r.get("severity", "medium")).lower()
                r["severity"] = sev if sev in ("high", "medium", "low") else "medium"
                risks.append(r)
        data["risks"] = risks
        kills = []
        for k in data.get("kill_criteria") or []:
            if isinstance(k, str):
                k = {"text": k, "triggered": False}
            if isinstance(k, dict) and k.get("text"):
                k["triggered"] = k.get("triggered") is True
                kills.append(k)
        # The demand rule is checked in code: a ratio below 0.2 of the pre-set target is a kill criterion.
        results = get_artifact(ctx, P2_RESULTS)
        if results is not None and isinstance(results.get("ratio"), (int, float)):
            ratio = float(results["ratio"])
            if ratio < 0.2 and not any(k["triggered"] for k in kills):
                kills.append({"text": f"Demand ratio {ratio} is below 0.2 of the target set before the test "
                                      f"(provenance {results.get('provenance', 'unknown')})",
                              "triggered": True, "checked_in_code": True})
        data["kill_criteria"] = kills
        wcm = data.get("would_change_mind")
        data["would_change_mind"] = [wcm] if isinstance(wcm, str) else [str(x) for x in (wcm or [])]
        return data
