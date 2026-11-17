# OWNER: M2
"""Every Phase 1 agent: registered, prompt and fixture exist, a mock run writes valid artifacts and log
entries, and a guardrail violation in the model output never reaches the artifacts. Plus agent-specific
honesty rules that are enforced in code."""
import json

import pytest

from agents import all_agents, get_agent
from tests.test_m2_helpers import (DECISION_KEYS, PHASE1_AGENTS, ROOT, STEPS, TransformLLM, ctx_for, run_until)

VIOLATION = " We guarantee 5-star results, a great idea."
DEMO = json.loads((ROOT / "demo" / "founder_inputs.json").read_text(encoding="utf-8"))
TOOLS = {"opportunity_finder": ["search", "fetch"], "market_scout": ["search", "fetch"],
         "demand_analyst": ["search", "fetch"], "competitor_scanner": ["search", "fetch"],
         "idea_generator": ["search"]}


def inputs(**over):
    d = dict(DEMO)
    d.update(over)
    return d


def only(agent_name, new_data):
    """Transform: replace the model output for one agent."""
    return lambda agent, data: dict(new_data) if agent == agent_name else data


def test_all_17_phase1_agents_are_in_stages():
    assert sorted(PHASE1_AGENTS) == sorted(STEPS)
    assert len(PHASE1_AGENTS) == 17


