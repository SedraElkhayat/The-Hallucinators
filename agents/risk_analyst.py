"""risk_analyst: adversarial risks and kill criteria.

A kill criterion counts as triggered only when it names its evidence, checked in code (the same rule as
the Phase 1 skeptic): ``evidence`` must name an input artifact stem that exists, or quote text that
appears in the inputs and is not an ASSUMPTION. Otherwise ``triggered`` is set to false and the
criterion is flagged ``triggered_without_evidence``. The demand rule (ratio below 0.2 of the pre-set
target) is decided in code from ``phase2_step5_demand_results``.
"""
import json
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_SKEPTIC, P2_ASSUMPTIONS, P2_CANVAS,
                              P2_COMPETITOR_ANALYSIS, P2_PLAN, P2_RESULTS, P2_RISKS, get_artifact)

DEMAND_KILL_RATIO = 0.2
MIN_QUOTE_CHARS = 12
_QUOTED = re.compile(r"[\"“”']([^\"“”']{%d,})[\"“”']" % MIN_QUOTE_CHARS)
# Absence of evidence is "unknown", not a reason to stop (same rule as M2's skeptic). Real run: "no willingness to pay"
# was triggered because "there is no clear evidence".
_MISSING_EVIDENCE = re.compile(
    r"\b(?:no|not enough|insufficient|little|limited|lack of|lacks?|without)\s+(?:\w+\s+)?"
    r"(?:evidence|data|signals?|indications?|signs?|proof)\b|\b(?:might|may|could|possibly|perhaps|unclear|"
    r"cannot be (?:determined|confirmed))\b", re.I)
# A kill criterion that is itself "no evidence of X" describes absence: only the scorecard's "unknown" can say that.
_ABSENCE_CRITERION = re.compile(r"^\s*(?:\w+\s+){0,3}?(?:no|lack of|insufficient|not enough|little|limited)\s+"
                                r"(?:\w+\s+){0,2}(?:evidence|data|signals?|indications?|willingness)\b", re.I)
_DEMAND_RULE = re.compile(r"(?:ratio|sign-?ups?|demand|target|waitlist).*(?<![\d.])0?\.2(?!\d)|(?<![\d.])0?\.2(?!\d).*(?:ratio|sign-?ups?|demand|target|waitlist)", re.I)


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def evidence_is_named(evidence, stems_present: list, input_texts: list) -> bool:
    """True if evidence names an existing input stem, or quotes ASSUMPTION-free text found in the inputs."""
    if not isinstance(evidence, str) or not evidence.strip():
        return False
    if any(stem in evidence for stem in stems_present):
        rest = evidence
        for stem in stems_present:
            rest = rest.replace(stem, " ")
        # Naming an artifact is not evidence by itself: say what in it shows the condition. (Real run: a kill
        # criterion "sign-ups below 0.2 of the target" was triggered with only the artifact name, ratio was 1.4.)
        if len(re.sub(r"[\W_]+", " ", rest).strip()) >= 12:
            return True
    candidates = _QUOTED.findall(evidence) or [evidence.strip().strip("\"'“”")]
    for quote in candidates:
        q = _norm(quote)
        if len(q) < MIN_QUOTE_CHARS or "assumption" in q:
            continue
        rest_q = q
        for stem in stems_present:
            rest_q = rest_q.replace(stem.lower(), " ")
        if len(re.sub(r"[\W_]+", " ", rest_q).strip()) < 12:
            continue  # only an artifact name, not text that shows the condition
        # The quote must come from an input string that is itself not labeled ASSUMPTION.
        if any(q in _norm(t) and "assumption" not in t.lower() for t in input_texts):
            return True
    return False


class RiskAnalyst(M3InputsMixin, Agent):
    name = "risk_analyst"
    phase = 2
    step = P2_RISKS
    inputs = [P2_RESULTS, P2_PLAN, P2_CANVAS, P2_COMPETITOR_ANALYSIS, P2_ASSUMPTIONS]
    optional_inputs = [P1_SKEPTIC]
    tools = []
    required_keys = ["risks", "kill_criteria", "would_change_mind"]
    kind = "llm"

    def _inputs_seen(self, ctx):
        stems, texts = [], []
        for stem in list(self.inputs) + list(self.optional_inputs):
            art = get_artifact(ctx, stem)
            if art is not None:
                stems.append(stem)
                texts.extend(_strings(art))
        return stems, texts

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

        stems, texts = self._inputs_seen(ctx)
        kills = []
        for k in data.get("kill_criteria") or []:
            if isinstance(k, str):
                k = {"text": k}
            if not isinstance(k, dict) or not k.get("text"):
                continue
            evidence = k.get("evidence")
            k["evidence"] = evidence.strip() if isinstance(evidence, str) else ""
            claimed = k.get("triggered") is True
            k["triggered"] = claimed and evidence_is_named(k["evidence"], stems, texts)
            if claimed and not k["triggered"]:
                k["triggered_without_evidence"] = True  # the model's bare claim never reaches the gate
            if k["triggered"] and _ABSENCE_CRITERION.search(str(k.get("text", ""))):
                k["triggered"] = False
                k["triggered_on_missing_evidence"] = True  # "no evidence of X" can only be unknown, never a kill
            if k["triggered"] and _MISSING_EVIDENCE.search(k["evidence"]):
                k["triggered"] = False
                k["triggered_on_missing_evidence"] = True  # missing or hedged evidence is unknown, not a kill
            kills.append(k)

        self._apply_demand_rule(ctx, kills)
        data["kill_criteria"] = kills
        wcm = data.get("would_change_mind")
        data["would_change_mind"] = [wcm] if isinstance(wcm, str) else [str(x) for x in (wcm or [])]
        return data

    @staticmethod
    def _apply_demand_rule(ctx, kills: list) -> None:
        """The demand kill criterion is decided in code from the result against the pre-set target."""
        results = get_artifact(ctx, P2_RESULTS)
        if results is None or not isinstance(results.get("ratio"), (int, float)) or isinstance(results.get("ratio"), bool):
            return
        ratio, prov = float(results["ratio"]), str(results.get("provenance") or "unknown")
        evidence = f"{P2_RESULTS} ratio {ratio}, provenance {prov}"
        met = ratio < DEMAND_KILL_RATIO
        existing = [k for k in kills if _DEMAND_RULE.search(str(k.get("text", "")))]
        if not existing and not met:
            return
        if not existing:
            kills.append({"text": f"Demand ratio below {DEMAND_KILL_RATIO} of the sign-up target set before the test",
                          "triggered": False, "evidence": ""})
            existing = [kills[-1]]
        for k in existing:  # one decision for every criterion about this rule; no duplicate is added
            k["triggered"] = met
            k["evidence"] = evidence if met else ""
            k["checked_in_code"] = True
            if met and prov != "REAL" and f"provenance {prov}".lower() not in k["text"].lower():
                note = ": the result is MOCKED, not from real visitors" if prov == "MOCKED" else ""
                k["text"] += f" (provenance {prov}{note})"
