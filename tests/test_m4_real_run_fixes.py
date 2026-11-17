# OWNER: M4
"""Fixes from the first real-model run (qwen3:8b) of Phases 4-6."""
from __future__ import annotations

import gates
from agents import get_agent
from agents.m4_common import UNVERIFIED_PREFIX, supported_recommendations, verify_model_issues
from phases import phase5, phase6
from tests.helpers import make_ctx


def put(ctx, step, data):
    ctx.store.put(step, data, f"# {step}", "test")


# ---------------------------------------------------------------- compliance reviewers: model must_fix needs a real quote

def test_model_must_fix_without_quote_is_downgraded():
    out = verify_model_issues({"issues": [{"severity": "must_fix", "text": "price not labeled"}]}, "some drafts")
    assert out["issues"][0]["severity"] == "should_fix"
    assert out["issues"][0]["text"].startswith(UNVERIFIED_PREFIX)


def test_model_must_fix_on_required_label_is_downgraded():
    drafts = 'checkout: "MOCKED: no real payment" Contact: [FOUNDER TO SET: contact address]'
    for q in ("MOCKED: no real payment", "[FOUNDER TO SET: contact address]"):
        out = verify_model_issues({"issues": [{"severity": "must_fix", "quote": q, "text": "x"}]}, drafts)
        assert out["issues"][0]["severity"] == "should_fix", q


def test_model_must_fix_with_real_quote_holds_the_gate(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase5_step3_launch_posts", {"posts": [
        {"channel": "Reddit", "text": "Loved by designers everywhere, grab it", "status": "approved"}]})
    out = get_agent("compliance_reviewer_phase5").post_process(ctx, {"issues": [
        {"severity": "must_fix", "quote": "Loved by designers everywhere", "text": "implied social proof"},
        {"severity": "must_fix", "quote": "posted", "text": "posts marked posted false without approval"}],
        "verdict": "revise"})
    sev = [i["severity"] for i in out["issues"]]
    assert sev[:2] == ["must_fix", "should_fix"] and out["verdict"] == "revise"


def test_real_run_phase4_false_positives_do_not_hold_gate4(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": None, "comparable_claims": [], "is_assumption": True})
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Terms of Service", "text": "Contact address: [FOUNDER TO SET: contact address].",
         "needs_legal_review": True}]})
    model = {"issues": [
        {"severity": "must_fix", "text": "phase4_step1_pricing: A price is neither verified nor labeled an assumption."},
        {"severity": "must_fix", "quote": "[FOUNDER TO SET: contact address]", "text": "term not set"}],
        "verdict": "revise"}
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, model)
    assert out["verdict"] == "ok" and all(i["severity"] == "should_fix" for i in out["issues"])


# ---------------------------------------------------------------- store page price only from Phase 4

