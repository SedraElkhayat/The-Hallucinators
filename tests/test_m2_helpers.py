# OWNER: M2
"""Helpers for the M2 tests (Phase 1 agents, gates, claims, audit). Holds no tests."""
from __future__ import annotations

import json

from agents import get_agent
from core.contracts import LLMResponse
from core.llm import MockLLM
from phases import phase1
from tests.helpers import DECISION_KEYS, ROOT, make_ctx  # noqa: F401  (re-exported)

PHASE1_AGENTS = [n for stage in phase1.STAGES for n in stage]
STEPS = {
    "scope_classifier": "phase1_step1_scope", "clarifier": "phase1_step2_clarification",
    "option_suggester": "phase1_step2_options", "idea_generator": "phase1_step3_idea_candidates",
    "idea_sharpener": "phase1_step4_idea_card", "opportunity_finder": "phase1_step5_opportunities",
    "market_scout": "phase1_step5_market", "demand_analyst": "phase1_step5_demand_signals",
    "competitor_scanner": "phase1_step5_competitors", "founder_fit": "phase1_step5_founder_fit",
    "mom_test_designer": "phase1_step5_interview_script", "feasibility_analyst": "phase1_step6_feasibility",
    "interview_analyst": "phase1_step6_interview_findings", "opportunity_scorer": "phase1_step7_opportunity_scores",
    "skeptic": "phase1_step8_skeptic", "discover_synthesizer": "phase1_step9_discover_report",
    "critic_phase1": "phase1_step9_critique",
}
STRONG_BRIEF = (ROOT / "demo" / "brief_strong.md").read_text(encoding="utf-8")


class TransformLLM(MockLLM):
    """MockLLM whose responses pass through ``transform(agent, data)`` (e.g. to inject violations)."""

    def __init__(self, transform):
        super().__init__()
        self.transform = transform

    def chat(self, system, user, agent, json_mode=True):
        r = super().chat(system, user, agent, json_mode)
        data = self.transform(agent, json.loads(r.text))
        return LLMResponse(text=json.dumps(data), data=data if json_mode else None, model=r.model,
                           tokens_in=0, tokens_out=0, cost=0.0)


def ctx_for(tmp_path, brief: str = STRONG_BRIEF, founder_inputs=None):
    return make_ctx(tmp_path, brief=brief, founder_inputs=founder_inputs)


def run_until(ctx, name: str) -> None:
    """Run the Phase 1 stages (mock) that come before ``name``, so its inputs exist."""
    for stage in phase1.STAGES:
        if name in stage:
            return
        for n in stage:
            get_agent(n).run(ctx)
    raise KeyError(name)
