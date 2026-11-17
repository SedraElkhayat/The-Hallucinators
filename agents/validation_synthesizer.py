"""validation_synthesizer: hedged Phase 2 report; includes the risk findings; never picks the verdict."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P2_ASSUMPTIONS, P2_CANVAS, P2_COMPETITOR_ANALYSIS,
                              P2_PLAN, P2_REPORT, P2_RESULTS, P2_RISKS, P2_SCORECARD, get_artifact)

_VERDICT_KEYS = ("verdict", "recommendation", "outcome", "decision", "gate_verdict")


class ValidationSynthesizer(M3InputsMixin, Agent):
    name = "validation_synthesizer"
    phase = 2
    step = P2_REPORT
    inputs = [P2_COMPETITOR_ANALYSIS, P2_CANVAS, P2_PLAN, P2_RESULTS, P2_ASSUMPTIONS, P2_RISKS, P2_SCORECARD]
    tools = []
    required_keys = ["summary", "findings", "assumptions", "limitations", "confidence", "verdict_inputs"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        for k in _VERDICT_KEYS:  # the gate decides in code
            data.pop(k, None)
        conf = str(data.get("confidence", "low")).lower()
        data["confidence"] = conf if conf in ("low", "medium", "high") else "low"
        for k in ("assumptions", "limitations"):
            v = data.get(k)
            data[k] = [v] if isinstance(v, str) else [str(x) for x in (v or [])]
        findings = []
        for f in data.get("findings") or []:
            if isinstance(f, str):
                f = {"text": f, "assumption": True}
            if isinstance(f, dict) and f.get("text"):
                if not f.get("claim_ids"):
                    f.pop("claim_ids", None)
                    f["assumption"] = True
                findings.append(f)

        # Make sure the Risk Analyst's high risks and triggered kill criteria are in the report.
        risks = get_artifact(ctx, P2_RISKS) or {}
        texts = " ".join(f["text"] for f in findings).lower()
        for r in risks.get("risks") or []:
            if isinstance(r, dict) and r.get("severity") == "high" and str(r.get("text", "")).lower()[:40] not in texts:
                findings.append({"text": f"Risk (high): {r['text']}", "claim_ids": [P2_RISKS]})
        triggered = [k["text"] for k in risks.get("kill_criteria") or [] if isinstance(k, dict) and k.get("triggered")]
        for t in triggered:
            if t.lower()[:40] not in texts:
                findings.append({"text": f"Kill criterion triggered: {t}", "claim_ids": [P2_RISKS]})
        data["findings"] = findings

        # verdict_inputs are facts taken from artifacts by code, so they cannot drift.
        results = get_artifact(ctx, P2_RESULTS) or {}
        card = (get_artifact(ctx, P2_SCORECARD) or {}).get("dimensions") or {}
        assumptions = get_artifact(ctx, P2_ASSUMPTIONS) or {}
        data["verdict_inputs"] = {
            "demand_ratio": results.get("ratio"),
            "demand_provenance": results.get("provenance"),
            "scorecard": {k: (v or {}).get("rating", "unknown") for k, v in card.items()},
            "kill_criteria_triggered": triggered,
            "untested_high_impact_assumptions": assumptions.get("untested_high_impact_count"),
        }
        if results.get("provenance") == "MOCKED" and not any("MOCKED" in s for s in data["limitations"]):
            data["limitations"].append("The demand-test result is MOCKED, not from real visitors.")
        return data
