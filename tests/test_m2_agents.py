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


# ---------------------------------------------------------------- messy answers from small real models

def test_helpers_read_messy_values():
    from agents.m2_common import id_list, norm_severity, to_number, truthy
    assert to_number("7/10") == 7.0 and to_number("score: 6.5") == 6.5 and to_number("n/a") is None
    assert id_list("C1, C2") == ["C1", "C2"] and id_list(["C3"]) == ["C3"]
    assert norm_severity("Must-Fix") == "must_fix" and norm_severity("minor") == "should_fix"
    assert truthy("true") and truthy("Yes") and not truthy("false") and not truthy(None)


def test_messy_scorer_synthesizer_critic_outputs(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "opportunity_scorer")
    ctx.llm = TransformLLM(only("opportunity_scorer", {
        "ranked": [{"name": "Mine", "score": "6/10", "reasons": "MOCKED one reason", "is_founder_idea": "true"},
                   {"name": "Alt", "score": "9", "reasons": []}], "chosen": "Mine"}))
    get_agent("opportunity_scorer").run(ctx)
    s = ctx.store.get("phase1_step7_opportunity_scores")
    assert s["chosen"] == "Mine" and s["ranked"][0]["score"] == 9.0 and s["switch_suggested"] is True

    run_until(ctx, "discover_synthesizer")
    ctx.llm = TransformLLM(only("discover_synthesizer", {
        "summary": "MOCKED", "findings": [{"text": "MOCKED", "claim_ids": "C1, C2"}],
        "assumptions": "MOCKED one", "limitations": [], "confidence": "Medium"}))
    get_agent("discover_synthesizer").run(ctx)
    r = ctx.store.get("phase1_step9_discover_report")
    assert r["findings"][0]["claim_ids"] == ["C1", "C2"] and r["confidence"] == "medium"
    assert r["assumptions"] == ["MOCKED one"]

    ctx.llm = TransformLLM(only("critic_phase1", {"issues": [{"severity": "Must-Fix", "text": "MOCKED"}],
                                                  "verdict": "OK."}))
    get_agent("critic_phase1").run(ctx)
    c = ctx.store.get("phase1_step9_critique")
    assert c["issues"][0]["severity"] == "must_fix" and c["verdict"] == "revise"


def test_messy_scope_and_kill_criteria(tmp_path):
    ctx = ctx_for(tmp_path)
    ctx.llm = TransformLLM(only("scope_classifier", {"is_digital": "Yes", "product_type": "MOCKED",
                                                     "excluded_reason": "null", "reasoning": "MOCKED"}))
    get_agent("scope_classifier").run(ctx)
    assert ctx.store.get("phase1_step1_scope")["is_digital"] is True
    run_until(ctx, "skeptic")
    ctx.llm = TransformLLM(only("skeptic", {"risks": [], "would_change_mind": [], "kill_criteria": [
        {"text": "MOCKED", "triggered": "true", "evidence": "MOCKED interview findings"}]}))
    get_agent("skeptic").run(ctx)
    assert ctx.store.get("phase1_step8_skeptic")["kill_criteria"][0]["triggered"] is True


def test_product_terms_and_topic_queries():
    from agents.m2_common import product_terms, topic_queries
    card = {"solution": "A bilingual Notion and Google Sheets template pack for designers",
            "customer": "Freelance designers in Egypt", "problem": "They lose track of unpaid invoices"}
    assert product_terms(card) == "Notion Google Sheets template"
    t = topic_queries(card)
    assert t["cust"] == "Freelance designers" and t["prob"] == "unpaid invoices"
    assert product_terms({"solution": "a weekly planner"}) == "planner"


def test_competitor_url_not_in_search_results_is_not_counted(tmp_path):
    ctx = ctx_for(tmp_path)
    run_until(ctx, "competitor_scanner")
    ctx.llm = TransformLLM(only("competitor_scanner", {
        "competitors": [{"name": "Invented", "url": "https://invented-rival.org/x", "pricing": "unknown",
                         "positioning": "MOCKED"},
                        {"name": "Seen", "url": "https://example.com/mock/cs1", "pricing": "unknown",
                         "positioning": "MOCKED"}], "claims": [], "insufficient_evidence": False}))
    get_agent("competitor_scanner").run(ctx)
    comps = ctx.store.get("phase1_step5_competitors")["competitors"]
    assert comps[0]["url"] == "" and comps[0]["url_not_in_results"] == "https://invented-rival.org/x"
    assert comps[1]["url"] == "https://example.com/mock/cs1"


