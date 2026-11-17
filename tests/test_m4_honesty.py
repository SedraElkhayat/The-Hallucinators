# OWNER: M4
"""Honesty rules in M4 agents: no invented numbers, untrusted customer text, code fallbacks labeled."""
from __future__ import annotations

from agents import get_agent
from agents.metrics_analyst import compute_comparison, parse_results_csv
from tests.helpers import make_ctx

CSV = "metric,value,provenance\nwaitlist_signups,140,MOCKED\nmock_sales,9,MOCKED\n"


def _put(ctx, step, data):
    ctx.store.put(step, data, "# test", "test")


def test_metrics_comparison_computed_in_code(tmp_path):
    ctx = make_ctx(tmp_path)
    _put(ctx, "phase2_step3_demand_test_plan", {"target": 100})
    c = compute_comparison(ctx, CSV)
    assert c["actual_signups"] == 140.0
    assert c["phase2_target_signups"] == 100.0
    assert c["target_status"] == "met"
    assert c["provenance"] == "MOCKED"


def test_metrics_not_met_and_missing(tmp_path):
    ctx = make_ctx(tmp_path)
    _put(ctx, "phase2_step3_demand_test_plan", {"target": 200})
    assert compute_comparison(ctx, CSV)["target_status"] == "not met"
    empty = compute_comparison(ctx, "")
    assert empty["results"] == {} and empty["target_status"] == "unknown"
    assert empty["provenance"] == "none provided"


def test_metrics_model_numbers_overridden(tmp_path):
    ctx = make_ctx(tmp_path)
    agent = get_agent("metrics_analyst")
    agent._computed = compute_comparison(ctx, CSV)
    out = agent.post_process(ctx, {"comparison": {"actual_signups": 9999}, "provenance": "REAL", "gaps": []})
    assert out["comparison"]["actual_signups"] == 140.0
    assert out["provenance"] == "MOCKED"


def test_parse_csv_ignores_blank_rows():
    res, labels = parse_results_csv("metric,value,provenance\n,,\nsales,3,SAMPLE\n")
    assert res == {"sales": 3.0} and labels == ["SAMPLE"]


def test_support_refund_promise_replaced(tmp_path):
    ctx = make_ctx(tmp_path)
    agent = get_agent("support_drafter")
    agent._questions = "Can I get my money back?"
    out = agent.post_process(ctx, {"replies": [
        {"question": "Can I get my money back?", "reply": "Sure, we have refunded your order.", "escalate": False},
        {"question": "Arabic?", "reply": "Yes, the template is bilingual.", "escalate": False},
    ]})
    first, second = out["replies"]
    assert first["escalate"] is True and "refunded" not in first["reply"]
    assert second["escalate"] is False
    assert "mocked" not in out


def test_support_no_invented_replies(tmp_path):
    ctx = make_ctx(tmp_path)
    agent = get_agent("support_drafter")
    agent._questions = "Q1? Q2?"
    out = agent.post_process(ctx, {"replies": []})
    assert len(out["replies"]) == 1
    assert out["replies"][0]["escalate"] is True
    assert out["replies"][0]["reply"].startswith("STUBBED")


def test_support_redacts_customer_card(tmp_path):
    ctx = make_ctx(tmp_path, founder_inputs={"support_questions": "My card 4111 1111 1111 1111 was charged twice"})
    agent = get_agent("support_drafter")
    msg = agent.build_user_message(ctx)
    assert "4111" not in msg
    assert '<data untrusted="true">' in msg


def test_pricing_no_invented_price(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("pricing_analyst").post_process(ctx, {"comparable_claims": []})
    # The system never invents a price: it stays empty, or the founder sets it (asked through FounderInput).
    assert out["price_usd"] is None or out.get("price_source") == "founder"
    assert out["is_assumption"] is True


def test_memo_fallback_is_stop_without_evidence(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("persevere_pivot_memo").post_process(ctx, {"recommendation": "maybe"})
    assert out["recommendation"] == "stop"
    assert "stubbed" in out
    assert out["reasons"][0].startswith("STUBBED")


def test_memo_fallback_follows_evidence(tmp_path):
    ctx = make_ctx(tmp_path)
    _put(ctx, "phase6_step2_metrics", {"comparison": {"target_status": "not met"}})
    out = get_agent("persevere_pivot_memo").post_process(ctx, {})
    assert out["recommendation"] == "pivot"


def test_store_page_uses_phase4_price(tmp_path):
    ctx = make_ctx(tmp_path)
    _put(ctx, "phase4_step1_pricing", {"price_usd": 19.0})
    agent = get_agent("store_page_builder")
    out = agent.post_process(ctx, {"title": "Kit", "description": "d", "price_usd": 99, "bullets": ["a"]})
    assert out["price_usd"] == 19.0
    assert out["checkout"].startswith("MOCKED")
