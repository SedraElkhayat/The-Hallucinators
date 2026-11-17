"""risk_analyst kill criteria: triggered only with named evidence, checked in code (same rule as Phase 1)."""
import gates
from phases import phase2
from tests.test_m3_helpers import ScriptedLLM, fixture, get_agent, make_ctx, put

DEMAND = "phase2_step5_demand_results"


def _run(tmp_path, kill_criteria, signups=140):
    agent = get_agent("risk_analyst")
    resp = dict(fixture("risk_analyst"), kill_criteria=kill_criteria)
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"risk_analyst": resp}), seed=agent.inputs)
    put(ctx, DEMAND, {"signups": signups, "days": 14, "provenance": "MOCKED", "ratio": signups / 100,
                      "target": 100, "window_days": 14})
    return ctx, agent.run(ctx).data


def _demand_kills(data):
    return [k for k in data["kill_criteria"] if "0.2" in k["text"]]


def test_TC_M3_risk_1_triggered_kill_criterion_without_evidence_is_ignored(tmp_path):
    ctx, data = _run(tmp_path, [{"text": "MOCKED: buyers will not pay", "triggered": True}])
    k = data["kill_criteria"][0]
    assert k["triggered"] is False and k["triggered_without_evidence"] is True
    assert k["text"] == "MOCKED: buyers will not pay" and k["evidence"] == ""
    assert phase2.measure(ctx)["kill_triggered"] == 0


def test_TC_M3_risk_2_triggered_kill_criterion_with_evidence_counts(tmp_path):
    ctx, data = _run(tmp_path, [{"text": "MOCKED: no differentiator against free substitutes", "triggered": True,
                                 "evidence": "phase2_step1_competitor_analysis: substitutes level high"}])
    assert data["kill_criteria"][0]["triggered"] is True
    assert phase2.measure(ctx)["kill_triggered"] == 1


def test_TC_M3_risk_3_evidence_must_name_an_existing_input(tmp_path):
    ctx, data = _run(tmp_path, [
        {"text": "a", "triggered": True, "evidence": "phase9_step1_made_up shows it"},
        {"text": "b", "triggered": True, "evidence": "phase1_step8_skeptic"},  # optional input, not present here
        {"text": "c", "triggered": True, "evidence": "   "},
    ])
    assert [k["triggered"] for k in data["kill_criteria"]] == [False, False, False]


def test_TC_M3_risk_4_quote_from_inputs_counts_but_not_an_assumption_or_invented_quote(tmp_path):
    ctx, data = _run(tmp_path, [
        {"text": "q1", "triggered": True, "evidence": '"rivals target agencies; the evidence shows no kit"'},
        {"text": "q2", "triggered": True, "evidence": '"intended model is a one-time purchase of the kit"'},
        {"text": "q3", "triggered": True, "evidence": '"nobody wants onboarding templates at all"'},
    ])
    # q1 quotes the competitor analysis, but that sentence is labeled ASSUMPTION; q2 quotes the canvas
    # revenue box, also labeled ASSUMPTION; q3 is not in the inputs.
    assert [k["triggered"] for k in data["kill_criteria"]] == [False, False, False]
    # The competitor analysis states this without an ASSUMPTION label, so quoting it counts.
    ctx, data = _run(tmp_path / "b", [
        {"text": "q4", "triggered": True, "evidence": '"sells an onboarding template bundle aimed at design agencies"'}])
    assert data["kill_criteria"][0]["triggered"] is True
    from agents.risk_analyst import evidence_is_named
    texts = ["MOCKED: free checklists exist (claim: MOCKED free onboarding checklists are common)"]
    assert evidence_is_named('"free checklists exist"', [], texts) is True
    assert evidence_is_named('"free checklists exist"', [], [t + " ASSUMPTION" for t in texts]) is False
    assert evidence_is_named("short", [], ["short"]) is False


def test_TC_M3_risk_5_demand_ratio_below_0_2_still_triggers_in_code_with_evidence(tmp_path):
    ctx, data = _run(tmp_path, fixture("risk_analyst")["kill_criteria"], signups=12)
    demand = _demand_kills(data)
    assert len(demand) == 1  # the model's own demand criterion is reused, not duplicated
    k = demand[0]
    assert k["triggered"] is True and k["checked_in_code"] is True
    assert k["evidence"] == f"{DEMAND} ratio 0.12, provenance MOCKED"
    assert "provenance MOCKED" in k["text"]
    assert phase2.measure(ctx)["kill_triggered"] == 1


def test_TC_M3_risk_6_demand_rule_added_when_model_omits_it(tmp_path):
    ctx, data = _run(tmp_path, [], signups=12)
    demand = _demand_kills(data)
    assert len(demand) == 1 and demand[0]["triggered"] is True and "MOCKED" in demand[0]["text"]


def test_TC_M3_risk_7_model_cannot_trigger_demand_rule_against_the_ratio(tmp_path):
    ctx, data = _run(tmp_path, [{"text": "Demand ratio below 0.2 of the target", "triggered": True,
                                 "evidence": DEMAND}], signups=140)
    k = _demand_kills(data)[0]
    assert k["triggered"] is False and k["evidence"] == ""
    assert phase2.measure(ctx)["kill_triggered"] == 0


def test_TC_M3_risk_8_strong_idea_with_a_guessed_trigger_still_passes_gate2_kill_check(tmp_path):
    ctx, data = _run(tmp_path, [{"text": "MOCKED: the market might be too small", "triggered": True},
                                {"text": "MOCKED: demand ratio below 0.2 of the pre-set target", "triggered": False}])
    put(ctx, "phase2_step8_scorecard", fixture("scorecard_builder"))
    put(ctx, "phase2_step9_critique", fixture("critic_phase2"))
    gates.preregister(ctx, 2, phase2.gate_checks(ctx))
    m = phase2.measure(ctx)
    assert m["kill_triggered"] == 0 and m["demand_ratio"] == 1.4
    result = gates.evaluate(ctx, 2, m, 0)
    assert not any("kill" in r for r in result.reasons)
    assert result.outcome == "go"