def test_hedged_kill_evidence_does_not_trigger():
    from agents.m2_common import norm_risks
    d = norm_risks({"risks": [], "kill_criteria": [
        {"text": "Budget too small", "triggered": True, "evidence": "The budget might be insufficient."},
        {"text": "No demand evidence", "triggered": True, "evidence": "demand_signals has no verified claims."}]})
    assert d["kill_criteria"][0]["triggered"] is False and d["kill_criteria"][0]["triggered_on_speculation"]
    assert d["kill_criteria"][1]["triggered"] is True


def test_critic_issue_about_labelled_assumption_is_not_must_fix():
    from agents.critic_phase1 import LABELLED_ASSUMPTION
    assert LABELLED_ASSUMPTION.search("The finding 'ASSUMPTION: Canva has a Pro plan' should be marked")
    assert not LABELLED_ASSUMPTION.search("The finding 'Canva has a Pro plan' cites no claim")


def test_founder_time_is_computed_in_code():
    from agents.m2_common import founder_time
    t = founder_time("**Time:** 8 hours per week for 3 months.")
    assert t["hours_per_week"] == 8 and t["weeks"] == 13 and t["total_hours"] == 104
    assert founder_time("**Time:** 2 hours per week.") == {"hours_per_week": 2.0, "note": founder_time("2 hours per week")["note"]}
    assert founder_time("no time given") is None


def test_time_kill_criterion_contradicted_by_its_own_numbers(tmp_path):
    from types import SimpleNamespace
    sk = get_agent("skeptic")
    ctx = SimpleNamespace(brief="**Time:** 8 hours per week for 3 months.")
    d = sk.post_process(ctx, {"risks": [], "would_change_mind": [], "kill_criteria": [
        {"text": "Founder time is insufficient", "triggered": True,
         "evidence": "8 hours per week for 13 weeks, totaling 104 hours, but the project requires 40 hours."},
        {"text": "Founder time is insufficient", "triggered": True,
         "evidence": "104 hours available but the build needs 300 hours."}]})
    assert d["kill_criteria"][0]["triggered"] is False and d["kill_criteria"][0]["triggered_contradicted"]
    assert d["kill_criteria"][1]["triggered"] is True


def test_queries_never_repeat_words():
    from agents.m2_common import dedupe_words
    assert dedupe_words("Freelance graphic Freelance graphic designers") == "Freelance graphic designers"


def test_verified_quote_from_unrelated_page_is_not_evidence(tmp_path):
    from types import SimpleNamespace
    from agents.m2_common import check_on_topic
    logged = []
    ctx = SimpleNamespace(log=SimpleNamespace(action=lambda *a, **k: logged.append((a, k))))
    card = {"customer": "Freelance graphic designers in Egypt", "problem": "They lose track of unpaid invoices",
            "solution": "A Notion and Google Sheets template pack"}
    data = {"claims": [
        {"claim": "Designers need invoice tracking", "source_url": "https://webmd.example/physio", "verified": True,
         "assumption": False, "quote": "Physical therapy is a common treatment that can help you recover."},
        {"claim": "Freelancers send invoices late", "source_url": "https://hn.example/1", "verified": True,
         "assumption": False, "quote": "As a freelance designer I chase unpaid invoices every month."},
        {"claim": "Designers like quizzes", "source_url": "https://quiz.example/1", "verified": True,
         "assumption": False, "quote": "Quiz: which design era are you? Automoviles, Alimentos, Medicina"},
        {"claim": "MOCKED claim", "source_url": "https://example.com/mock/1", "verified": True, "mocked": True,
         "assumption": False, "quote": "MOCKED quote text that is long enough"}]}
    check_on_topic(ctx, data, card, "demand_analyst")
    off, on, one_word, mocked = data["claims"]
    assert one_word["verified"] is False  # a single shared word ("design") is not enough
    assert off["verified"] is False and off["assumption"] is True and off["check"].startswith("off-topic")
    assert on["verified"] is True and "invoi" in on["topic_terms"]
    assert mocked["verified"] is True
    assert len(logged) == 2 and logged[0][0][1] == "claim_downgraded"


