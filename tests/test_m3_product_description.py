"""The content reviewer must not ask for a source on the product's own description (final real run, Gate 3).

In the final real run on qwen3:8b, Gate 3 stopped on six must_fix issues that all said a statement about the product
itself lacks a source link or an ASSUMPTION label ("the product does not collect client data", "is bilingual", "is a
digital template pack for freelance graphic designers in Egypt"). Those statements are the founder's design (spec, idea
card, stated values), not market claims. Real market claims, numbers, prices, reviews and promises stay must_fix.
Offline: scripted model answers, no network.
"""
import pytest

from agents.content_reviewer import describes_the_product_itself, founder_design_text
from tests.test_m3_helpers import ScriptedLLM, get_agent, make_ctx, put

COMPLAINT = "lacks a source link or an 'ASSUMPTION' label."

PRODUCT_ISSUES = [
    f"The claim about the product not collecting client data {COMPLAINT}",
    f"The claim about the product not including payment processing, user accounts, or subscription models {COMPLAINT}",
    f"The claim about the product being bilingual (Arabic and English) {COMPLAINT}",
    f"The claim about the product being a digital template pack for freelance graphic designers in Egypt {COMPLAINT}",
    f"The claim about the product being a digital template pack for freelance graphic designers in the MENA region {COMPLAINT}",
    f"The claim about the product being a digital template pack for freelance graphic designers who work with several "
    f"clients at once {COMPLAINT}",
]


def _ctx(tmp_path, issues, spec=True, card=True, values=True):
    agent = get_agent("content_reviewer")
    resp = {"issues": [{"severity": "must_fix", "text": t, "file": "index.html"} for t in issues], "verdict": "revise"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"content_reviewer": resp}), seed=agent.inputs)
    if spec:
        put(ctx, "phase3_step1_spec", {
            "mvp_scope": ["One-page website for a bilingual (Arabic and English) digital template pack for freelance "
                          "graphic designers in Egypt and the MENA region who work with several clients at once"],
            "out_of_scope": ["Payment processing, user accounts and subscription models"],
            "user_stories": ["As a freelance designer I want a template so that I track client projects"],
            "acceptance_tests": []})
    if card:
        put(ctx, "phase1_step4_idea_card", {"customer": "Freelance graphic designers in Egypt and the MENA region",
                                            "problem": "They lose track of invoices",
                                            "solution": "A digital template pack in Notion and Google Sheets",
                                            "value_proposition": "Bilingual Arabic and English, no subscription"})
    if values:
        put(ctx, "phase1_step2_clarification", {"answers": {
            "clarify_values_and_limits": "No lock-in subscriptions; never collects client data",
            "clarify_differentiation": "Bilingual Arabic and English, built for local freelancing habits",
            "clarify_budget": "100"}})
    return agent, ctx


def _severities(data):
    return [i["severity"] for i in data["issues"]]


def test_TC_M3_final_run_product_description_issues_become_should_fix(tmp_path):
    agent, ctx = _ctx(tmp_path, PRODUCT_ISSUES)
    data = agent.run(ctx).data
    assert _severities(data) == ["should_fix"] * 6
    assert all("product's own description" in i["downgraded_by_code"] for i in data["issues"])
    assert data["verdict"] == "ok" and data.get("verdict_changed_by_code")


@pytest.mark.parametrize("issue", [
    "The claim that 80% of designers lose invoices is presented as a fact without a source link.",
    f"The claim that designers prefer Notion over Trello {COMPLAINT}",
    f"The claim about the product having 500 happy customers {COMPLAINT}",
    f"The claim about the product earning designers a monthly income {COMPLAINT}",
    f"The claim about the product being 100% free forever {COMPLAINT}",
    f"The claim about competitors of the product charging more {COMPLAINT}",
    f"The product page shows invented testimonials from customers. {COMPLAINT}",
])
def test_TC_M3_final_run_real_market_claims_numbers_and_fake_proof_stay_must_fix(tmp_path, issue):
    agent, ctx = _ctx(tmp_path, [issue])
    data = agent.run(ctx).data
    assert _severities(data) == ["must_fix"] and data["verdict"] == "revise"
    assert not data["issues"][0].get("downgraded_by_code")


def test_TC_M3_final_run_product_issue_stays_must_fix_when_it_matches_nothing_the_founder_defined(tmp_path):
    issue = f"The claim about the product supporting voice assistants {COMPLAINT}"
    agent, ctx = _ctx(tmp_path, [issue])
    assert _severities(agent.run(ctx).data) == ["must_fix"]


def test_TC_M3_final_run_without_spec_idea_card_or_values_nothing_is_downgraded(tmp_path):
    agent, ctx = _ctx(tmp_path, PRODUCT_ISSUES[:2], spec=False, card=False, values=False)
    assert _severities(agent.run(ctx).data) == ["must_fix"] * 2


def test_TC_M3_final_run_the_design_text_uses_spec_idea_card_and_values_but_not_the_problem_or_budget(tmp_path):
    _, ctx = _ctx(tmp_path, [])
    design = founder_design_text(ctx).lower()
    assert "bilingual" in design and "never collects client data" in design and "digital template pack" in design
    assert "lose track of invoices" not in design and "100" not in design


@pytest.mark.parametrize("issue,expected", [
    (PRODUCT_ISSUES[0].lower(), True),
    ("the claim about the product being a digital template pack lacks a source link.", True),
    ("the product claim lacks a source link.", False),                      # no shared words with the design
    ("the claim about the product being bilingual (arabic and english) is presented as a fact.", True),
    ("the claim about the product being bilingual is presented as a fact.", False),   # one shared word only
    ("the product is bilingual.", False),                                     # no complaint at all
])
def test_TC_M3_final_run_describes_the_product_itself_unit(issue, expected):
    design = ("one-page website for a bilingual arabic and english digital template pack for freelance graphic designers. "
              "no lock-in subscriptions; never collects client data")
    assert describes_the_product_itself(issue, design) is expected