def test_store_page_ignores_model_price_without_phase4_price(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": None, "comparable_claims": [], "is_assumption": True})
    out = get_agent("store_page_builder").post_process(
        ctx, {"title": "Kit", "description": "Tracks client work.", "price_usd": 100, "bullets": ["Arabic"]})
    assert out["price_usd"] is None and out["model_price_ignored"] == 100.0


def test_pricing_budget_is_not_a_price(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.brief = "Idea: template pack.\n**Budget:** USD 100 total."
    out = get_agent("pricing_analyst").post_process(ctx, {"price_usd": 100, "comparable_claims": []})
    # The budget is never the price: the model's 100 is removed; only the founder may then set a (different) price.
    assert out["price_usd"] != 100 and "budget" in out["budget_not_price"]
    assert out["price_usd"] is None or out.get("price_source") == "founder"


# ---------------------------------------------------------------- policies

def test_policy_empty_document_dropped_and_compliance_sentence_replaced(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("policy_drafter").post_process(ctx, {"documents": [
        {"name": "Privacy Policy", "text": "We keep no data. The founder ensures the product complies with all laws. Ask us."},
        {"name": "Policy Document", "text": ""}]})
    assert [d["name"] for d in out["documents"]] == ["Privacy Policy"]
    t = out["documents"][0]["text"]
    assert "complies with" not in t and "needs legal review" in t
    assert t.startswith("We keep no data.") and "Ask us." in t


# ---------------------------------------------------------------- Phase 6: recommendation backed by metrics

def test_supported_recommendations_rule():
    assert supported_recommendations("not met", "FOUNDER-PROVIDED (unverified)") == ["pivot", "stop"]
    assert supported_recommendations("met", "MOCKED") == ["stop", "pivot"]
    assert supported_recommendations("met", "FOUNDER-PROVIDED (unverified)")[0] == "persevere"
    assert supported_recommendations("unknown", "SAMPLE") == ["stop"]


def test_memo_persevere_on_mocked_numbers_is_overridden(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase6_step2_metrics", {"provenance": "MOCKED", "comparison": {"target_status": "met"}})
    out = get_agent("persevere_pivot_memo").post_process(
        ctx, {"recommendation": "persevere", "reasons": ["MOCKED data: 140 sign-ups"], "experiments": ["x"]})
    assert out["recommendation"] == "stop" and out["model_recommendation"] == "persevere" and "overridden" in out


def test_gate6_repeats_when_memo_not_backed(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase6_step2_metrics", {"provenance": "SAMPLE", "comparison": {"target_status": "not met"}})
    put(ctx, "phase6_step3_persevere_pivot_memo", {"recommendation": "persevere"})
    m = phase6.measure(ctx)
    assert m["memo_backed_by_metrics"] == 0
    gates.preregister(ctx, 6, phase6.gate_checks(ctx))
    assert gates.evaluate(ctx, 6, m, attempt=0).outcome == "repeat"


# ---------------------------------------------------------------- sale to cash measured from state

def test_sale_to_cash_flags_and_gate5(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": 19.0, "comparable_claims": [], "is_assumption": True})
    get_agent("sale_to_cash").run(ctx)
    d = ctx.store.get("phase5_step5_sale_to_cash")
    assert d["payment_triggers_delivery"] and d["duplicate_ignored"] and d["refund_revokes_access"]
    assert d["double_deliveries"] == 0 and d["reconcile_balanced"] is True
    assert d["reconcile_summary"]["total_payments_usd"] == 57.0 and "Phase 4 price" in d["order_amounts_basis"]
    assert phase5.measure(ctx)["sale_to_cash_passed"] == 1


def test_gate5_fails_sale_to_cash_when_refund_keeps_access(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase5_step5_sale_to_cash", {"double_deliveries": 0, "reconcile_balanced": True,
                                           "payment_triggers_delivery": True, "duplicate_ignored": True,
                                           "refund_revokes_access": False, "access_after_refund": True})
    assert phase5.measure(ctx)["sale_to_cash_passed"] == 0


# ---------------------------------------------------------------- guardrails: leaks a real model produced

def test_output_guard_blocks_echoed_card_and_password():
    from core.guardrails import check_output
    for t in ("The customer card number 4111 1111 1111 1111 has been saved.",
              "The customer's card number is on file and the secret password is pass123456."):
        assert not check_output(t).allowed, t
    assert check_output("We never ask for passwords or card numbers. The token is revoked after a refund.").allowed


def test_arabic_password_without_colon_is_redacted():
    from core.guardrails import check_input
    t = "رقم بطاقة العميل هو 4111 1111 1111 1111 وكلمة المرور السرية هي pass123456."
    res = check_input(t)
    assert "pass123456" not in res.text and "4111" not in res.text
    assert "كلمة المرور مهمة" in check_input("كلمة المرور مهمة جدا").text


def test_redteam_scoring_counts_guard_catch_and_drafts():
    from evals.run_redteam import evaluate_model_answer
    assert evaluate_model_answer({"expected": "redact"}, "Saved card 4111 1111 1111 1111.")[0] == "caught"
    assert evaluate_model_answer({"expected": "draft_only"}, "Here is a launch post about the kit.")[0] == "drafted"


# ---------------------------------------------------------------- second real run: quotes of keys or placeholders

def test_quote_of_json_key_or_placeholder_is_not_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": None, "comparable_claims": [], "is_assumption": True,
                                      "rationale": "ASSUMPTION: no verified comparable price."})
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Terms of Service", "text": "Licence limits: [FOUNDER TO SET: licence limits].",
         "needs_legal_review": True}]})
    model = {"issues": [
        {"severity": "must_fix", "quote": "is_assumption", "text": "price is labeled as an assumption"},
        {"severity": "must_fix", "quote": "Licence limits: [FOUNDER TO SET: licence limits]", "text": "term not set"}],
        "verdict": "revise"}
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, model)
    assert out["verdict"] == "ok" and [i["severity"] for i in out["issues"]] == ["should_fix", "should_fix"]
    assert out["issues"][1]["quote"].startswith("Licence limits")


def test_quote_of_pipeline_note_is_not_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": None, "comparable_claims": [], "is_assumption": True,
                                      "note": "STUBBED: the model returned no price; the founder must set one."})
    put(ctx, "phase4_step3_policies", {"documents": [{"name": "Terms", "text": "Terms text.", "needs_legal_review": True}]})
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, {"issues": [
        {"severity": "must_fix", "quote": "the model returned no price; the founder must set one", "text": "no price"}],
        "verdict": "revise"})
    assert out["verdict"] == "ok" and out["issues"][0]["severity"] == "should_fix"


def test_pricing_rationale_built_on_budget_is_replaced(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.brief = "**Budget:** USD 100 total."
    out = get_agent("pricing_analyst").post_process(ctx, {
        "price_usd": None, "comparable_claims": [],
        "rationale": "The price of USD 100 is based on the verified claim that designers will pay USD 100."})
    assert "verified claim" not in out["rationale"] and out["rationale"].startswith("ASSUMPTION")


def test_policy_without_name_is_named_from_its_text(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("policy_drafter").post_process(ctx, {"documents": [
        {"text": "Refund requests go to the founder. Refund window: [FOUNDER TO SET: refund window]."}]})
    assert out["documents"][0]["name"] == "Refund Policy"
