"""Fixes after the first real-model run of Phases 2 and 3 (Groq gpt-oss-20b, M1's report).

Three problems stopped both gates: the Phase 2 critic marked labeled MOCKED demand results as must_fix, the
Phase 3 content reviewer marked ASSUMPTION-labeled claims as must_fix, and the spec asked for a price and a
policy name that a Phase 3 page can never contain. Offline: scripted model answers, no network.
"""
import json
from pathlib import Path

import pytest

from agents.spec_writer import drop_later_phase_tests, normalize_acceptance_tests
from phases import phase3
from tests.test_m3_helpers import ScriptedLLM, fixture, get_agent, make_ctx, put

ROOT = Path(__file__).resolve().parent.parent


def _prompt(name):
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def _test(tid, text, ctype="text_contains"):
    return {"id": tid, "description": f"MOCKED {tid}", "check": {"type": ctype, "path": "index.html", "text": text}}


# ---------------------------------------------------------------- spec_writer: tests Phase 3 can pass

@pytest.mark.parametrize("text", ["$19", "19 USD", "EGP 200", "€5", "Privacy Policy", "Terms of Service",
                                  "Refund policy", "price section", "Pricing"])
def test_TC_M3_real_spec_drops_price_and_policy_tests(text):
    kept, dropped = drop_later_phase_tests([_test("AT1", text)])
    assert kept == [] and [d["id"] for d in dropped] == ["AT1"]
    assert "Phase 4" in dropped[0]["reason"] and dropped[0]["text"] == text


@pytest.mark.parametrize("text", ["bilingual", "Notion", "What is included", "Sign up", "Onboarding checklist",
                                  "Demo only: nothing is sent or stored", "Bilingual Project Tracker", "precise offer",
                                  "Price: set in Phase 4", "Policies drafted in Phase 4"])
def test_TC_M3_real_spec_keeps_phase3_texts(text):
    kept, dropped = drop_later_phase_tests([_test("AT1", text)])
    assert [t["id"] for t in kept] == ["AT1"] and dropped == []


def test_TC_M3_real_spec_file_exists_test_is_never_dropped():
    test = _test("AT1", "$19", ctype="file_exists")  # the text of a file_exists check is not used
    kept, dropped = drop_later_phase_tests([test])
    assert kept == [test] and dropped == []


def test_TC_M3_real_spec_empty_and_malformed_input():
    assert drop_later_phase_tests(None) == ([], [])
    assert drop_later_phase_tests([]) == ([], [])
    kept, dropped = drop_later_phase_tests(normalize_acceptance_tests(["not a test", {"id": "AT9"}]))
    assert [t["id"] for t in kept] == ["AT9"] and dropped == []


def _spec_with_bad_tests():
    spec = fixture("spec_writer")
    spec["acceptance_tests"] += [_test("AT90", "$19"), _test("AT91", "Privacy Policy")]
    return spec


def test_TC_M3_real_spec_agent_records_the_dropped_tests(tmp_path):
    agent = get_agent("spec_writer")
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"spec_writer": _spec_with_bad_tests()}), seed=agent.inputs)
    result = agent.run(ctx)
    from agents.spec_writer import STRUCTURAL_REASON, structural_acceptance_tests
    ids = [t["id"] for t in result.data["acceptance_tests"]]
    assert "AT90" not in ids and "AT91" not in ids
    # M1 review 14:54: acceptance tests are structural and set in code; the model's own tests are all recorded.
    assert result.data["acceptance_tests"] == structural_acceptance_tests()
    dropped = {d["id"]: d["reason"] for d in result.data["dropped_tests"]}
    assert "Phase 4 and 5" in dropped["AT90"] and "Phase 4 and 5" in dropped["AT91"]
    assert {t["id"] for t in fixture("spec_writer")["acceptance_tests"]} <= {k for k, v in dropped.items()
                                                                           if v == STRUCTURAL_REASON}


