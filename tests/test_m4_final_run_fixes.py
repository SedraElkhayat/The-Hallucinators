# OWNER: M4
"""Fixes from the final real run: a price sourced on quotes with no amount, and legal-review-only must_fix."""
from __future__ import annotations

from agents import get_agent
from agents.pricing_analyst import quote_has_price
from tests.helpers import make_ctx


def put(ctx, step, data):
    ctx.store.put(step, data, "# test", "test")


def claim(n, quote):
    return {"claim": f"MOCKED: comparable {n}", "source_url": f"https://example.com/mock/final{n}",
            "quote": quote, "verified": True, "assumption": False}


NO_PRICE = [claim(1, "MOCKED quote: Freelance templates are designed for independent professionals"),
            claim(2, "MOCKED quote: customizable freelancer templates in Google Sheets")]


def test_quote_price_detection():
    for q in ("$19 one-time", "USD 12", "300 EGP", "EGP 300", "19.99"):
        assert quote_has_price(q), q
    for q in (NO_PRICE[0]["quote"], NO_PRICE[1]["quote"], "since 2024, 50 templates", ""):
        assert not quote_has_price(q), q


def test_verified_claims_without_amounts_make_the_price_an_assumption(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase1_step5_competitors", {"claims": NO_PRICE})
    out = get_agent("pricing_analyst").post_process(ctx, {
        "price_usd": 25, "range": [20, 30], "is_assumption": False, "rationale": "Based on comparables.",
        "comparable_claims": [dict(c, verified=None) for c in NO_PRICE]})
    assert len(out["comparable_claims"]) == 2  # still verified, but they name no price
    assert out["is_assumption"] is True
    assert out["rationale"].startswith("ASSUMPTION") and out["price_label"].startswith("ASSUMPTION")


def test_verified_quote_with_price_may_source_the_price(tmp_path):
    ctx = make_ctx(tmp_path)
    priced = claim(3, "MOCKED quote: the bundle is $19 one-time")
    put(ctx, "phase1_step5_competitors", {"claims": NO_PRICE + [priced]})
    out = get_agent("pricing_analyst").post_process(ctx, {
        "price_usd": 19, "range": [15, 25], "is_assumption": False,
        "comparable_claims": [dict(c, verified=None) for c in NO_PRICE + [priced]]})
    assert out["is_assumption"] is False and "price_label" not in out


def _policies(ctx, flag=True):
    put(ctx, "phase4_step1_pricing", {"price_usd": 25, "comparable_claims": [], "is_assumption": True})
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Privacy Policy", "text": "Privacy Policy. Contact: [FOUNDER TO SET: contact address].",
         "needs_legal_review": flag},
        {"name": "Terms of Service", "text": "Terms of Service. Refunds: [FOUNDER TO SET: refund window].",
         "needs_legal_review": True}]})


LEGAL_ONLY = [{"severity": "must_fix", "quote": "Privacy Policy", "text": "Privacy Policy document needs legal review"},
              {"severity": "must_fix", "quote": "Terms of Service", "text": "Terms of Service document needs legal review"}]


def test_legal_review_only_must_fix_is_downgraded_when_flagged(tmp_path):
    ctx = make_ctx(tmp_path)
    _policies(ctx)
    out = get_agent("compliance_reviewer_phase4").post_process(
        ctx, {"issues": [dict(i) for i in LEGAL_ONLY], "verdict": "revise"})
    assert out["verdict"] == "ok"
    assert all(i["severity"] == "should_fix" for i in out["issues"])
    assert all("needs_legal_review: true" in i["text"] for i in out["issues"])
    assert len(out["downgraded"]) == 2


def test_legal_review_must_fix_kept_when_document_not_flagged(tmp_path):
    ctx = make_ctx(tmp_path)
    _policies(ctx, flag=False)
    out = get_agent("compliance_reviewer_phase4").post_process(
        ctx, {"issues": [dict(LEGAL_ONLY[0])], "verdict": "revise"})
    assert out["verdict"] == "revise"
    assert any(i["severity"] == "must_fix" and "needs legal review" in i["text"] for i in out["issues"])


def test_real_legal_problem_stays_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    _policies(ctx)
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, {"issues": [
        {"severity": "must_fix", "quote": "Privacy Policy",
         "text": "Privacy Policy claims GDPR compliance; needs legal review"}], "verdict": "revise"})
    assert out["verdict"] == "revise" and out["issues"][0]["severity"] == "must_fix"


def test_founder_to_set_placeholder_stays_should_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    _policies(ctx)
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, {"issues": [
        {"severity": "should_fix", "quote": "[FOUNDER TO SET: refund window]", "text": "founder must set refund window"}],
        "verdict": "ok"})
    assert out["verdict"] == "ok" and out["issues"][0]["severity"] == "should_fix"