def test_feasibility_with_wrong_time_arithmetic_becomes_unknown():
    from types import SimpleNamespace
    fa = get_agent("feasibility_analyst")
    ctx = SimpleNamespace(brief="**Time:** 8 hours per week for 3 months.", store=SimpleNamespace(has=lambda s: True))
    bad = fa.post_process(ctx, {"rating": "weak", "evidence_refs": ["phase1_step5_competitors"],
                                "effort_hours_estimate": 40,
                                "reasoning": "8 hours per week for 3 months (24 hours total) is not enough."})
    assert bad["rating"] == "unknown" and bad["rating_before_check"] == "weak" and "104" in bad["arithmetic_error"]
    ok = fa.post_process(ctx, {"rating": "weak", "evidence_refs": ["phase1_step5_competitors"],
                               "effort_hours_estimate": 300,
                               "reasoning": "About 104 hours total, but the scope needs 300 hours."})
    assert ok["rating"] == "weak"


def test_missing_evidence_is_a_risk_not_a_kill():
    from agents.m2_common import norm_risks
    d = norm_risks({"risks": [], "kill_criteria": [
        {"text": "No willingness to pay", "triggered": True,
         "evidence": "The interview findings show no clear evidence of willingness to pay."},
        {"text": "No willingness to pay", "triggered": True,
         "evidence": "Interviewees said they are not willing to pay for a newsletter."}]})
    assert d["kill_criteria"][0]["triggered"] is False and d["kill_criteria"][0]["triggered_on_absence"]
    assert d["kill_criteria"][1]["triggered"] is True


def test_quote_that_does_not_say_the_claim_is_not_evidence():
    # Real run (SearXNG, strong brief): an on-topic page, but the quote says something else entirely.
    from types import SimpleNamespace
    from agents.m2_common import check_on_topic, unsupported_reason
    logged = []
    ctx = SimpleNamespace(log=SimpleNamespace(action=lambda *a, **k: logged.append(k)))
    card = {"customer": "Freelance graphic designers in Egypt", "problem": "They lose track of client projects and invoices",
            "solution": "A Notion and Google Sheets template pack"}
    data = {"claims": [
        {"claim": "Freelance designers in Egypt need a way to track client projects, invoices sent, and revision rounds.",
         "source_url": "https://www.fiverr.com/categories/graphics-design", "verified": True, "assumption": False,
         "quote": "There is no simple answer to this question as graphic design is not a commodity or a product that "
                  "has an exact way to be measured or priced."},
        {"claim": "Freelancers can use Notion templates to manage client projects, invoices, and time tracking.",
         "source_url": "https://www.notion.com/templates/category/freelance", "verified": True, "assumption": False,
         "quote": "Designed for independent professionals, our collection of Notion freelance templates includes "
                  "project proposals, client management tools, invoice trackers, and time management sheets."}]}
    check_on_topic(ctx, data, card, "opportunity_finder")
    bad, good = data["claims"]
    assert bad["verified"] is False and bad["assumption"] is True and bad["check"].startswith("unsupported")
    assert good["verified"] is True
    assert [k["reason"] for k in logged] == ["quote does not support the claim"]
    # numbers in a claim must be in its quote
    assert "49" in unsupported_reason("49% of graphic designers are freelancers.",
                                      "Most graphic designers work as freelancers today.")
    assert unsupported_reason("Designers earn $72,122 a year as freelancers.",
                              "freelance designers earn $72,122 average annual income") is None
    # a translated claim shares no stems with its Arabic quote: only numbers are checked
    assert unsupported_reason("Freelance designers in Egypt chase unpaid invoices.",
                              "المصممون المستقلون في مصر يطاردون الفواتير غير المدفوعة") is None


