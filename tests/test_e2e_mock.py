# OWNER: M1
"""End-to-end mocked runs: all six phases with MockLLM and the scripted demo founder (offline)."""
import json

import pytest

import orchestrator
from agents import all_agents
from phases import load_phase
from tests.helpers import assert_log_keys, make_ctx

ROOT = orchestrator.ROOT

# CONTEXT.md section 5: agent name -> artifact stem (idea_generator only runs when the brief has no idea)
EXPECTED = {
    "scope_classifier": "phase1_step1_scope", "clarifier": "phase1_step2_clarification",
    "option_suggester": "phase1_step2_options", "idea_sharpener": "phase1_step4_idea_card",
    "opportunity_finder": "phase1_step5_opportunities", "market_scout": "phase1_step5_market",
    "demand_analyst": "phase1_step5_demand_signals", "competitor_scanner": "phase1_step5_competitors",
    "founder_fit": "phase1_step5_founder_fit", "mom_test_designer": "phase1_step5_interview_script",
    "feasibility_analyst": "phase1_step6_feasibility", "interview_analyst": "phase1_step6_interview_findings",
    "opportunity_scorer": "phase1_step7_opportunity_scores", "skeptic": "phase1_step8_skeptic",
    "discover_synthesizer": "phase1_step9_discover_report", "critic_phase1": "phase1_step9_critique",
    "competitor_analyst": "phase2_step1_competitor_analysis", "lean_canvas_drafter": "phase2_step2_lean_canvas",
    "demand_test_designer": "phase2_step3_demand_test_plan", "landing_page_builder": "phase2_step4_landing_page",
    "demand_results": "phase2_step5_demand_results", "assumption_auditor": "phase2_step6_assumptions",
    "risk_analyst": "phase2_step7_risks", "scorecard_builder": "phase2_step8_scorecard",
    "validation_synthesizer": "phase2_step9_validation_report", "critic_phase2": "phase2_step9_critique",
    "spec_writer": "phase3_step1_spec", "copywriter": "phase3_step2_page_copy", "builder": "phase3_step3_build",
    "user_docs_writer": "phase3_step4_user_docs", "qa_agent": "phase3_step5_qa_report",
    "content_reviewer": "phase3_step6_content_review",
    "pricing_analyst": "phase4_step1_pricing", "offer_packager": "phase4_step2_offer",
    "policy_drafter": "phase4_step3_policies", "compliance_reviewer_phase4": "phase4_step4_compliance_review",
    "channel_planner": "phase5_step1_channel_plan", "store_page_builder": "phase5_step2_store_page",
    "launch_post_drafter": "phase5_step3_launch_posts", "compliance_reviewer_phase5": "phase5_step4_launch_review",
    "sale_to_cash": "phase5_step5_sale_to_cash",
    "support_drafter": "phase6_step1_support_replies", "metrics_analyst": "phase6_step2_metrics",
    "persevere_pivot_memo": "phase6_step3_persevere_pivot_memo",
}
ALL_REGISTERED = set(EXPECTED) <= set(all_agents())


def _run(tmp_path, brief="brief_strong.md", inputs="founder_inputs.json"):
    ctx = make_ctx(tmp_path, brief=(ROOT / "demo" / brief).read_text(encoding="utf-8"),
                   founder_inputs=ROOT / "demo" / inputs)
    return ctx, orchestrator.run(ctx, through=6)


def test_e2e_mock_completes(tmp_path):
    ctx, result = _run(tmp_path)
    assert result["outcome"] in {"go", "repeat", "pivot", "stop"}
    for phase, _, _ in result["history"]:
        assert (ctx.out_dir / f"phase{phase}_gate_criteria.json").exists()
        assert (ctx.out_dir / f"phase{phase}_gate_decision.md").exists()
    entries = json.loads(ctx.log.path.read_text(encoding="utf-8"))
    assert_log_keys(entries)
    assert any(e["action"] == "run_finished" for e in entries)
    # nothing outward-facing without approval
    for e in entries:
        if e["action"].startswith("released:"):
            assert e["approved_by"] == "founder"
    # every scripted founder answer is labeled
    assert all(e.get("provenance") == "SCRIPTED" for e in entries if e["action"].startswith("founder_input:"))


def test_e2e_mock_with_stub_phases_runs_zero_stages(tmp_path):
    stubbed = [n for n in range(1, 7) if not load_phase(n).STAGES]
    if not stubbed:
        pytest.skip("no stub phases left")
    ctx, result = _run(tmp_path)
    logged = {e["phase"] for e in ctx.log.entries() if e["action"] == "phase_stubbed"}
    assert set(stubbed) & {h[0] for h in result["history"]} <= logged


def test_e2e_registered_agents_of_passed_phases_wrote_artifacts(tmp_path):
    ctx, result = _run(tmp_path)
    registered = all_agents()
    for phase, _, outcome in result["history"]:
        if outcome != "go":
            continue
        for stage in load_phase(phase).STAGES:
            for name in stage:
                if name in registered:
                    assert ctx.store.has(registered[name].step), f"{name} wrote no artifact"


@pytest.mark.xfail(not ALL_REGISTERED, reason="not every agent from CONTEXT section 5 is registered yet",
                   strict=False)
def test_e2e_every_artifact_stem_exists(tmp_path):
    ctx, result = _run(tmp_path)
    missing = [stem for stem in EXPECTED.values() if not ctx.store.has(stem)]
    assert not missing, f"missing artifacts: {missing}"
    assert (ctx.out_dir / "phase2_step4_landing_page.html").exists()
    assert (ctx.out_dir / "phase5_step2_store_page.html").exists()
    assert (ctx.out_dir / "payment_test_log.md").exists()


@pytest.mark.xfail(not ALL_REGISTERED, reason="needs the Phase 2 agents and gate metrics", strict=False)
def test_e2e_weak_brief_stops_at_gate_2(tmp_path):
    ctx, result = _run(tmp_path, "brief_weak.md", "founder_inputs_weak.json")
    assert result["outcome"] == "stop"
    assert "STOP" in (ctx.out_dir / "phase2_gate_decision.md").read_text(encoding="utf-8")
