"""critic_phase2: reviews the validation report; must_fix for unsupported facts or flattery.

Two points are decided in code and are correct by design, so a must_fix that disputes them is downgraded to
should_fix (with the reason recorded), but only when the artifacts show the rule applied:
- the scorecard caps demand_evidence at "adequate" for a demand result that is not REAL (scorecard_builder);
- a kill criterion counts only with named evidence, so a MOCKED result alone triggers none (risk_analyst).
"""
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P2_CRITIQUE, P2_REPORT, P2_RESULTS, P2_RISKS, P2_SCORECARD,
                              downgrade_must_fix, get_artifact, normalize_verdict)


class CriticPhase2(M3InputsMixin, Agent):
    name = "critic_phase2"
    phase = 2
    step = P2_CRITIQUE
    inputs = [P2_REPORT]
    optional_inputs = [P2_RESULTS, P2_RISKS, P2_SCORECARD]
    tools = []
    required_keys = ["issues", "verdict"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        # The critic reviews the report itself; it does not need the previous critique.
        from agents.m3_common import inputs_message
        return inputs_message(ctx, list(self.inputs) + list(self.optional_inputs))

    def post_process(self, ctx, data: dict) -> dict:
        data = normalize_verdict(data)
        results = get_artifact(ctx, P2_RESULTS) or {}
        if results and results.get("provenance") != "REAL":
            card = ((get_artifact(ctx, P2_SCORECARD) or {}).get("dimensions") or {}).get("demand_evidence") or {}
            if card.get("rating") in ("adequate", "weak", "unknown"):
                downgrade_must_fix(data, lambda t: "adequate" in t and "mock" in t and "strong" not in t,
                                   "rule applied in code: a demand result that is not REAL caps demand_evidence "
                                   "at adequate")
            downgrade_must_fix(data, lambda t: "kill" in t and "mock" in t
                               and re.search(r"not\s+(?:been\s+)?trigger|should\s+(?:be\s+|have\s+been\s+)?trigger|despite", t),
                               "rule applied in code: a kill criterion counts only with named evidence; a MOCKED "
                               "result alone triggers none")
        return normalize_verdict(data)
