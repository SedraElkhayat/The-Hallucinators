"""interview_analyst (founder kind): waits for the founder's interview notes, then extracts pain points,
current solutions and commitment signals (time, money, introductions). Compliments are weak evidence.
Never invents interviews: empty notes give ``unknown`` findings without a model call.

Founder key ``interview_notes``. Provenance is SAMPLE when the notes come from a scripted demo file or are
labeled SAMPLE, else REAL.
"""
import json

from agents.base import Agent
from agents.m2_common import (IDEA_CARD, INTERVIEW_SCRIPT, INTERVIEWS, ask_model, as_list, banner, clean, clip,
                              get_artifact, is_mocked, is_unknown, redact_input)


class InterviewAnalyst(Agent):
    name = "interview_analyst"
    phase = 1
    step = INTERVIEWS
    inputs: list = []
    tools: list = []
    required_keys = ["findings", "pain_points", "commitment_signals", "provenance"]
    kind = "founder"

    def run(self, ctx):
        raw = ctx.founder.provide("interview_notes",
                                  "Paste your notes from customer interviews (what people said they did, tried "
                                  "and paid for). Leave empty if you have not done interviews yet.")
        notes, flags = redact_input(raw)
        scripted = getattr(ctx.founder, "mode", "") == "scripted"
        provenance = "SAMPLE" if scripted or "SAMPLE" in notes.upper() else "REAL"
        if is_unknown(notes):
            data = {"findings": "unknown", "pain_points": [], "current_solutions": [], "commitment_signals": [],
                    "weak_evidence": [], "provenance": provenance, "interview_count": 0,
                    "note": "No interview notes were provided, so there are no interview findings."}
            md = f"PROVENANCE: {provenance}\n\n# Interview findings\n\nNo interview notes were provided. Findings: unknown.\n"
            return self.save(ctx, data, markdown=md, sources=[], model=None, mocked=bool(ctx.mock),
                             provenance=provenance)
        payload = {"interview_notes": clip(notes, 6000),
                   "idea_card": clean(get_artifact(ctx, IDEA_CARD) or {}),
                   "interview_script": clean(get_artifact(ctx, INTERVIEW_SCRIPT) or {})}
        user = "<data>\n" + json.dumps(payload, ensure_ascii=False, indent=1) + \
               "\n</data>\nAnswer with the JSON object described in your instructions."
        data, model, cost, tokens = ask_model(self, ctx, user,
                                              ["findings", "pain_points", "current_solutions", "commitment_signals"])
        for k in ("pain_points", "current_solutions", "commitment_signals", "weak_evidence"):
            data[k] = as_list(data.get(k))
        data["provenance"] = provenance  # set in code, never by the model
        if flags:
            data["input_flags"] = flags
        mocked = is_mocked(ctx, model)
        md = [f"PROVENANCE: {provenance}", "", banner(mocked) + "# Interview findings", ""]
        if provenance == "SAMPLE":
            md += ["These notes are SAMPLE input for a demo run, not real interviews.", ""]
        md += ["## Findings", "", str(data.get("findings")), ""]
        for k in ("pain_points", "current_solutions", "commitment_signals", "weak_evidence"):
            md += [f"## {k}", ""] + [f"- {json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x}"
                                     for x in data[k]] + ["- none"] * (not data[k]) + [""]
        return self.save(ctx, data, markdown="\n".join(md), sources=[], model=model, cost=cost, mocked=mocked,
                         provenance=provenance, **tokens)
