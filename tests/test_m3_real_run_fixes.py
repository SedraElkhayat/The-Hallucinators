"""Fixes from the first full real run of Phases 1 to 3 (qwen3:8b on the RTX 5080, Tuesday evening).

What the real run showed, and what these tests pin down:
- The website showed claims as sourced facts although the quote did not support them (the quote was on the page, but
  about something else). A claim is now a fact only when the quote also supports it, otherwise it is ASSUMPTION.
- risk_analyst triggered the kill criterion "sign-ups below 0.2 of the target" with only an artifact name as evidence
  while the demand ratio was 1.4, which stopped Gate 2. The demand rule now covers that wording, and an artifact name
  alone is not evidence.
- critic_phase2 and content_reviewer raised must_fix issues about rules that code had already applied. Those are
  downgraded with the reason recorded; real problems stay must_fix.
Offline: scripted model answers, no network.
"""
import re

import pytest

from agents.m3_common import claim_support, claim_supported_by_quote
from agents.m3_site import check_site, fill_template, sanitize_content
from agents.risk_analyst import evidence_is_named
from phases import phase3
from tests.test_m3_helpers import ScriptedLLM, fixture, get_agent, make_ctx, put

# ---------------------------------------------------------------- claims: the quote must support the claim

REAL_CLAIM_A = ("Freelance graphic designers in Egypt and the MENA region struggle to track client projects, "
                "invoices sent, and revision rounds.")
REAL_QUOTE_A = ("most of my clients couldn't distinguish a good design from a better one! I interviewed my clients, "
                "and 90% of them told me the only way they could identify a de")
REAL_CLAIM_B = ("Freelance graphic designers in Egypt and the MENA region will find the bilingual (Arabic and English) "
                "template pack useful for their local freelancing habits.")
REAL_QUOTE_B = "It would help many freelance designers if I built a project management tool specifically for them!"
REAL_CLAIM_C = "Google Sheet template of SaaS KPIs for founders is free."
REAL_QUOTE_C = "I built a free Google Sheet template of KPIs for SaaS founders."


@pytest.mark.parametrize("claim,quote,expected", [
    (REAL_CLAIM_A, REAL_QUOTE_A, False),
    (REAL_CLAIM_B, REAL_QUOTE_B, False),
    (REAL_CLAIM_C, REAL_QUOTE_C, True),
    ("MOCKED Rival Kit A sells onboarding templates for agencies",
     "MOCKED quote: Rival Kit A offers an onboarding template bundle for design agencies", True),
    ("Free plan", "This tool has a free plan for everyone", True),
    ("The rival template costs 19 USD", "", False),
    ("The rival template costs 19 USD", "The rival template costs 29 USD", True),   # number mismatch is a known limit
    ("", "anything", False),
])
def test_TC_M3_real_claim_support_by_quote(claim, quote, expected):
    assert claim_supported_by_quote(claim, quote) is expected


def test_TC_M3_real_claim_support_scores_are_low_for_unrelated_quotes():
    assert claim_support(REAL_CLAIM_A, REAL_QUOTE_A) < 0.2
    assert claim_support(REAL_CLAIM_C, REAL_QUOTE_C) == 1.0
    assert claim_support("", "") == 0.0


def _content(claims):
    return {"headline": "Client tracker", "value_proposition": "Track revisions in one board.",
            "features": ["Revision board"], "faq": [{"q": "Formats?", "a": "Notion and Sheets."}], "claims": claims}


def _real_claims():
    return [{"claim": REAL_CLAIM_A, "source_url": "https://news.ycombinator.com/item?id=1", "verified": True,
             "quote": REAL_QUOTE_A},
            {"claim": REAL_CLAIM_B, "source_url": "https://news.ycombinator.com/item?id=1", "verified": True,
             "quote": REAL_QUOTE_B},
            {"claim": REAL_CLAIM_C, "source_url": "https://news.ycombinator.com/item?id=2", "verified": True,
             "quote": REAL_QUOTE_C}]


def test_TC_M3_real_unsupported_verified_claims_are_shown_as_assumption():
    content, _ = sanitize_content(_content(_real_claims()))
    shown = {c["claim"][:30]: (c["shown_as"], c["assumption"], c["supported_by_quote"]) for c in content["claims"]}
    assert shown["Freelance graphic designers in"] in (("ASSUMPTION", True, False),)
    assert [c["shown_as"] for c in content["claims"]] == ["ASSUMPTION", "ASSUMPTION", "fact"]
    assert [c["verified"] for c in content["claims"]] == [True, True, True]   # upstream flag is kept, only shown_as changes