@pytest.mark.parametrize("name", sorted(STEPS))
def test_registered_with_prompt_and_fixture(name):
    assert name in all_agents()
    a = get_agent(name)
    assert a.name == name and a.phase == 1 and a.step == STEPS[name]
    assert sorted(a.tools) == sorted(TOOLS.get(name, []))
    assert (ROOT / "agents" / f"{name}.py").exists()
    prompt = (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    for heading in (f"# {name}", "## Role", "## Task", "## Inputs", "## Output", "## Rules"):
        assert heading in prompt, f"{name} prompt lacks {heading}"
    fixture = (ROOT / "tests" / "fixtures" / "mock" / f"{name}.json").read_text(encoding="utf-8")
    assert "MOCKED" in fixture
    for url in __import__("re").findall(r"https?://[^\s\"]+", fixture):
        assert url.startswith("https://example.com/mock/"), f"{name} fixture has a real-looking URL {url}"


@pytest.mark.parametrize("name", PHASE1_AGENTS)
def test_mock_run_writes_artifact_and_log(name, tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, name)
    agent = get_agent(name)
    before = len(ctx.log.entries())
    agent.run(ctx)
    step = STEPS[name]
    assert (ctx.out_dir / f"{step}.json").exists() and (ctx.out_dir / f"{step}.md").exists()
    data = ctx.store.get(step)
    for k in agent.required_keys:
        assert k in data, f"{name}: missing {k}"
    new = ctx.log.entries()[before:]
    assert any(e["agent"] == name for e in new)
    for e in ctx.log.entries():
        assert all(k in e for k in DECISION_KEYS), e
    assert "MOCKED" in (ctx.out_dir / f"{step}.md").read_text(encoding="utf-8")


def _inject(agent, data):
    best = [None, None, -1]

    def walk(obj):
        items = obj.items() if isinstance(obj, dict) else enumerate(obj) if isinstance(obj, list) else []
        for k, v in items:
            if isinstance(v, str) and len(v) > best[2] and k not in ("source_url", "url", "_marker"):
                best[:] = [obj, k, len(v)]
            elif isinstance(v, (dict, list)):
                walk(v)
    walk(data)
    if best[0] is not None:
        best[0][best[1]] += VIOLATION
    return data


@pytest.mark.parametrize("name", PHASE1_AGENTS)
def test_guardrail_violation_is_blocked(name, tmp_path):
    ctx = ctx_for(tmp_path)
    if name == "idea_generator":  # force the generation path (no idea in the clarification)
        run_until(ctx, name)
        clar = ctx.store.get("phase1_step2_clarification")
        clar["idea"] = None
        ctx.store.put("phase1_step2_clarification", clar, "# test", agent="test")
    else:
        run_until(ctx, name)
    ctx.llm = TransformLLM(lambda agent, data: _inject(agent, data))
    try:
        get_agent(name).run(ctx)
    except Exception:  # noqa: BLE001 - refusing the whole output also blocks it
        pass
    for f in ctx.out_dir.rglob("*"):
        if f.is_file():
            assert "we guarantee 5-star" not in f.read_text(encoding="utf-8").lower(), f"{name} leaked into {f.name}"


# ---------------------------------------------------------------- scope

def test_vague_brief_is_undetermined_not_rejected(tmp_path):
    ctx = ctx_for(tmp_path, brief="A website that sells something.")
    ctx.llm = TransformLLM(only("scope_classifier", {"is_digital": "undetermined", "product_type": "unknown",
                                                     "excluded_reason": None, "reasoning": "MOCKED vague"}))
    get_agent("scope_classifier").run(ctx)
    assert ctx.store.get("phase1_step1_scope")["is_digital"] == "undetermined"
    assert "halt_phase" not in ctx.extra


def test_excluded_product_halts(tmp_path):
    ctx = ctx_for(tmp_path, brief="A crypto trading signals app.")
    ctx.llm = TransformLLM(only("scope_classifier", {"is_digital": True, "product_type": "app",
                                                     "excluded_reason": "financial_or_crypto", "reasoning": "MOCKED"}))
    get_agent("scope_classifier").run(ctx)
    scope = ctx.store.get("phase1_step1_scope")
    assert scope["is_digital"] is False and scope["excluded_reason"] == "financial_or_crypto"
    assert "out of scope" in ctx.extra["halt_phase"]


# ---------------------------------------------------------------- clarifier and options

def test_clarifier_asks_product_type_first_and_reasks_unknown_once(tmp_path):
    ctx = ctx_for(tmp_path, brief="I want to sell something to students.",
                  founder_inputs=inputs(clarify_product_type="I don't know", clarify_target_customer="unknown",
                                        clarify_problem="", clarify_budget="50"))
    ctx.llm = TransformLLM(only("clarifier", {"stated": {}, "idea": None, "questions": []}))
    get_agent("clarifier").run(ctx)
    d = ctx.store.get("phase1_step2_clarification")
    asked = d["questions_asked"]
    assert asked[0]["field"] == "product_type" and "digital" in asked[0]["question"]
    assert sum(1 for q in asked if q["round"] == 1) <= 4
    pt = [q for q in asked if q["field"] == "product_type"]
    assert len(pt) == 2 and pt[1]["round"] == 2  # asked again exactly once
    assert d["fields"]["product_type"]["status"] == "unknown"
    assert d["fields"]["budget"] == {"value": "50", "status": "answered", "source": "founder"}
    assert any(e["action"] == "clarify_question" for e in ctx.log.entries())


def test_clarifier_skip_stops(tmp_path):
    ctx = ctx_for(tmp_path, brief="Something.", founder_inputs=inputs(clarify_product_type="skip"))
    ctx.llm = TransformLLM(only("clarifier", {"stated": {}, "idea": None, "questions": []}))
    get_agent("clarifier").run(ctx)
    d = ctx.store.get("phase1_step2_clarification")
    assert d["stopped_by_founder"] is True and len(d["questions_asked"]) == 1


def test_clarifier_redacts_card_numbers(tmp_path):
    ctx = ctx_for(tmp_path, brief="Something.",
                  founder_inputs=inputs(clarify_product_type="ebook, my card is 4111 1111 1111 1111"))
    ctx.llm = TransformLLM(only("clarifier", {"stated": {}, "idea": None, "questions": []}))
    get_agent("clarifier").run(ctx)
    text = (ctx.out_dir / "phase1_step2_clarification.json").read_text(encoding="utf-8")
    assert "4111 1111 1111 1111" not in text
    assert "4111 1111 1111 1111" not in ctx.log.path.read_text(encoding="utf-8")


def test_option_rejected_stays_unknown_and_approved_is_logged(tmp_path):
    ctx = ctx_for(tmp_path, founder_inputs=inputs(option_distribution_channel="none of these"))
    run_until(ctx, "option_suggester")
    get_agent("option_suggester").run(ctx)
    d = ctx.store.get("phase1_step2_options")
    assert d["fields"]["distribution_channel"]["status"] == "unknown_confirmed"

    ctx2 = ctx_for(tmp_path / "b")
    run_until(ctx2, "option_suggester")
    get_agent("option_suggester").run(ctx2)
    d2 = ctx2.store.get("phase1_step2_options")
    assert d2["fields"]["distribution_channel"]["status"] == "suggested_approved"
    assert any(e["action"] == "option_decision:distribution_channel" and e["approved_by"] == "founder"
               for e in ctx2.log.entries())


def test_option_suggester_rechecks_scope_and_halts(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "option_suggester")
    ctx.llm = TransformLLM(only("scope_classifier", {"is_digital": "undetermined", "product_type": "unknown",
                                                     "excluded_reason": None, "reasoning": "MOCKED"}))
    get_agent("option_suggester").run(ctx)
    assert ctx.store.get("phase1_step1_scope")["rechecked_after"]
    assert "not clearly digital" in ctx.extra["halt_phase"]


# ---------------------------------------------------------------- idea

def test_idea_generator_skips_when_brief_has_idea(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "idea_generator")
    get_agent("idea_generator").run(ctx)
    assert ctx.store.get("phase1_step3_idea_candidates")["skipped"] is True
    assert ctx.store.get("phase1_step3_idea_choice")["source"] == "founder_brief"


def test_idea_generator_asks_founder_to_pick(tmp_path):
    ctx = ctx_for(tmp_path, founder_inputs=inputs(idea_choice="2"))
    run_until(ctx, "idea_generator")
    clar = ctx.store.get("phase1_step2_clarification")
    clar["idea"] = None
    ctx.store.put("phase1_step2_clarification", clar, "# test", agent="test")
    get_agent("idea_generator").run(ctx)
    cands = ctx.store.get("phase1_step3_idea_candidates")
    assert cands["skipped"] is False and len(cands["candidates"]) >= 3
    assert ctx.store.get("phase1_step3_idea_choice")["chosen"] == cands["candidates"][1]["name"]


def test_idea_sharpener_reads_pivot_notes(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "idea_sharpener")
    ctx.store.put("pivot_notes", {"reason": "Gate 2 pivot", "next_best_alternative": {"name": "ALT-X"}}, "#",
                  agent="orchestrator")
    seen = {}

    def spy(agent, data):
        return data
    ctx.llm = TransformLLM(spy)
    msg = get_agent("idea_sharpener").build_user_message(ctx)
    assert "ALT-X" in msg
    get_agent("idea_sharpener").run(ctx)
    assert ctx.store.get("phase1_step4_idea_card")["pivoted"] is True
    assert not seen


# ---------------------------------------------------------------- evidence agents

def test_research_agent_wraps_pages_as_untrusted(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "market_scout")
    msg = get_agent("market_scout").build_user_message(ctx)
    assert 'untrusted=\\"true\\"' in msg or 'untrusted="true"' in msg
    tool_calls = [e for e in ctx.log.entries() if e["agent"] == "market_scout" and e["action"] in ("search", "fetch")]
    assert 1 <= len(tool_calls) <= 8


def test_insufficient_evidence_is_computed_in_code(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "market_scout")
    ctx.llm = TransformLLM(only("market_scout", {
        "market_definition": {"segment": "MOCKED", "size_note": "unknown"}, "insufficient_evidence": False,
        "claims": [{"claim": "MOCKED unsourced", "source_url": "", "quote": "", "verified": None,
                    "assumption": False}]}))
    get_agent("market_scout").run(ctx)
    d = ctx.store.get("phase1_step5_market")
    assert d["insufficient_evidence"] is True
    assert d["claims"][0]["verified"] is False and d["claims"][0]["assumption"] is True


def test_competitor_pricing_without_verified_claim_is_assumption(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "competitor_scanner")
    ctx.llm = TransformLLM(only("competitor_scanner", {
        "competitors": [{"name": "Rival", "url": "https://rival.example.org", "pricing": "9 USD",
                         "positioning": "MOCKED"}], "claims": [], "insufficient_evidence": False}))
    get_agent("competitor_scanner").run(ctx)
    c = ctx.store.get("phase1_step5_competitors")["competitors"][0]
    assert c["pricing"].startswith("ASSUMPTION") and c["pricing_sourced"] is False


def test_ratings_without_evidence_refs_become_unknown(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "founder_fit")
    ctx.llm = TransformLLM(only("founder_fit", {"rating": "strong", "reasoning": "MOCKED", "evidence_refs": []}))
    get_agent("founder_fit").run(ctx)
    assert ctx.store.get("phase1_step5_founder_fit")["rating"] == "unknown"


def test_mom_test_drops_pitching_questions(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "mom_test_designer")
    ctx.llm = TransformLLM(only("mom_test_designer", {
        "questions": [{"text": "Would you buy a template pack for 20 USD?", "why": "MOCKED"},
                      {"text": "When did you last chase a late invoice?", "why": "MOCKED"}],
        "rules": ["MOCKED"], "avoid_list": ["MOCKED"]}))
    get_agent("mom_test_designer").run(ctx)
    d = ctx.store.get("phase1_step5_interview_script")
    assert [q["text"] for q in d["questions"]] == ["When did you last chase a late invoice?"]
    assert d["dropped_questions"]


def test_interview_analyst_never_invents_interviews(tmp_path):
    ctx = ctx_for(tmp_path, founder_inputs=inputs(interview_notes=""))
    calls = []
    ctx.llm = TransformLLM(lambda agent, data: calls.append(agent) or data)
    get_agent("interview_analyst").run(ctx)
    d = ctx.store.get("phase1_step6_interview_findings")
    assert d["findings"] == "unknown" and d["pain_points"] == [] and d["interview_count"] == 0
    assert "interview_analyst" not in calls


def test_interview_analyst_labels_scripted_notes_sample(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "interview_analyst")
    get_agent("interview_analyst").run(ctx)
    d = ctx.store.get("phase1_step6_interview_findings")
    assert d["provenance"] == "SAMPLE"
    assert (ctx.out_dir / "phase1_step6_interview_findings.md").read_text(encoding="utf-8").startswith(
        "PROVENANCE: SAMPLE")


# ---------------------------------------------------------------- scoring, skeptic, report, critic

def test_scorer_keeps_founder_idea_as_chosen_and_clamps(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "opportunity_scorer")
    ctx.llm = TransformLLM(only("opportunity_scorer", {
        "ranked": [{"name": "Alt", "score": 14, "reasons": ["MOCKED"]},
                   {"name": "Mine", "score": 4, "reasons": ["MOCKED"], "is_founder_idea": True}],
        "chosen": "Alt"}))
    get_agent("opportunity_scorer").run(ctx)
    d = ctx.store.get("phase1_step7_opportunity_scores")
    assert d["chosen"] == "Mine" and d["ranked"][0]["score"] == 10.0 and d["switch_suggested"] is True


def test_skeptic_trigger_needs_evidence(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "skeptic")
    ctx.llm = TransformLLM(only("skeptic", {
        "risks": ["MOCKED risk"], "would_change_mind": "MOCKED",
        "kill_criteria": [{"text": "MOCKED guess", "triggered": True},
                          {"text": "MOCKED shown", "triggered": True, "evidence": "interview findings: no one paid"}]}))
    get_agent("skeptic").run(ctx)
    k = ctx.store.get("phase1_step8_skeptic")["kill_criteria"]
    assert [x["triggered"] for x in k] == [False, True]


def test_synthesizer_downgrades_unsupported_findings(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "discover_synthesizer")
    ctx.llm = TransformLLM(only("discover_synthesizer", {
        "summary": "MOCKED", "assumptions": [], "limitations": [], "confidence": "high",
        "findings": [{"text": "MOCKED cited", "claim_ids": ["C1"]}, {"text": "MOCKED bad id", "claim_ids": ["C99"]},
                     {"text": "MOCKED nothing"}]}))
    get_agent("discover_synthesizer").run(ctx)
    f = ctx.store.get("phase1_step9_discover_report")["findings"]
    assert f[0]["claim_ids"] == ["C1"] and not f[0].get("assumption")
    assert f[1]["assumption"] is True and f[1]["unverified_claim_ids"] == ["C99"]
    assert f[2]["text"].startswith("ASSUMPTION")


def test_critic_flags_praise_in_code(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "critic_phase1")
    rep = ctx.store.get("phase1_step9_discover_report")
    rep["summary"] = "This is an excellent opportunity."
    ctx.store.put("phase1_step9_discover_report", rep, "# t", agent="test")
    get_agent("critic_phase1").run(ctx)
    c = ctx.store.get("phase1_step9_critique")
    assert c["verdict"] == "revise"
    assert any(i["severity"] == "must_fix" and i.get("found_in_code") for i in c["issues"])


def test_empty_search_is_logged_and_queries_are_keywords(tmp_path):
    from agents.m2_common import short
    assert short("a bilingual Notion and Google Sheets template pack", 3) == "bilingual Notion Google"
    ctx = ctx_for(tmp_path)
    run_until(ctx, "market_scout")
    ctx.tools.search = lambda agent, q: []  # e.g. the search engine served a bot-check page
    results, pages = get_agent("market_scout").gather(ctx)
    assert results == [] and pages == []
    empties = [e for e in ctx.log.entries() if e["action"] == "search_empty"]
    assert len(empties) == 3 and all(e["agent"] == "market_scout" for e in empties)
