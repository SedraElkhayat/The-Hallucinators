"""discover_synthesizer: hedged Phase 1 report. Every finding cites verified claim ids (C1, C2, ... from the
claims index built in code) or is marked as an assumption. It never chooses the gate verdict. On a revision
round it reads ``ctx.extra["critique"]``."""
from agents.base import Agent
from agents.m2_common import (founder_budget, high_risks, report_mentions, get_artifact, COMPETITORS, DEMAND, FEASIBILITY, FOUNDER_FIT, IDEA_CARD, INTERVIEWS, MARKET,
                              OPPORTUNITIES, REPORT, SCOPE, SCORES, SKEPTIC, as_list, claims_index, id_list, message)


class DiscoverSynthesizer(Agent):
    name = "discover_synthesizer"
    phase = 1
    step = REPORT
    inputs = [IDEA_CARD]
    optional_inputs = [SCOPE, OPPORTUNITIES, MARKET, DEMAND, COMPETITORS, FOUNDER_FIT, FEASIBILITY, INTERVIEWS,
                       SCORES, SKEPTIC]
    tools: list = []
    required_keys = ["summary", "findings", "assumptions", "limitations", "confidence"]
    kind = "llm"

    def build_user_message(self, ctx) -> str:
        extra = {"claims_index": claims_index(ctx), "founder_budget": founder_budget(ctx.brief)}
        if ctx.extra.get("critique"):
            extra["critique"] = ctx.extra["critique"]
        return message(ctx, self.inputs + self.optional_inputs, extra, brief=False, compact=True)

    def post_process(self, ctx, data: dict) -> dict:
        index = {c["id"]: c for c in claims_index(ctx)}
        findings = []
        for f in as_list(data.get("findings")):
            if isinstance(f, str):
                f = {"text": f}
            if not isinstance(f, dict) or not str(f.get("text", "")).strip():
                continue
            ids = id_list(f.get("claim_ids"))
            good = [i for i in ids if i in index and index[i]["verified"]]
            bad = [i for i in ids if i not in good]
            f["claim_ids"] = good
            if bad:
                f["unverified_claim_ids"] = bad
            if not good:  # code rule: no verified support means it is an assumption
                f["assumption"] = True
                if not str(f["text"]).startswith("ASSUMPTION"):
                    f["text"] = f"ASSUMPTION: {f['text']}"
            else:
                f["sources"] = sorted({index[i]["source_url"] for i in good if index[i].get("source_url")})
            findings.append(f)
        data["findings"] = findings
        data["assumptions"] = [str(a) for a in as_list(data.get("assumptions"))]
        data["limitations"] = [str(a) for a in as_list(data.get("limitations"))]
        conf = str(data.get("confidence", "low")).lower()
        conf = conf if conf in ("low", "medium", "high") else "low"
        verified = sum(1 for c in index.values() if c["verified"])
        if verified < 3 and conf != "low":
            data["confidence_capped"] = f"only {verified} verified claims, so confidence is low"
            conf = "low"
        data["confidence"] = conf
        data["sources"] = sorted({s for f in findings for s in f.get("sources", [])})
        # Every high- or medium-severity skeptic risk must be visible in the report (the critic's must_fix rule). A small model
        # sometimes paraphrases or drops one, so code adds the missing ones word for word: more disclosure, never less.
        added = []
        for risk in high_risks(get_artifact(ctx, SKEPTIC) or {}):
            if not report_mentions(data, risk):
                data["limitations"].append(f"Risk (skeptic): {risk}")
                added.append(risk)
        if added:
            data["risks_added_by_code"] = added
        return data