def test_TC_M3_real_page_links_only_the_supported_claim_and_passes_the_site_checks():
    content, _ = sanitize_content(_content(_real_claims()))
    page = fill_template(content)
    assert page.count('class="source"') == 1 and "news.ycombinator.com/item?id=2" in page
    assert page.count("ASSUMPTION</span>") >= 2
    assert check_site(page)["passed"] is True


def test_TC_M3_real_verified_claim_without_a_quote_is_an_assumption():
    content, _ = sanitize_content(_content([{"claim": "Rival costs less", "source_url": "https://example.com/a",
                                             "verified": True}]))
    assert content["claims"][0]["shown_as"] == "ASSUMPTION" and content["claims"][0]["supported_by_quote"] is False


# ---------------------------------------------------------------- risk_analyst: false kill criterion

def _risk_run(tmp_path, kill):
    agent = get_agent("risk_analyst")
    resp = fixture("risk_analyst")
    resp["kill_criteria"] = [kill]
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"risk_analyst": resp}), seed=agent.inputs)
    return agent.run(ctx).data["kill_criteria"]


def test_TC_M3_real_demand_kill_criterion_without_the_word_ratio_is_decided_by_code(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Sign-ups below 0.2 of the target set before the test.", "triggered": True,
                                 "evidence": "phase2_step5_demand_results"})
    demand = [k for k in kills if "0.2" in k["text"]]
    assert len(demand) == 1 and demand[0]["triggered"] is False and demand[0]["checked_in_code"] is True


@pytest.mark.parametrize("text", ["Demand falls below 0.2 of the sign-up target", "Waitlist under 0.2 of target",
                                  "The ratio of sign-ups to target is below .2"])
def test_TC_M3_real_demand_rule_wording_variants_are_decided_by_code(tmp_path, text):
    kills = _risk_run(tmp_path, {"text": text, "triggered": True, "evidence": "phase2_step5_demand_results"})
    assert [k["triggered"] for k in kills if "0.2" in k["text"] or ".2" in k["text"]] == [False]


def test_TC_M3_real_artifact_name_alone_is_not_evidence(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Interviewees refuse to pay for templates", "triggered": True,
                                 "evidence": "phase2_step5_demand_results"})
    k = [x for x in kills if "refuse" in x["text"]][0]
    assert k["triggered"] is False and k["triggered_without_evidence"] is True


def test_TC_M3_real_artifact_name_with_what_it_shows_is_evidence():
    stems = ["phase2_step5_demand_results"]
    assert evidence_is_named("phase2_step5_demand_results shows 12 sign-ups against a target of 100", stems, []) is True
    assert evidence_is_named("phase2_step5_demand_results", stems, []) is False
    assert evidence_is_named("phase2_step5_demand_results.", stems, []) is False
    assert evidence_is_named("", stems, []) is False


# ---------------------------------------------------------------- critic_phase2: only code-decided issues are downgraded

REAL_CRITIC_ISSUES = [
    "The demand ratio of 1.4 is MOCKED, not real behavior, but it is presented as real evidence.",
    "The claim about the product differentiating itself with a bilingual template pack is not supported by the "
    "phase2_step1_competitor_analysis artifact.",
    "The assumption about local freelancing habits is presented as a claim without proper evidence or source.",
    "The assumption about users paying USD 100 for the template pack is presented as a claim without proper evidence "
    "or source.",
    "The kill criterion triggered (sign-ups below 0.2 of the target) is presented without proper evidence or source.",
    "The high-severity risk about lack of clear demand signals is not addressed with evidence.",
]


CRITIC_SEEDS = ["phase2_step9_validation_report", "phase2_step5_demand_results", "phase2_step7_risks",
                "phase2_step8_scorecard"]