def test_TC_M3_real_corrected_spec_reaches_full_acceptance_pass_ratio(tmp_path):
    seeds = ["phase2_step2_lean_canvas", "phase2_step9_validation_report", "phase2_step3_demand_test_plan",
             "phase1_step4_idea_card", "phase1_step2_clarification", "phase2_step4_landing_page"]
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"spec_writer": _spec_with_bad_tests()}), seed=seeds)
    for stage in phase3.STAGES:
        for name in stage:
            get_agent(name).run(ctx)
    qa = ctx.store.get("phase3_step5_qa_report")
    assert qa["pass_ratio"] == 1.0 and qa["site_checks"]["passed"] is True
    assert phase3.measure(ctx)["acceptance_pass_ratio"] == 1.0


# ---------------------------------------------------------------- the report states where MOCKED data comes from

def _synth_ctx(tmp_path, provenance, summary):
    agent = get_agent("validation_synthesizer")
    resp = fixture("validation_synthesizer")
    resp["summary"] = summary
    resp["limitations"] = ["Interviews are SAMPLE."]
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"validation_synthesizer": resp}), seed=agent.inputs)
    results = ctx.store.get("phase2_step5_demand_results")
    results["provenance"] = provenance
    put(ctx, "phase2_step5_demand_results", results)
    return agent, ctx


@pytest.mark.parametrize("prov", ["MOCKED", "SAMPLE"])
def test_TC_M3_real_report_states_mocked_provenance_in_summary_and_limitations(tmp_path, prov):
    agent, ctx = _synth_ctx(tmp_path, prov, "The test reached 140 sign-ups against a target of 100.")
    data = agent.run(ctx).data
    assert prov in data["summary"] and "not from real visitors" in data["summary"]
    assert any(prov in s for s in data["limitations"])


def test_TC_M3_real_report_summary_is_not_changed_for_real_demand(tmp_path):
    summary = "The test reached 140 sign-ups against a target of 100."
    agent, ctx = _synth_ctx(tmp_path, "REAL", summary)
    data = agent.run(ctx).data
    assert data["summary"] == summary
    assert not any("MOCKED" in s for s in data["limitations"])


def test_TC_M3_real_report_does_not_repeat_provenance_already_in_summary(tmp_path):
    summary = "140 sign-ups (MOCKED, not real visitors) against a target of 100."
    agent, ctx = _synth_ctx(tmp_path, "MOCKED", summary)
    assert agent.run(ctx).data["summary"] == summary


# ---------------------------------------------------------------- prompts carry the corrected rules

def test_TC_M3_real_critic_accepts_labeled_mocked_input_but_still_blocks_real_dishonesty():
    text = _prompt("critic_phase2")
    assert "acceptable when the report states where it comes from" in text
    assert "must_fix` only when the provenance is missing" in text
    assert "always `must_fix`" in text and "flattery" in text and "income promises" in text
    assert "MOCKED data presented as real are always" not in text


def test_TC_M3_real_synthesizer_prompt_asks_for_provenance_next_to_demand_numbers():
    assert "provenance (MOCKED, SAMPLE or REAL) next to every demand number" in _prompt("validation_synthesizer")


def test_TC_M3_real_content_reviewer_treats_assumption_label_as_honest():
    text = _prompt("content_reviewer")
    assert "labeled `ASSUMPTION` is honest handling" in text
    assert "Fake proof, promises, invented numbers and unlabeled sample content are always `must_fix`" in text


def test_TC_M3_real_spec_prompt_forbids_price_and_policy_tests():
    text = _prompt("spec_writer")
    assert "Never test a price" in text and "policy name" in text


@pytest.mark.parametrize("name", ["builder", "copywriter"])
def test_TC_M3_real_faq_prompt_forbids_system_limits(name):
    text = _prompt(name)
    assert "Never mention technical limits of the system" in text and "address buyer questions" in text


def test_TC_M3_real_critic_fixture_is_still_valid_json_with_required_keys():
    data = json.loads((ROOT / "tests" / "fixtures" / "mock" / "critic_phase2.json").read_text(encoding="utf-8"))
    assert set(data) >= {"issues", "verdict"}
