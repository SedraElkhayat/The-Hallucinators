"""critic_phase1: review the Discover report for unsupported claims, flattery and missing risks.
must_fix for any unsupported factual statement or flattery. Code adds must_fix issues for praise words and
for unsupported confidence; any must_fix forces verdict "revise" (up to 2 revision rounds)."""
import re

from agents.base import Agent
from agents.m2_common import (report_mentions, COMPETITORS, CRITIQUE, DEMAND, MARKET, OPPORTUNITIES, REPORT, SKEPTIC, as_list, claims_index, norm_severity,
                              get_artifact, message)

PRAISE = re.compile(r"\b(excellent|amazing|fantastic|brilliant|incredible|huge potential|massive opportunity|"
                    r"perfect fit|can't miss|will definitely|outstanding|exceptional|"
                    r"very promising|highly promising)\b", re.I)


LABELLED_ASSUMPTION = re.compile(r"['\"‘“]ASSUMPTION\b")


def _flat(text) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(text or "").lower()).split())


def kill_texts(skeptic: dict) -> tuple[list[str], list[str]]:
    """(triggered, not triggered) kill-criterion texts from the skeptic artifact, flattened for matching."""
    hit, quiet = [], []
    for k in (skeptic or {}).get("kill_criteria") or []:
        if isinstance(k, dict) and _flat(k.get("text")):
            (hit if k.get("triggered") is True else quiet).append(_flat(k.get("text")))
    return hit, quiet


def only_untriggered_kill(text: str, hit: list[str], quiet: list[str]) -> bool:
    """True if the issue is about a kill criterion the skeptic did NOT trigger (and none it did trigger).
    A real run's critic called an untriggered criterion a 'high-severity risk missing from the report'."""
    t = _flat(text)
    return any(q in t for q in quiet) and not any(h in t for h in hit)


CLAIM_ID = re.compile(r"\bC(\d+)\b")
SOURCE_COMPLAINT = re.compile(r"without (?:providing |citing |giving )?(?:a |any )?(?:source|citation|link)|"
                              r"no source|not sourced|unsourced|missing (?:a )?source|"
                              r"inconsistent with the claim'?s? source", re.I)


def cited_claims_verified(text: str, verified_ids: set) -> bool:
    """True if the issue only complains about a missing source for a finding whose cited claims are all verified.
    A real run's critic raised four must_fix issues like "The finding '49% of graphic designers work as
    freelancers.' cites claim_id C4, which is verified. However, the report mentions this claim without
    providing a source": citing a verified claim id IS the report's source (the .md report links it)."""
    ids = {f"C{n}" for n in CLAIM_ID.findall(text)}
    return bool(ids) and ids <= verified_ids and bool(SOURCE_COMPLAINT.search(text))


RISK_NOT_ADDRESSED = re.compile(r"risk|kill", re.I)


def risk_in_report(text: str, report: dict) -> bool:
    """True if the issue says a skeptic risk is missing and that risk's quoted text is in the report."""
    if not RISK_NOT_ADDRESSED.search(text):
        return False
    quoted = re.findall(r"['\"‘“]([^'\"’”]{25,})['\"’”]", text)
    return bool(quoted) and all(report_mentions(report, q) for q in quoted)


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
        hit, quiet = kill_texts(get_artifact(ctx, SKEPTIC) or {})
        verified_ids = {c["id"] for c in claims_index(ctx) if c["verified"]}
        report_art = get_artifact(ctx, REPORT) or {}
        for i in as_list(data.get("issues")):
            if isinstance(i, str):
                i = {"severity": "should_fix", "text": i}
            if isinstance(i, dict) and str(i.get("text", "")).strip():
                i["severity"] = norm_severity(i.get("severity"))
                if i["severity"] == "must_fix" and cited_claims_verified(str(i["text"]), verified_ids):
                    i["severity"], i["downgraded_in_code"] = "should_fix", "the cited claims are verified, so the finding has its source"
                if i["severity"] == "must_fix" and LABELLED_ASSUMPTION.search(str(i["text"])):
                    # The finding it quotes is already labelled ASSUMPTION, which is what the rules ask for.
                    i["severity"], i["downgraded_in_code"] = "should_fix", "finding already labelled ASSUMPTION"
                elif i["severity"] == "must_fix" and risk_in_report(i["text"], report_art):
                    i["severity"], i["downgraded_in_code"] = "should_fix", "the risk it names is in the report"
                elif i["severity"] == "must_fix" and only_untriggered_kill(i["text"], hit, quiet):
                    i["severity"], i["downgraded_in_code"] = "should_fix", "kill criterion was not triggered"
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
        v = str(data.get("verdict", "ok")).strip().strip(".").lower()
        data["verdict"] = "revise" if any(i["severity"] == "must_fix" for i in issues) else (
            v if v in ("ok", "revise") else "ok")
        return data
