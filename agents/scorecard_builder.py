"""scorecard_builder: six dimensions rated from evidence; code enforces the evidence rules."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_DEMAND_SIGNALS, P1_FEASIBILITY, P1_FOUNDER_FIT,
                              P1_INTERVIEWS, P1_MARKET, P2_ASSUMPTIONS, P2_CANVAS,
                              P2_COMPETITOR_ANALYSIS, P2_RESULTS, P2_RISKS, P2_SCORECARD, get_artifact)

DIMENSIONS = ("problem_severity", "demand_evidence", "competition", "founder_fit", "feasibility", "monetization")
RATINGS = ("strong", "adequate", "weak", "unknown")


def sanitize_scorecard(data: dict, demand_results=None) -> dict:
    """Normalize the scorecard; apply the demand rubric; empty evidence_refs -> unknown."""
    raw = data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {}
    dims = {}
    for d in DIMENSIONS:
        v = raw.get(d)
        if isinstance(v, str):
            v = {"rating": v}
        if not isinstance(v, dict):
            v = {}
        rating = str(v.get("rating", "unknown")).lower()
        refs = v.get("evidence_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        refs = [str(r) for r in refs if str(r).strip()]
        dims[d] = {"rating": rating if rating in RATINGS else "unknown", "evidence_refs": refs,
                   "note": str(v.get("note", ""))}

    # Rubric for demand_evidence, driven by the result against the pre-set target.
    if demand_results and isinstance(demand_results.get("ratio"), (int, float)):
        ratio = float(demand_results["ratio"])
        de = dims["demand_evidence"]
        label = f"ratio {ratio} vs pre-set target ({demand_results.get('provenance', 'unknown')} result)"
        if ratio >= 1.0:
            de["rating"] = "strong"
        elif ratio < 0.5:
            de["rating"] = "weak"
        elif de["rating"] == "strong":
            de["rating"] = "adequate"
        if ratio >= 1.0 or ratio < 0.5 or de["rating"] != "unknown":
            if P2_RESULTS not in de["evidence_refs"]:
                de["evidence_refs"].append(P2_RESULTS)
            de["note"] = (de["note"] + " | " if de["note"] else "") + f"Rubric applied in code: {label}"

    # No evidence means unknown, whatever the model said.
    for d, v in dims.items():
        if not v["evidence_refs"] and v["rating"] != "unknown":
            v["note"] = (v["note"] + " | " if v["note"] else "") + f"Set to unknown in code: no evidence (was {v['rating']})"
            v["rating"] = "unknown"
    data["dimensions"] = dims
    return data


class ScorecardBuilder(M3InputsMixin, Agent):
    name = "scorecard_builder"
    phase = 2
    step = P2_SCORECARD
    inputs = [P2_RESULTS, P2_COMPETITOR_ANALYSIS, P2_CANVAS, P2_ASSUMPTIONS, P2_RISKS]
    optional_inputs = [P1_FOUNDER_FIT, P1_FEASIBILITY, P1_DEMAND_SIGNALS, P1_MARKET, P1_INTERVIEWS]
    tools = []
    required_keys = ["dimensions"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        return sanitize_scorecard(data, get_artifact(ctx, P2_RESULTS))
