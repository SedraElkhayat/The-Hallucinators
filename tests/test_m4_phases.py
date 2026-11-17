# OWNER: M4
"""Unit tests for Phase 4, Phase 5, and Phase 6 gates and measurement.

Verifies:
1. measure() on hand-built artifacts for Phase 4, 5, 6.
2. Gate 4, 5, 6 outcomes via gates.evaluate().
3. An unapproved release stops Gate 5.
4. Store page HTML has no script, timer, or counter.
"""
from __future__ import annotations

import re

import gates
from phases import phase4, phase5, phase6
from tests.helpers import make_ctx


def test_phase4_measure_and_gate_go(tmp_path):
    ctx = make_ctx(tmp_path)

    # Hand-built clean artifacts for Phase 4
    ctx.store.put("phase4_step1_pricing", {
        "price_usd": 29.0,
        "range": [19.0, 39.0],
        "comparable_claims": [{"claim": "mock comparable"}],
        "is_assumption": False,
    }, "# Pricing", "pricing_analyst")

    ctx.store.put("phase4_step2_offer", {
        "tiers": [{"name": "Standard", "price_usd": 29.0, "includes": ["Dashboard"]}],
        "positioning": "Productivity toolkit for freelancers.",
    }, "# Offer", "offer_packager")

    ctx.store.put("phase4_step3_policies", {
        "documents": [
            {"name": "Terms of Service", "text": "Terms here", "needs_legal_review": True},
            {"name": "Privacy Policy", "text": "Privacy here", "needs_legal_review": True},
            {"name": "Refund Policy", "text": "Refunds here", "needs_legal_review": True},
        ]
    }, "# Policies", "policy_drafter")

    metrics = phase4.measure(ctx)
    assert metrics["price_sourced_or_labeled"] == 1
    assert metrics["policies_labeled"] == 1
    assert metrics["banned_claims"] == 0
    assert metrics["payment_code_present"] == 0

    gates.preregister(ctx, 4, phase4.gate_checks(ctx))
    res = gates.evaluate(ctx, 4, metrics, attempt=0)
    assert res.outcome == "go"


def test_phase4_gate_repeat_on_banned_claim(tmp_path):
    ctx = make_ctx(tmp_path)

    # Valid pricing so price check passes
    ctx.store.put("phase4_step1_pricing", {
        "price_usd": 29.0,
        "is_assumption": True,
    }, "# Pricing", "pricing_analyst")

    # Valid policies so policies check passes
    ctx.store.put("phase4_step3_policies", {
        "documents": [{"name": "Terms", "text": "Terms", "needs_legal_review": True}]
    }, "# Policies", "policy_drafter")

    # Offer with banned income promise
    ctx.store.put("phase4_step2_offer", {
        "tiers": [],
        "positioning": "Guaranteed 100% passive income for all buyers.",
    }, "# Offer", "offer_packager")

    metrics = phase4.measure(ctx)
    assert metrics["banned_claims"] > 0

    gates.preregister(ctx, 4, phase4.gate_checks(ctx))
    res = gates.evaluate(ctx, 4, metrics, attempt=0)
    assert res.outcome == "repeat"


def test_phase5_store_page_html_clean(tmp_path):
    ctx = make_ctx(tmp_path)
    from agents import get_agent
    spb = get_agent("store_page_builder")
    spb.run(ctx)

    html_path = ctx.out_dir / "phase5_step2_store_page.html"
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    assert "<script" not in content.lower()
    assert not re.search(r"\b(?:countdown|timer|only \d+ left)\b", content, re.I)
    assert "MOCKED checkout: no real payment" in content


def test_phase5_unapproved_release_stops_gate(tmp_path):
    ctx = make_ctx(tmp_path)

    # Unapproved launch post marked posted
    ctx.store.put("phase5_step3_launch_posts", {
        "posts": [{"channel": "Twitter", "text": "Live post", "posted": True}]
    }, "# Posts", "launch_post_drafter")

    metrics = phase5.measure(ctx)
    assert metrics["unapproved_released"] > 0

    gates.preregister(ctx, 5, phase5.gate_checks(ctx))
    res = gates.evaluate(ctx, 5, metrics, attempt=0)
    assert res.outcome == "stop"


def test_phase5_gate_go(tmp_path):
    ctx = make_ctx(tmp_path)

    # Clean approved artifacts and passing sale-to-cash
    ctx.store.put("phase5_step2_store_page", {"released": False}, "# Store Page", "store_page_builder")
    ctx.store.put("phase5_step3_launch_posts", {
        "posts": [{"channel": "LinkedIn", "posted": False}]
    }, "# Posts", "launch_post_drafter")
    ctx.store.put("phase5_step5_sale_to_cash", {
        "double_deliveries": 0,
        "reconcile_balanced": True,
    }, "# Sale to Cash", "sale_to_cash")

    metrics = phase5.measure(ctx)
    assert metrics["unapproved_released"] == 0
    assert metrics["sale_to_cash_passed"] == 1
    assert metrics["double_deliveries"] == 0
    assert metrics["reconcile_balanced"] == 1

    gates.preregister(ctx, 5, phase5.gate_checks(ctx))
    res = gates.evaluate(ctx, 5, metrics, attempt=0)
    assert res.outcome == "go"


def test_phase6_measure_and_gate_go(tmp_path):
    ctx = make_ctx(tmp_path)

    ctx.store.put("phase6_step2_metrics", {
        "comparison": {"target": 100, "actual": 140, "target_status": "met"},
        "provenance": "FOUNDER-PROVIDED (unverified)",
        "gaps": [],
    }, "# Metrics", "metrics_analyst")

    ctx.store.put("phase6_step3_persevere_pivot_memo", {
        "recommendation": "persevere",
        "reasons": ["Target exceeded"],
        "experiments": ["New landing variation"],
    }, "# Memo", "persevere_pivot_memo")

    metrics = phase6.measure(ctx)
    assert metrics["inputs_labeled"] == 1
    assert metrics["memo_written"] == 1

    gates.preregister(ctx, 6, phase6.gate_checks(ctx))
    res = gates.evaluate(ctx, 6, metrics, attempt=0)
    assert res.outcome == "go"