def test_critic_issue_about_untriggered_kill_criterion_is_not_must_fix():
    # Real run: the critic called kill criteria with triggered=false 'high-severity risks missing from the report'.
    from types import SimpleNamespace
    from agents.critic_phase1 import CriticPhase1
    arts = {"phase1_step8_skeptic": {"kill_criteria": [
                {"text": "No evidence of willingness to pay for the template pack.", "triggered": True},
                {"text": "Competitors offer similar solutions with better features or lower costs.", "triggered": False}]},
            "phase1_step9_discover_report": {"summary": "s", "findings": [], "confidence": "low"}}
    store = SimpleNamespace(has=lambda s: s in arts, get=lambda s: arts[s], names=lambda: list(arts))
    ctx = SimpleNamespace(store=store, extra={}, mock=False)
    out = CriticPhase1().post_process(ctx, {"verdict": "revise", "issues": [
        {"severity": "must_fix", "text": "The report does not mention the kill criteria that 'Competitors offer "
                                         "similar solutions with better features or lower costs.'"},
        {"severity": "must_fix", "text": "The report omits the triggered kill criterion 'No evidence of willingness "
                                         "to pay for the template pack.'"}]})
    quiet, triggered = out["issues"][:2]
    assert quiet["severity"] == "should_fix" and quiet["downgraded_in_code"] == "kill criterion was not triggered"
    assert triggered["severity"] == "must_fix" and out["verdict"] == "revise"


def test_critic_source_complaint_on_verified_claims_is_not_must_fix():
    from agents.critic_phase1 import cited_claims_verified
    t = ("The finding '49% of graphic designers work as freelancers.' cites claim_id C4, which is verified. "
         "However, the report mentions this claim without providing a source.")
    assert cited_claims_verified(t, {"C4"}) is True
    assert cited_claims_verified(t, {"C2"}) is False  # C4 not verified: stays must_fix
    assert cited_claims_verified("Finding C4 is praise without evidence.", {"C4"}) is False


def test_founder_budget_is_labelled_not_a_price():
    from agents.m2_common import founder_budget
    b = founder_budget("**Budget:** USD 100 total.")
    assert b["amount"] == "100" and "NOT the product price" in b["note"]
    assert founder_budget("no money mentioned") is None


class _FakeLLM:
    model = "fake-real-model"

    def __init__(self, data=None, fail=False):
        self.data, self.fail = data, fail

    def chat(self, system, user, agent, json_mode=True):
        from types import SimpleNamespace
        if self.fail:
            raise TimeoutError("model down")
        return SimpleNamespace(data=self.data, model=self.model, cost=0.0, tokens_in=50, tokens_out=10)


def _support_ctx(llm):
    from types import SimpleNamespace
    logged = []
    return SimpleNamespace(mock=False, llm=llm, log=SimpleNamespace(action=lambda *a, **k: logged.append((a, k)))), logged


def test_support_check_downgrades_only_a_clear_no():
    from agents.m2_common import check_support
    claims = [{"claim": "A", "quote": "a", "verified": True}, {"claim": "B", "quote": "b", "verified": True},
              {"claim": "C", "quote": "c", "verified": True}, {"claim": "D", "quote": "d", "verified": False}]
    ctx, logged = _support_ctx(_FakeLLM({"results": [{"i": 1, "supported": True}, {"i": 2, "supported": False}]}))
    check_support(ctx, {"claims": claims}, "market_scout")
    assert [c["verified"] for c in claims] == [True, False, True, False]  # 3rd: no verdict -> unchanged
    assert claims[1]["assumption"] is True and "support" in claims[1]["check"]
    entry = [k for a, k in logged if a[1] == "claim_support_check"][0]
    assert entry["model"] == "fake-real-model" and entry["checked"] == 3 and entry["downgraded"] == 1


def test_support_check_failure_or_mock_changes_nothing():
    from agents.m2_common import check_support
    claims = [{"claim": "A", "quote": "a", "verified": True}]
    ctx, logged = _support_ctx(_FakeLLM(fail=True))
    check_support(ctx, {"claims": claims}, "market_scout")
    assert claims[0]["verified"] is True and logged[0][0][1] == "claim_support_check_failed"
    ctx, logged = _support_ctx(_FakeLLM({"results": [{"i": 1, "supported": False}]}))
    ctx.mock = True
    check_support(ctx, {"claims": claims}, "market_scout")
    assert claims[0]["verified"] is True and logged == []
