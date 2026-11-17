# OWNER: M2
"""phases/phase1.py: stages, measure() on hand-built artifacts, Gate 1 outcomes, early halt."""
import gates
import orchestrator
from agents import has_agent
from phases import phase1
from tests.test_m2_helpers import ROOT, ctx_for


def put(ctx, step, data):
    ctx.store.put(step, data, f"# {step}", agent="test")


def claim(url, quote, verified=True):
    return {"claim": "x", "source_url": url, "quote": quote, "verified": verified, "assumption": not verified}


def good_set(ctx):
    put(ctx, "phase1_step1_scope", {"is_digital": True})
    put(ctx, "phase1_step5_market", {"claims": [claim("https://a.org", "quote one is long enough"),
                                                claim("https://b.org", "quote two is long enough")]})
    put(ctx, "phase1_step5_demand_signals", {"claims": [claim("https://a.org", "quote one is long enough"),  # dup
                                                        claim("https://c.org", "quote three long enough"),
                                                        claim("https://d.org", "unverified quote here", False)]})
    put(ctx, "phase1_step5_competitors", {"claims": [], "competitors": [
        {"name": "A", "url": "https://a.org"}, {"name": "B", "url": "https://b.org"}, {"name": "C", "url": ""}]})
    put(ctx, "phase1_step8_skeptic", {"kill_criteria": [{"text": "k", "triggered": False}]})
    put(ctx, "phase1_step9_critique", {"issues": [{"severity": "should_fix", "text": "t"}], "verdict": "ok"})


def test_stage_agents_exist_and_shape():
    assert all(has_agent(n) for stage in phase1.STAGES for n in stage)
    assert phase1.PHASE == 1 and phase1.PIVOT_TO is None
    assert phase1.REVISE == ("discover_synthesizer", "critic_phase1")
    assert phase1.STAGES[5] == ["opportunity_finder", "market_scout", "demand_analyst", "competitor_scanner",
                                "founder_fit", "mom_test_designer"]


def test_measure_on_hand_built_artifacts(tmp_path):
    ctx = ctx_for(tmp_path)
    good_set(ctx)
    m = phase1.measure(ctx)
    assert m == {"scope_ok": 1, "verified_claims": 3, "competitors_found": 2, "kill_triggered": 0,
                 "open_must_fix": 0}


def test_measure_leaves_missing_artifacts_unmeasured(tmp_path):
    ctx = ctx_for(tmp_path)
    put(ctx, "phase1_step1_scope", {"is_digital": "undetermined"})
    assert phase1.measure(ctx) == {"scope_ok": 0}


def _gate(ctx, attempt=0):
    gates.preregister(ctx, 1, phase1.gate_checks(ctx))
    return gates.evaluate(ctx, 1, phase1.measure(ctx), attempt=attempt)


def test_gate1_go(tmp_path):
    ctx = ctx_for(tmp_path)
    good_set(ctx)
    assert _gate(ctx).outcome == "go"


def test_gate1_repeat_then_stop_on_too_few_claims(tmp_path):
    ctx = ctx_for(tmp_path)
    good_set(ctx)
    put(ctx, "phase1_step5_market", {"claims": []})
    put(ctx, "phase1_step5_demand_signals", {"claims": []})
    assert _gate(ctx, attempt=0).outcome == "repeat"
    res = _gate(ctx, attempt=1)
    assert res.outcome == "stop" and any("repeat budget exhausted" in r for r in res.reasons)


def test_gate1_stop_on_kill_criterion(tmp_path):
    ctx = ctx_for(tmp_path)
    good_set(ctx)
    put(ctx, "phase1_step8_skeptic", {"kill_criteria": [{"text": "k", "triggered": True}]})
    assert _gate(ctx).outcome == "stop"


def test_not_digital_halts_and_stops(tmp_path):
    from tests.test_m2_helpers import TransformLLM
    ctx = ctx_for(tmp_path, brief="I will sell handmade candles by mail.")
    ctx.llm = TransformLLM(lambda agent, data: {"is_digital": False, "product_type": "candles",
                                                "excluded_reason": "physical_goods", "reasoning": "MOCKED"}
                           if agent == "scope_classifier" else data)
    result = orchestrator.run(ctx, through=1)
    assert result["outcome"] == "stop" and result["phase"] == 1
    assert not ctx.store.has("phase1_step2_clarification")  # remaining stages skipped
    text = (ctx.out_dir / "phase1_gate_decision.md").read_text(encoding="utf-8")
    assert "STOP" in text and "out of scope" in text


def test_full_mock_phase1_passes_gate(tmp_path):
    ctx = ctx_for(tmp_path)
    result = orchestrator.run(ctx, through=1)
    assert result["history"][0] == (1, 0, "go")
    assert (ctx.out_dir / "phase1_gate_criteria.json").exists()


def test_docstring_lists_founder_keys():
    for key in ("clarify_", "option_", "idea_choice", "interview_notes"):
        assert key in phase1.__doc__
    assert (ROOT / "phases" / "phase1.py").read_text(encoding="utf-8").startswith("# OWNER: M2")
