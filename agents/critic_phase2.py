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

_STEM = re.compile(r"phase\d+_step\d+_[a-z0-9_]*[a-z0-9]")


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
        """Normalize the verdict, then turn must_fix issues that only dispute rules decided in code (demand
        rating capped for non-REAL results, inputs the critic saw shortened) into should_fix, with the reason."""
        data = normalize_verdict(data)
        results = get_artifact(ctx, P2_RESULTS) or {}
        if results and results.get("provenance") != "REAL":
            card = ((get_artifact(ctx, P2_SCORECARD) or {}).get("dimensions") or {}).get("demand_evidence") or {}
            if card.get("rating") in ("adequate", "weak", "unknown"):
                downgrade_must_fix(data, lambda t: "adequate" in t and "mock" in t and "strong" not in t,
                                   "rule applied in code: a demand result that is not REAL caps demand_evidence "
                                   "at adequate")
            report_text = str(get_artifact(ctx, P2_REPORT) or {}).lower()

            def _stems(t):
                return [s for s in _STEM.findall(t)]

            def not_provided(t):  # the critic sees shortened inputs, so "not provided" often means "cut off"
                stems = _stems(t)
                return bool(stems) and re.search(r"not (?:fully )?provided|not fully shown|which is not", t) \
                    and all(ctx.store.has(s) for s in stems)

            def cited(t):  # "does not cite X": true only if X appears nowhere in the report
                stems = _stems(t)
                return bool(stems) and re.search(r"not cited|does not cite|without citing|cited to the (?:wrong|incorrect)"
                                                 r"|incorrect artifact", t) and all(s in report_text for s in stems)

            downgrade_must_fix(data, not_provided,
                               "rule applied in code: the artifact named in the issue exists in the run (the critic's "
                               "input is shortened, so it can look cut off)")
            downgrade_must_fix(data, cited,
                               "rule applied in code: the artifact named in the issue is cited in the report")
            prov = str(results.get("provenance") or "").lower()
            report = get_artifact(ctx, P2_REPORT) or {}
            stated = prov and (prov in str(report.get("summary", "")).lower()
                               or any(prov in str(s).lower() for s in report.get("limitations") or []))
            if stated:
                downgrade_must_fix(data, lambda t: "mock" in t and re.search(r"as real|real (?:evidence|behavio|data|demand)|not real", t),
                                   "rule applied in code: the report states that the demand data is "
                                   f"{results.get('provenance')} in its summary and limitations")
            downgrade_must_fix(data, lambda t: "assumption" in t and "kill criteri" not in t
                               and re.search(r"presented as (?:a )?(?:claim|fact)|as if (?:they are |it is )?supported"
                                             r"|without (?:a |an |any |proper |supporting |sufficient )?(?:cited )?"
                                             r"(?:evidence|source|artifact)"
                                             r"|lacks? (?:clear |any |sufficient )?evidence", t),
                               "rule applied in code: a finding without a cited claim is flagged assumption=true by "
                               "code, so an assumption is not presented as a claim")
            downgrade_must_fix(data, lambda t: "kill" in t and "mock" in t
                               and re.search(r"not\s+(?:been\s+)?trigger|should\s+(?:be\s+|have\s+been\s+)?trigger|despite", t),
                               "rule applied in code: a kill criterion counts only with named evidence; a MOCKED "
                               "result alone triggers none")
        report_all = str(get_artifact(ctx, P2_REPORT) or {}).lower()
        high_risks = [str(r.get("text", "")).lower()[:40] for r in (get_artifact(ctx, P2_RISKS) or {}).get("risks") or []
                      if isinstance(r, dict) and r.get("severity") == "high" and r.get("text")]
        if high_risks and all(h in report_all for h in high_risks):
            downgrade_must_fix(data, lambda t: "risk" in t and "high" in t
                               and re.search(r"fails? to mention|does not mention|not mention|omits?|missing", t),
                               "rule applied in code: every high risk of the Risk Analyst is in the report (the "
                               "validation_synthesizer adds any that is missing)")
        downgrade_must_fix(data, lambda t: re.search(r"verified (?:as )?false|not verified|unverified", t)
                           and re.search(r"no source|without (?:a )?source|not cited", t) and "kill criteri" not in t,
                           "rule applied in code: a claim whose quote the checker did not find is flagged "
                           "assumption=true by code, so it is not presented as a verified fact")
        # Two more points that code decides, whatever the provenance of the demand data:
        # - a scorecard rating without evidence_refs counts as "unknown" in the gate (phases/phase2.effective_ratings),
        #   so a rating cannot overstate its evidence;
        # - the Risk Analyst's high risks are copied into the report by code and cited to phase2_step7_risks.
        downgrade_must_fix(data, lambda t: "scorecard" in t and re.search(
            r"no (?:evidence|source)|without (?:evidence|source)|lack of evidence|evidence (?:is )?(?:not|missing)", t),
            "rule applied in code: a scorecard rating without evidence_refs counts as unknown in the gate, so it "
            "cannot overstate the evidence")
        downgrade_must_fix(data, lambda t: t.startswith("risk (high)") or (
            "risk" in t and re.search(r"no source|not cited|source (?:is )?not", t)
            and not re.search(r"competitor|price|invent", t)),
            "rule applied in code: high risks come from the Risk Analyst and are cited to phase2_step7_risks by code")
        return normalize_verdict(data)
