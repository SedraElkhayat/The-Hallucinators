"""Phase 2: stages, measure() on hand-built artifacts, scorecard rules, Gate 2 outcomes, halts."""
from pathlib import Path

import pytest

import gates
from phases import phase2

try:
    from test_m3_helpers import PHASE2_AGENTS, fixture, get_agent, make_ctx, put
except ImportError:
    from tests.test_m3_helpers import PHASE2_AGENTS, fixture, get_agent, make_ctx, put


def _card(**ratings):
    dims = {}
    for d in phase2.DIMENSIONS:
        r = ratings.get(d, "adequate")
        dims[d] = {"rating": r, "evidence_refs": [] if r == "unknown" else ["phase1_step5_market"], "note": "test"}
    return {"dimensions": dims}


def _artifacts(ctx, signups=140, target=100, card=None, kills=(), must_fix=0):
    put(ctx, "phase2_step8_scorecard", card or _card())
    put(ctx, "phase2_step3_demand_test_plan", {"hypothesis": "h", "metric": "waitlist_signups", "target": target,
                                               "window_days": 14, "traffic_sources": [], "reading_rule": "r"})
    put(ctx, "phase2_step5_demand_results", {"signups": signups, "days": 14, "provenance": "MOCKED",
                                             "ratio": signups / target})
    put(ctx, "phase2_step7_risks", {"risks": [], "would_change_mind": [],
                                    "kill_criteria": [{"text": k, "triggered": True} for k in kills]
                                    + [{"text": "not met", "triggered": False}]})
    put(ctx, "phase2_step9_critique", {"issues": [{"severity": "must_fix", "text": "x"}] * must_fix
                                       + [{"severity": "should_fix", "text": "y"}],
                                       "verdict": "revise" if must_fix else "ok"})


def _gate(ctx, attempt=0):
    gates.preregister(ctx, 2, phase2.gate_checks(ctx))
    return gates.evaluate(ctx, 2, phase2.measure(ctx), attempt)


def test_stages_and_constants():
    assert phase2.PHASE == 2 and phase2.PIVOT_TO == 1
    assert [a for stage in phase2.STAGES for a in stage] == PHASE2_AGENTS
    assert phase2.REVISE == ("validation_synthesizer", "critic_phase2")
    for name in PHASE2_AGENTS:
        assert get_agent(name).name == name
    checks = phase2.gate_checks(None)
    assert {c.metric for c in checks} == {"demand_unknown", "any_weak_dimension", "weak_count", "unknown_count",
                                          "demand_ratio", "kill_triggered", "open_must_fix"}


def test_measure_on_hand_built_artifacts(tmp_path):
    ctx = make_ctx(tmp_path)
    card = _card(competition="weak", monetization="unknown")
    card["dimensions"]["founder_fit"]["evidence_refs"] = []  # strong/adequate without evidence counts as unknown
    _artifacts(ctx, signups=70, card=card, kills=["ratio below 0.2"], must_fix=2)
    m = phase2.measure(ctx)
    assert m == {"demand_unknown": 0, "weak_count": 1, "any_weak_dimension": 1, "unknown_count": 2,
                 "demand_ratio": 0.7, "kill_triggered": 1, "open_must_fix": 2}


def test_measure_omits_missing_metrics(tmp_path):
    ctx = make_ctx(tmp_path)
    assert phase2.measure(ctx) == {}


def test_scorecard_sanitizer_sets_unknown_without_evidence(tmp_path):
    from agents.scorecard_builder import sanitize_scorecard
    data = fixture("scorecard_builder")
    data["dimensions"]["monetization"] = {"rating": "strong", "evidence_refs": [], "note": ""}
    out = sanitize_scorecard(data, {"ratio": 0.7, "provenance": "MOCKED"})
    assert out["dimensions"]["monetization"]["rating"] == "unknown"
    assert out["dimensions"]["demand_evidence"]["rating"] == "adequate"  # strong capped below a ratio of 1.0
    low = sanitize_scorecard(fixture("scorecard_builder"), {"ratio": 0.12, "provenance": "MOCKED"})
    assert low["dimensions"]["demand_evidence"]["rating"] == "weak"
    high = sanitize_scorecard({"dimensions": {"demand_evidence": {"rating": "unknown", "evidence_refs": []}}},
                              {"ratio": 1.4, "provenance": "MOCKED"})
    assert high["dimensions"]["demand_evidence"]["rating"] == "strong"
    assert "phase2_step5_demand_results" in high["dimensions"]["demand_evidence"]["evidence_refs"]
    assert high["dimensions"]["problem_severity"]["rating"] == "unknown"


def test_scorecard_agent_applies_sanitizer(tmp_path):
    agent = get_agent("scorecard_builder")
    ctx = make_ctx(tmp_path, seed=agent.inputs)
    put(ctx, "phase2_step5_demand_results", {"signups": 12, "days": 14, "provenance": "MOCKED", "ratio": 0.12})
    data = agent.run(ctx).data
    assert data["dimensions"]["demand_evidence"]["rating"] == "weak"