def _critic(tmp_path, issues, summary="The demand ratio is 1.4 (MOCKED).", limitations=()):
    agent = get_agent("critic_phase2")
    resp = {"issues": [{"severity": "must_fix", "text": t} for t in issues], "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}), seed=CRITIC_SEEDS)
    report = ctx.store.get("phase2_step9_validation_report")
    report["summary"] = summary
    report["limitations"] = limitations
    put(ctx, "phase2_step9_validation_report", report)
    return agent.run(ctx).data


def test_TC_M3_real_critic_downgrades_only_what_code_has_decided(tmp_path):
    data = _critic(tmp_path, REAL_CRITIC_ISSUES)
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    mocked, differentiation, habits, paying, kill, risk = REAL_CRITIC_ISSUES
    assert sev[mocked] == "should_fix"
    assert sev[habits] == "should_fix"
    assert sev[paying] == "should_fix"
    assert sev[differentiation] == "must_fix"      # a real unsupported statement: stays
    assert sev[kill] == "must_fix"                 # a wrongly triggered kill criterion: stays
    assert sev[risk] == "must_fix"
    assert data["verdict"] == "revise"
    assert all(i.get("downgraded_by_code") for i in data["issues"] if i["severity"] == "should_fix")


def test_TC_M3_real_critic_keeps_mocked_issue_when_the_report_does_not_state_provenance(tmp_path):
    data = _critic(tmp_path, REAL_CRITIC_ISSUES[:1], summary="Demand looks strong.", limitations=["Interviews are SAMPLE."])
    assert data["issues"][0]["severity"] == "must_fix" and data["verdict"] == "revise"


def test_TC_M3_real_critic_does_not_downgrade_when_demand_is_real(tmp_path):
    agent = get_agent("critic_phase2")
    resp = {"issues": [{"severity": "must_fix", "text": REAL_CRITIC_ISSUES[0]}], "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}), seed=CRITIC_SEEDS)
    results = ctx.store.get("phase2_step5_demand_results")
    results["provenance"] = "REAL"
    put(ctx, "phase2_step5_demand_results", results)
    data = agent.run(ctx).data
    assert data["issues"][0]["severity"] == "must_fix" and data["verdict"] == "revise"


# ---------------------------------------------------------------- content_reviewer: rules checked on the page

def _phase3_without_review(tmp_path, issues):
    seeds = ["phase2_step2_lean_canvas", "phase2_step9_validation_report", "phase2_step3_demand_test_plan",
             "phase1_step4_idea_card", "phase1_step2_clarification", "phase2_step4_landing_page"]
    resp = {"issues": issues, "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"content_reviewer": resp}), seed=seeds)
    for stage in phase3.STAGES:
        for name in stage:
            if name != "content_reviewer":
                get_agent(name).run(ctx)
    return ctx


def _manifest_claim(ctx):
    return ctx.store.get("phase3_step3_build")["claims"][0]["claim"]


def _review_issues(ctx):
    data = get_agent("content_reviewer").run(ctx).data
    return data


def test_TC_M3_real_reviewer_downgrades_issues_about_rules_the_page_checks_pass(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    claim = _manifest_claim(ctx)
    issues = [
        {"severity": "must_fix", "text": f"The claim '{claim}' is presented as a fact without a source link or labeled "
                                         "as an assumption.", "file": "index.html"},
        {"severity": "must_fix", "text": "The page has a 'Demo only: nothing is sent or stored' sign-up box, but it "
                                         "is not clearly labeled as a demo in the text.", "file": "index.html"},
        {"severity": "must_fix", "text": "The call-to-action ('Join the waitlist') may imply urgency or scarcity.",
         "file": "index.html"},
        {"severity": "must_fix", "text": "The page shows invented testimonials from customers as real praise.",
         "file": "index.html"},
    ]
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": issues, "verdict": "revise"}})
    data = _review_issues(ctx)
    sev = [i["severity"] for i in data["issues"]]
    assert sev == ["should_fix", "should_fix", "should_fix", "must_fix"]
    assert data["verdict"] == "revise"
    assert all(i.get("downgraded_by_code") for i in data["issues"][:3])


def test_TC_M3_real_reviewer_keeps_the_label_issue_when_a_claim_really_has_no_label(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    claim = _manifest_claim(ctx)
    path = tmp_path / "outputs" / "phase3_step3_site" / "index.html"
    html = path.read_text(encoding="utf-8")
    html = re.sub(r'<span class="label">ASSUMPTION</span>', "", html)           # remove every ASSUMPTION label
    html = re.sub(r'\s*<a class="source"[^>]*>source</a>', "", html)              # and every source link
    path.write_text(html, encoding="utf-8")
    issue = {"severity": "must_fix", "text": f"The claim '{claim}' is presented as a fact without a source link or "
                                             "labeled as an assumption.", "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    data = _review_issues(ctx)
    assert data["issues"][0]["severity"] == "must_fix" and data["verdict"] == "revise"


def test_TC_M3_real_reviewer_keeps_urgency_issue_when_the_page_has_urgency(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    path = tmp_path / "outputs" / "phase3_step3_site" / "index.html"
    path.write_text(path.read_text(encoding="utf-8").replace("Join the waitlist", "Only 5 spots left"), encoding="utf-8")
    issue = {"severity": "must_fix", "text": "The call-to-action implies urgency or scarcity.", "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    assert _review_issues(ctx)["issues"][0]["severity"] == "must_fix"


# ---------------------------------------------------------------- absence of evidence is not a kill (second real run)

@pytest.mark.parametrize("evidence", [
    "phase2_step5_demand_results: there is no clear evidence of willingness to pay",
    "phase2_step3_demand_test_plan: insufficient evidence about pricing so far",
    "Founders might not pay, according to phase2_step2_lean_canvas",
    "There is a lack of data in phase2_step5_demand_results about paying visitors",
])
def test_TC_M3_real_missing_or_hedged_evidence_does_not_trigger_a_kill(tmp_path, evidence):
    kills = _risk_run(tmp_path, {"text": "No evidence of willingness to pay for the template pack", "triggered": True,
                                 "evidence": evidence})
    k = [x for x in kills if "willingness" in x["text"]][0]
    assert k["triggered"] is False and k.get("triggered_on_missing_evidence") is True


def test_TC_M3_real_evidence_that_names_no_input_never_triggers_a_kill(tmp_path):
    kills = _risk_run(tmp_path, {"text": "No evidence of willingness to pay", "triggered": True,
                                 "evidence": "The interview findings show that there is no clear evidence."})
    k = [x for x in kills if "willingness" in x["text"]][0]
    assert k["triggered"] is False and (k.get("triggered_without_evidence") or k.get("triggered_on_missing_evidence"))


def test_TC_M3_real_explicit_negative_evidence_still_triggers_a_kill(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Interviewees refuse to pay for the template pack", "triggered": True,
                                 "evidence": "phase2_step5_demand_results shows 3 of 10 interviewees said they "
                                             "would not pay any price"})
    k = [x for x in kills if "refuse" in x["text"]][0]
    assert k["triggered"] is True and not k.get("triggered_on_missing_evidence")


def test_TC_M3_real_critic_downgrades_assumption_without_supporting_evidence_but_not_a_real_gap(tmp_path):
    budget = ("The report mentions the founder's budget of USD 100 is sufficient, but this is an assumption "
              "without supporting evidence.")
    gap = "The report states a competitor price that appears in no input artifact."
    data = _critic(tmp_path, [budget, gap])
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    assert sev[budget] == "should_fix" and sev[gap] == "must_fix"


def test_TC_M3_real_reviewer_downgrades_without_verification_when_the_claim_is_linked_or_labeled(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    claim = _manifest_claim(ctx)
    issue = {"severity": "must_fix", "text": f"The claim '{claim}' is presented as a fact without proper verification.",
             "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    data = _review_issues(ctx)
    assert data["issues"][0]["severity"] == "should_fix" and data["verdict"] == "ok"


# ---------------------------------------------------------------- third real run: absence criteria and citation complaints

@pytest.mark.parametrize("text", ["No evidence of willingness to pay for the bilingual template pack.",
                                  "Lack of evidence that designers would pay", "Insufficient data on pricing"])
def test_TC_M3_real_a_criterion_that_describes_absence_never_triggers(tmp_path, text):
    kills = _risk_run(tmp_path, {"text": text, "triggered": True,
                                 "evidence": "phase2_step5_demand_results shows 12 sign-ups against a target of 100"})
    k = kills[0]
    assert k["triggered"] is False and k["triggered_on_missing_evidence"] is True


def test_TC_M3_real_a_positive_criterion_with_real_evidence_still_triggers(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Most interviewees refuse to pay", "triggered": True,
                                 "evidence": "phase2_step5_demand_results shows 12 sign-ups against a target of 100"})
    assert kills[0]["triggered"] is True


def test_TC_M3_real_critic_downgrades_not_provided_when_the_artifact_exists(tmp_path):
    issue = ("The report mentions a high-severity risk, but this is cited to phase2_step7_risks, which is not "
             "fully provided.")
    other = "The report invents a price that appears in phase2_step9_nowhere_artifact, which is not provided."
    data = _critic(tmp_path, [issue, other])
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    assert sev[issue] == "should_fix"      # phase2_step7_risks exists in the run
    assert sev[other] == "must_fix"        # an artifact that does not exist: the complaint stands


def test_TC_M3_real_critic_downgrades_does_not_cite_only_when_the_report_cites_it(tmp_path):
    agent = get_agent("critic_phase2")
    cited_issue = "The report claims MOCKED results but does not cite phase2_step5_demand_results."
    uncited_issue = "The report claims a kill criterion but does not cite phase2_step7_risks."
    resp = {"issues": [{"severity": "must_fix", "text": cited_issue}, {"severity": "must_fix", "text": uncited_issue}],
            "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}), seed=CRITIC_SEEDS)
    report = ctx.store.get("phase2_step9_validation_report")
    report["summary"] = "Demand ratio 1.4 (MOCKED), see phase2_step5_demand_results."
    report["findings"] = [{"text": "x", "claim_ids": ["phase2_step5_demand_results"]}]
    put(ctx, "phase2_step9_validation_report", report)
    data = agent.run(ctx).data
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    assert sev[cited_issue] == "should_fix" and sev[uncited_issue] == "must_fix"


# ---------------------------------------------------------------- fourth real run: scorecard and high-risk complaints

REAL_SCORECARD_RISK_ISSUES = [
    "The scorecard rates monetization as unknown due to lack of evidence, but no source is cited.",
    "The scorecard rates problem severity as adequate, but no evidence is provided to support this.",
    "The scorecard rates feasibility as adequate, but no evidence is provided to support this.",
    "The risk of no evidence of willingness to pay for the template pack is high, but no source is cited.",
    "Risk (high): The founder assumes designers will pay USD 100, but there is no evidence of willingness to pay.",
]


def test_TC_M3_real_critic_downgrades_scorecard_and_high_risk_complaints_that_code_decides(tmp_path):
    data = _critic(tmp_path, REAL_SCORECARD_RISK_ISSUES)
    assert [i["severity"] for i in data["issues"]] == ["should_fix"] * 5
    assert data["verdict"] == "ok" and data.get("verdict_changed_by_code")
    assert all(i.get("downgraded_by_code") for i in data["issues"])


def test_TC_M3_real_critic_keeps_real_problems_next_to_the_downgraded_ones(tmp_path):
    real = [
        "The report states a competitor price that appears in no input artifact.",
        "The report promises that the founder will earn a monthly income.",
        "The risk section invents a competitor named Acme and gives no source.",
    ]
    data = _critic(tmp_path, REAL_SCORECARD_RISK_ISSUES[:2] + real)
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    assert [sev[t] for t in real] == ["must_fix"] * 3
    assert data["verdict"] == "revise"


# ---------------------------------------------------------------- fifth real run: completeness of high risks, label wording

def test_TC_M3_real_critic_downgrades_missing_high_risk_only_when_the_report_has_every_high_risk(tmp_path):
    issue = "The report fails to mention the high-severity risk of lack of clear evidence of willingness to pay."
    agent = get_agent("critic_phase2")
    resp = {"issues": [{"severity": "must_fix", "text": issue}], "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}), seed=CRITIC_SEEDS)
    risks = ctx.store.get("phase2_step7_risks")
    risks["risks"] = [{"text": "Customers may not pay for a template pack at all", "severity": "high"}]
    put(ctx, "phase2_step7_risks", risks)
    report = ctx.store.get("phase2_step9_validation_report")
    report["findings"] = [{"text": "Risk (high): Customers may not pay for a template pack at all",
                           "claim_ids": ["phase2_step7_risks"]}]
    put(ctx, "phase2_step9_validation_report", report)
    assert agent.run(ctx).data["issues"][0]["severity"] == "should_fix"

    ctx2 = make_ctx(tmp_path / "second", llm=ScriptedLLM({"critic_phase2": resp}), seed=CRITIC_SEEDS)
    put(ctx2, "phase2_step7_risks", risks)
    report2 = ctx2.store.get("phase2_step9_validation_report")
    report2["findings"] = [{"text": "Something else entirely", "assumption": True}]
    put(ctx2, "phase2_step9_validation_report", report2)
    assert agent.run(ctx2).data["issues"][0]["severity"] == "must_fix"       # the high risk really is missing


@pytest.mark.parametrize("text", [
    "The founder's skills are sufficient, but this is an assumption without a cited artifact.",
    "The tool is based on free templates, but this is an assumption without a source.",
])
def test_TC_M3_real_critic_label_rule_wording_without_a_cited_artifact(tmp_path, text):
    assert _critic(tmp_path, [text])["issues"][0]["severity"] == "should_fix"


def test_TC_M3_real_critic_does_not_downgrade_an_unsupported_statement_that_is_not_an_assumption(tmp_path):
    text = "The report states the market is worth USD 2 billion without a cited artifact."
    assert _critic(tmp_path, [text])["issues"][0]["severity"] == "must_fix"


def test_TC_M3_real_critic_skills_is_not_a_kill_criterion(tmp_path):
    text = "The founder's skills are sufficient, but this is an assumption without a cited artifact."
    assert _critic(tmp_path, [text])["issues"][0]["severity"] == "should_fix"


@pytest.mark.parametrize("text", [
    "The report presents assumptions as if they are supported by evidence, which is misleading.",
    "The report lacks clear evidence for key assumptions, such as willingness to pay.",
])
def test_TC_M3_real_critic_label_rule_more_wordings(tmp_path, text):
    assert _critic(tmp_path, [text])["issues"][0]["severity"] == "should_fix"


def test_TC_M3_real_critic_keeps_a_kill_criterion_assumption_issue(tmp_path):
    text = "The kill criterion is triggered, but this is an assumption without a cited artifact."
    assert _critic(tmp_path, [text])["issues"][0]["severity"] == "must_fix"


def test_TC_M3_real_reviewer_downgrades_without_proper_context_or_source_when_the_claim_is_linked(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    claim = _manifest_claim(ctx)
    issue = {"severity": "must_fix", "text": f"The claim '{claim}' is presented as a fact without proper context or "
                                             "source, even though it is labeled as a fact.", "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    assert _review_issues(ctx)["issues"][0]["severity"] == "should_fix"


# ---------------------------------------------------------------- full six-phase real run: price slot, "verified as false"

def test_TC_M3_real_reviewer_downgrades_a_price_complaint_when_the_amount_is_not_on_the_page(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    issue = {"severity": "must_fix", "text": "The 'Price section' mentions a USD 100 one-time purchase, which is a promise "
                                             "of a price without any evidence or source.", "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    data = _review_issues(ctx)
    assert data["issues"][0]["severity"] == "should_fix" and data["verdict"] == "ok"


def test_TC_M3_real_reviewer_keeps_a_price_complaint_when_the_amount_is_really_on_the_page(tmp_path):
    ctx = _phase3_without_review(tmp_path, [])
    path = tmp_path / "outputs" / "phase3_step3_site" / "index.html"
    path.write_text(path.read_text(encoding="utf-8").replace("Join the waitlist", "Buy now for USD 100"),
                    encoding="utf-8")
    issue = {"severity": "must_fix", "text": "The page promises a USD 100 price without any evidence.", "file": "index.html"}
    ctx.llm = ScriptedLLM({"content_reviewer": {"issues": [issue], "verdict": "revise"}})
    assert _review_issues(ctx)["issues"][0]["severity"] == "must_fix"


def test_TC_M3_real_critic_downgrades_verified_as_false_without_source_but_not_other_missing_sources(tmp_path):
    flagged = ("The market claim that designers will pay USD 100 is verified as false, but no source is provided for "
               "this claim.")
    other = "The report states a competitor price without a source."
    data = _critic(tmp_path, [flagged, other])
    sev = {i["text"]: i["severity"] for i in data["issues"]}
    assert sev[flagged] == "should_fix" and sev[other] == "must_fix"


def test_TC_M3_real_no_clear_indication_is_absence_of_evidence_not_a_kill(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Interviewees show no willingness to pay for the solution.", "triggered": True,
                                 "evidence": "phase2_step5_demand_results: no clear indication of willingness to pay"})
    assert kills[0]["triggered"] is False and kills[0]["triggered_on_missing_evidence"] is True


def test_TC_M3_real_explicit_refusal_still_triggers_after_the_wording_change(tmp_path):
    kills = _risk_run(tmp_path, {"text": "Two of three interviewees say they will not pay", "triggered": True,
                                 "evidence": "phase2_step5_demand_results: interviewees B and C said they would "
                                             "never pay for a template"})
    assert kills[0]["triggered"] is True
