"""Shared helpers for the M3 tests (Phase 2 and 3). Offline: MockLLM, no network."""
import copy
import json
from pathlib import Path

from core.contracts import Context, LLMResponse

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "mock"
REQUIRED_LOG_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")

PHASE2_AGENTS = ["competitor_analyst", "lean_canvas_drafter", "demand_test_designer", "landing_page_builder",
                 "demand_results", "assumption_auditor", "risk_analyst", "scorecard_builder",
                 "validation_synthesizer", "critic_phase2"]
PHASE3_AGENTS = ["spec_writer", "copywriter", "builder", "user_docs_writer", "qa_agent", "content_reviewer"]
M3_AGENTS = PHASE2_AGENTS + PHASE3_AGENTS
NON_LLM_AGENTS = {"demand_results", "qa_agent"}

STEPS = {
    "competitor_analyst": "phase2_step1_competitor_analysis",
    "lean_canvas_drafter": "phase2_step2_lean_canvas",
    "demand_test_designer": "phase2_step3_demand_test_plan",
    "landing_page_builder": "phase2_step4_landing_page",
    "demand_results": "phase2_step5_demand_results",
    "assumption_auditor": "phase2_step6_assumptions",
    "risk_analyst": "phase2_step7_risks",
    "scorecard_builder": "phase2_step8_scorecard",
    "validation_synthesizer": "phase2_step9_validation_report",
    "critic_phase2": "phase2_step9_critique",
    "spec_writer": "phase3_step1_spec",
    "copywriter": "phase3_step2_page_copy",
    "builder": "phase3_step3_build",
    "user_docs_writer": "phase3_step4_user_docs",
    "qa_agent": "phase3_step5_qa_report",
    "content_reviewer": "phase3_step6_content_review",
}


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _claim(n, text):
    return {"claim": text, "source_url": f"https://example.com/mock/{n}", "quote": f"MOCKED quote {n}",
            "verified": True, "assumption": False, "mocked": True}


# Hand-built Phase 1 artifacts (test inputs, MOCKED).
PHASE1 = {
    "phase1_step2_clarification": {"answers": {"founder_skills": "MOCKED: graphic design, writing",
                                               "time_per_week": "MOCKED: 10 hours", "budget": "MOCKED: 0"}},
    "phase1_step4_idea_card": {"customer": "MOCKED: solo freelance designers", "problem": "MOCKED: onboarding by hand",
                               "solution": "MOCKED: onboarding template kit", "value_proposition": "MOCKED: ready kit",
                               "hypotheses": [{"id": "H1", "text": "MOCKED: designers want a kit", "test": "MOCKED: waitlist"}]},
    "phase1_step5_competitors": {"claims": [_claim(1, "MOCKED Rival Kit A sells onboarding templates for agencies")],
                                 "competitors": [{"name": "MOCKED Rival Kit A", "url": "https://example.com/mock/1",
                                                  "pricing": "MOCKED $49", "positioning": "MOCKED agencies"}],
                                 "insufficient_evidence": False},
    "phase1_step5_market": {"claims": [_claim(2, "MOCKED free onboarding checklists are common")],
                            "insufficient_evidence": False},
    "phase1_step5_demand_signals": {"claims": [_claim(3, "MOCKED designers ask for onboarding templates")],
                                    "insufficient_evidence": False},
    "phase1_step5_founder_fit": {"rating": "strong", "reasoning": "MOCKED", "evidence_refs": ["phase1_step2_clarification"]},
    "phase1_step6_feasibility": {"rating": "strong", "reasoning": "MOCKED", "evidence_refs": ["phase1_step5_competitors"]},
    "phase1_step6_interview_findings": {"pain_points": ["MOCKED SAMPLE: onboarding takes long"], "provenance": "SAMPLE"},
    "phase1_step8_skeptic": {"risks": [], "kill_criteria": [], "would_change_mind": []},
    "phase1_step9_discover_report": {"summary": "MOCKED report", "findings": [], "assumptions": [], "limitations": [],
                                     "confidence": "low"},
}


class FakeApprovals:
    """Records every request; returns the configured decision (True = founder approves)."""

    def __init__(self, decision=True):
        self.decision = decision
        self.requests = []

    def request(self, kind, title, content, phase):
        self.requests.append({"kind": kind, "title": title, "content": content, "phase": phase})
        return self.decision


class FakeFounder:
    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.calls = []

    def ask(self, key, prompt, options=None):
        return self.provide(key, prompt)

    def provide(self, key, prompt):
        self.calls.append(key)
        if key not in self.answers:
            raise KeyError(key)
        return self.answers[key]


class FakeTools:
    def search(self, agent, query):
        raise AssertionError("M3 agents must not use tools")

    def fetch(self, agent, url):
        raise AssertionError("M3 agents must not use tools")


class ScriptedLLM:
    """LLM double returning given data per agent (falls back to the agent's fixture)."""

    def __init__(self, responses=None, transform=None):
        self.responses = responses or {}
        self.transform = transform
        self.calls = []

    def chat(self, system, user, agent, json_mode=True):
        self.calls.append(agent)
        data = copy.deepcopy(self.responses[agent]) if agent in self.responses else fixture(agent)
        if self.transform:
            data = self.transform(agent, data)
        return LLMResponse(text=json.dumps(data), data=data, model="mock", tokens_in=0, tokens_out=0, cost=0.0)


def _mock_llm():
    from core.llm import MockLLM
    try:
        return MockLLM()
    except TypeError:  # pragma: no cover - constructor variants
        return MockLLM(FIXTURES)


def _store(out_dir):
    from core.artifacts import ArtifactStore
    return ArtifactStore(out_dir)


def _log(path):
    from core.decision_log import DecisionLog
    return DecisionLog(path)


def make_ctx(tmp_path, llm=None, approve=True, founder_answers=None, seed=()):
    out_dir = Path(tmp_path) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(brief="MOCKED brief: onboarding kit for solo designers", out_dir=out_dir,
                  store=_store(out_dir), llm=llm or _mock_llm(), tools=FakeTools(),
                  log=_log(out_dir.parent / "decision_log.json"), approvals=FakeApprovals(approve),
                  founder=FakeFounder(founder_answers if founder_answers is not None else
                                      {"demand_results": '{"signups": 140, "days": 14, "provenance": "MOCKED"}'}),
                  mock=True)
    for step in seed:
        put(ctx, step, seed_data(step))
    return ctx


def put(ctx, step, data, agent="test_seed"):
    ctx.store.put(step, data, f"# {step}\n\nMOCKED test input\n", agent, [])


def seed_data(step):
    if step in PHASE1:
        return copy.deepcopy(PHASE1[step])
    agent = next(a for a, s in STEPS.items() if s == step)
    return fixture(agent)


def log_entries(ctx):
    path = Path(ctx.out_dir).parent / "decision_log.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def get_agent(name):
    from agents import get_agent as _get
    agent = _get(name)
    return agent() if isinstance(agent, type) else agent


def test_helpers_fixtures_cover_all_agents():
    assert sorted(STEPS) == sorted(M3_AGENTS)
    for name in M3_AGENTS:
        assert "MOCKED" in (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