@pytest.mark.parametrize("signups,expected", [(100, "go"), (70, "repeat"), (30, "pivot"), (12, "stop")])
def test_gate2_outcomes_by_demand_ratio(tmp_path, signups, expected):
    ctx = make_ctx(tmp_path)
    _artifacts(ctx, signups=signups)
    result = _gate(ctx)
    assert result.outcome == expected
    assert (Path(ctx.out_dir) / "phase2_gate_decision.md").exists()


def test_gate2_weak_idea_stops_and_writes_decision(tmp_path):
    ctx = make_ctx(tmp_path)
    _artifacts(ctx, signups=12)
    result = _gate(ctx)
    assert result.outcome == "stop"
    decision = Path(ctx.out_dir) / "phase2_gate_decision.md"
    assert decision.exists() and decision.read_text(encoding="utf-8").strip()


def test_gate2_other_rules(tmp_path):
    ctx = make_ctx(tmp_path)
    _artifacts(ctx, card=_card(demand_evidence="unknown"))
    assert _gate(ctx).outcome == "repeat"
    ctx = make_ctx(tmp_path / "b")
    _artifacts(ctx, card=_card(competition="weak", monetization="weak"))
    assert _gate(ctx).outcome == "stop"
    ctx = make_ctx(tmp_path / "c")
    _artifacts(ctx, card=_card(competition="weak"))
    assert _gate(ctx).outcome == "pivot"
    ctx = make_ctx(tmp_path / "d")
    _artifacts(ctx, kills=["met"])
    assert _gate(ctx).outcome == "stop"
    ctx = make_ctx(tmp_path / "e")
    _artifacts(ctx, must_fix=1)
    assert _gate(ctx).outcome == "repeat"


def test_rejected_landing_page_halts_phase(tmp_path):
    agent = get_agent("landing_page_builder")
    ctx = make_ctx(tmp_path, approve=False, seed=agent.inputs)
    agent.run(ctx)
    assert ctx.extra.get("halt_phase") == "landing page rejected by the founder"
    assert ctx.approvals.requests and ctx.approvals.requests[0]["kind"] == "landing_page"
    # Without demand results the ratio metric is missing, so Gate 2 cannot pass.
    assert "demand_ratio" not in phase2.measure(ctx)


def test_demand_plan_defaults_and_locked_target(tmp_path):
    agent = get_agent("demand_test_designer")
    try:
        from test_m3_helpers import ScriptedLLM
    except ImportError:
        from tests.test_m3_helpers import ScriptedLLM
    bad = dict(fixture("demand_test_designer"), target="many", window_days=-3)
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"demand_test_designer": bad}), seed=agent.inputs)
    data = agent.run(ctx).data
    assert data["target"] == 100 and data["window_days"] == 14 and data["metric"] == "waitlist_signups"
    # A repeat round after a result exists keeps the target set before the result.
    put(ctx, "phase2_step3_demand_test_plan", dict(data, target=80, window_days=10))
    put(ctx, "phase2_step5_demand_results", {"signups": 12, "days": 10, "provenance": "MOCKED", "ratio": 0.15})
    ctx.llm = ScriptedLLM({"demand_test_designer": dict(fixture("demand_test_designer"), target=10)})
    data = agent.run(ctx).data
    assert data["target"] == 80 and data["window_days"] == 10


def test_risk_analyst_marks_low_ratio_kill_criterion(tmp_path):
    agent = get_agent("risk_analyst")
    ctx = make_ctx(tmp_path, seed=agent.inputs)
    put(ctx, "phase2_step5_demand_results", {"signups": 12, "days": 14, "provenance": "MOCKED", "ratio": 0.12})
    data = agent.run(ctx).data
    assert any(k["triggered"] for k in data["kill_criteria"])


def test_validation_report_never_picks_verdict(tmp_path):
    try:
        from test_m3_helpers import ScriptedLLM
    except ImportError:
        from tests.test_m3_helpers import ScriptedLLM
    agent = get_agent("validation_synthesizer")
    resp = dict(fixture("validation_synthesizer"), verdict="go", recommendation="go")
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"validation_synthesizer": resp}), seed=agent.inputs)
    data = agent.run(ctx).data
    assert "verdict" not in data and "recommendation" not in data
    assert data["verdict_inputs"]["demand_ratio"] == 1.4


def test_critic_must_fix_forces_revise(tmp_path):
    try:
        from test_m3_helpers import ScriptedLLM
    except ImportError:
        from tests.test_m3_helpers import ScriptedLLM
    agent = get_agent("critic_phase2")
    resp = {"issues": [{"severity": "must_fix", "text": "MOCKED unsupported statement"}], "verdict": "ok"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}), seed=agent.inputs)
    assert agent.run(ctx).data["verdict"] == "revise"


def test_competitor_analyst_drops_unknown_claim_refs(tmp_path):
    try:
        from test_m3_helpers import ScriptedLLM
    except ImportError:
        from tests.test_m3_helpers import ScriptedLLM
    agent = get_agent("competitor_analyst")
    resp = fixture("competitor_analyst")
    resp["claim_refs"].append({"claim": "MOCKED invented claim", "source_url": "https://example.com/mock/999"})
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"competitor_analyst": resp}), seed=agent.inputs)
    data = agent.run(ctx).data
    assert all(r["claim"] != "MOCKED invented claim" for r in data["claim_refs"])
    assert len(data["claim_refs"]) == 2
