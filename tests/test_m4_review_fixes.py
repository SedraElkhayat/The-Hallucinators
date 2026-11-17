# OWNER: M4
"""Tests for M2's quality-review fixes: critique shape, verified comparables only, founder-set policy
terms, free channels with named evidence, launch copy rules, support terms, SAMPLE/MOCKED labels."""
from __future__ import annotations

import gates
from agents import get_agent
from phases import phase4, phase5
from tests.helpers import make_ctx

UPSTREAM = {
    "claims": [{
        "claim": "MOCKED: the rival template costs 19 USD",
        "source_url": "https://example.com/mock/cs1",
        "quote": "MOCKED quote: complete freelancer template bundle for 19 USD",
        "verified": True, "assumption": False,
    }]
}


def put(ctx, step, data):
    ctx.store.put(step, data, "# test", "test")


# ---------------------------------------------------------------- pricing_analyst (MUST FIX)

def test_pricing_invented_url_not_counted(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase1_step5_competitors", UPSTREAM)
    out = get_agent("pricing_analyst").post_process(ctx, {
        "price_usd": 49, "range": [39, 59], "is_assumption": False,
        "comparable_claims": [{"claim": "Rival sells for 49 USD", "source_url": "https://invented.example.org/p",
                               "quote": "a quote the model made up for this price", "verified": True}],
    })
    assert out["comparable_claims"] == []
    assert out["is_assumption"] is True


def test_pricing_copied_verified_claim_kept(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase1_step5_competitors", UPSTREAM)
    c = dict(UPSTREAM["claims"][0], verified=None)
    out = get_agent("pricing_analyst").post_process(ctx, {"price_usd": 19, "range": [15, 25], "comparable_claims": [c]})
    assert len(out["comparable_claims"]) == 1
    assert out["comparable_claims"][0]["verified"] is True
    assert out["is_assumption"] is False


def test_pricing_unverified_upstream_claim_not_copied(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase2_step1_competitor_analysis", {"claims": [dict(UPSTREAM["claims"][0], verified=False)]})
    out = get_agent("pricing_analyst").post_process(ctx, {"price_usd": 19, "range": [15, 25],
                                                          "comparable_claims": [UPSTREAM["claims"][0]]})
    assert out["comparable_claims"] == [] and out["is_assumption"] is True


# ---------------------------------------------------------------- compliance critique shape

def _critique_ok(data):
    assert set(("issues", "verdict")) <= set(data)
    assert data["verdict"] in ("ok", "revise")
    for i in data["issues"]:
        assert i["severity"] in ("must_fix", "should_fix") and isinstance(i["text"], str)


def test_compliance4_shape_and_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Refund Policy", "text": "Full refund within 30 days. Fully compliant with GDPR.", "needs_legal_review": False}]})
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, {"issues": ["tone could be clearer"], "verdict": "ok"})
    _critique_ok(out)
    assert out["verdict"] == "revise"
    texts = " ".join(i["text"] for i in out["issues"] if i["severity"] == "must_fix")
    assert "needs_legal_review" in texts and "compliance" in texts and "refund window" in texts
    assert any(i["severity"] == "should_fix" for i in out["issues"])


def test_compliance4_clean_is_ok(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": None, "comparable_claims": [], "is_assumption": True})
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Refund Policy", "text": "Refund window: [FOUNDER TO SET: refund window].", "needs_legal_review": True}]})
    out = get_agent("compliance_reviewer_phase4").post_process(ctx, {"issues": [], "verdict": "ok"})
    _critique_ok(out)
    assert out["verdict"] == "ok" and out["issues"] == []


def test_compliance_bad_severity_normalized(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("compliance_reviewer_phase5").post_process(
        ctx, {"issues": [{"severity": "MUST FIX", "text": "x"}], "verdict": "fine"})
    _critique_ok(out)
    assert out["verdict"] == "revise"


def test_gate4_repeats_on_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", {"price_usd": 19, "comparable_claims": [], "is_assumption": True})
    put(ctx, "phase4_step2_offer", {"tiers": [], "positioning": "kit"})
    put(ctx, "phase4_step3_policies", {"documents": [{"name": "Terms", "text": "t", "needs_legal_review": True}]})
    put(ctx, "phase4_step4_compliance_review", {"issues": [{"severity": "must_fix", "text": "x"}], "verdict": "revise"})
    m = phase4.measure(ctx)
    assert m["compliance_must_fix"] == 1
    gates.preregister(ctx, 4, phase4.gate_checks(ctx))
    assert gates.evaluate(ctx, 4, m, attempt=0).outcome == "repeat"


def test_gate5_repeats_on_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase5_step5_sale_to_cash", {"double_deliveries": 0, "reconcile_balanced": True})
    put(ctx, "phase5_step4_launch_review", {"issues": [{"severity": "must_fix", "text": "x"}], "verdict": "revise"})
    m = phase5.measure(ctx)
    assert m["compliance_must_fix"] == 1
    gates.preregister(ctx, 5, phase5.gate_checks(ctx))
    assert gates.evaluate(ctx, 5, m, attempt=0).outcome == "repeat"


# ---------------------------------------------------------------- policy_drafter (MUST FIX)

def test_policy_refund_window_is_founder_placeholder(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("policy_drafter").post_process(ctx, {"documents": [
        {"name": "Refund Policy", "text": "Contact us within 14 days for a full refund."},
        {"name": "Terms of Service", "text": "Licence for one user. Fully compliant with all laws."}]})
    refund, terms = out["documents"]
    assert "14" not in refund["text"] and "[FOUNDER TO SET: refund window]" in refund["text"]
    assert "compliant" not in terms["text"].lower()
    assert all(d["needs_legal_review"] is True for d in out["documents"])


def test_policy_prompt_has_no_14_day_example():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "prompts" / "policy_drafter.md").read_text(encoding="utf-8")
    assert "14" not in text and "[FOUNDER TO SET" in text


# ---------------------------------------------------------------- channel_planner

def test_channels_paid_dropped_and_evidence_named(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("channel_planner").post_process(ctx, {"channels": [
        {"name": "Instagram paid ads", "evidence": "phase1_step5_market", "first_actions": ["Run ads"]},
        {"name": "Buy followers on TikTok", "evidence": "x", "first_actions": ["buy followers"]},
        {"name": "Founder's LinkedIn", "evidence": "phase2_step3_demand_test_plan: own network", "first_actions": ["Post"]},
        {"name": "Behance groups", "evidence": "designers hang out there", "first_actions": ["Share a checklist"]},
    ]})
    names = [c["name"] for c in out["channels"]]
    assert names == ["Founder's LinkedIn", "Behance groups"]
    assert len(out["dropped_channels"]) == 2
    assert out["channels"][1]["evidence"].startswith("ASSUMPTION")


# ---------------------------------------------------------------- launch posts and store page

def test_launch_post_with_counts_blocked_not_sent_for_approval(tmp_path):
    ctx = make_ctx(tmp_path)
    agent = get_agent("launch_post_drafter")
    out = agent.post_process(ctx, {"posts": [
        {"channel": "LinkedIn", "text": "Over 500 designers already use it and save 5 hours a week! - Sara, founder"},
        {"channel": "Community", "text": "A bilingual kit to track client revisions. Feedback welcome."},
    ]})
    blocked, ok = out["posts"]
    assert blocked["status"] == "blocked" and blocked["posted"] is False
    assert "500" not in blocked["text"]
    assert ok["status"] in ("approved", "rejected") and ok["text"].startswith("DRAFT: prepared for founder review")
    titles = [r["title"] for r in ctx.approvals.records]
    assert titles == ["Launch post 2 for Community"]


def test_store_page_strips_counts_and_testimonials(tmp_path):
    ctx = make_ctx(tmp_path)
    out = get_agent("store_page_builder").post_process(ctx, {
        "title": "Kit", "description": "Loved by 2,000 designers.", "price_usd": 19,
        "bullets": ["Saves 10 hours a week", "Testimonials from happy clients", "Arabic and English sheets"]})
    assert out["bullets"] == ["Arabic and English sheets"]
    assert out["description"].startswith("STUBBED")
    html = (ctx.out_dir / "phase5_step2_store_page.html").read_text(encoding="utf-8")
    assert "2,000" not in html and "10 hours" not in html


# ---------------------------------------------------------------- support_drafter

def test_support_terms_not_in_policies_escalate(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step3_policies", {"documents": [
        {"name": "Refund Policy", "text": "Refund window: [FOUNDER TO SET: refund window].", "needs_legal_review": True}]})
    agent = get_agent("support_drafter")
    agent._questions = "q"
    out = agent.post_process(ctx, {"replies": [
        {"question": "Refund?", "reply": "You can return it within 30 days.", "escalate": False},
        {"question": "Price?", "reply": "It costs $49.", "escalate": False},
        {"question": "Arabic?", "reply": "Thanks! Best regards, Sara (founder)", "escalate": False},
        {"question": "Arabic again?", "reply": "Yes, there is an Arabic version.", "escalate": False},
    ]})
    r = out["replies"]
    assert all(x["escalate"] for x in r[:3])
    assert "30 days" not in r[0]["reply"] and "$49" not in r[1]["reply"] and "Sara" not in r[2]["reply"]
    assert r[3]["escalate"] is False


def test_support_terms_in_policies_allowed(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step2_offer", {"tiers": [{"name": "Standard", "price_usd": 19.0}]})
    agent = get_agent("support_drafter")
    agent._questions = "q"
    out = agent.post_process(ctx, {"replies": [{"question": "Template price?", "reply": "The template is 19 USD.", "escalate": False}]})
    assert "19 USD" in out["replies"][0]["reply"]


# ---------------------------------------------------------------- persevere_pivot_memo

def test_memo_labels_sample_inputs(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase6_step2_metrics", {"provenance": "MOCKED", "comparison": {"target_status": "met"}})
    out = get_agent("persevere_pivot_memo").post_process(ctx, {
        "recommendation": "persevere", "reasons": ["Customers loved it"], "experiments": ["x"]})
    assert out["reasons"][0].startswith("[MOCKED data]")
    assert out["inputs_provenance"] == "MOCKED"


# ---------------------------------------------------------------- prompts follow the standard

def test_m4_prompts_follow_section10_standard():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "prompts"
    names = ["channel_planner", "compliance_reviewer_phase4", "compliance_reviewer_phase5", "launch_post_drafter",
             "metrics_analyst", "offer_packager", "persevere_pivot_memo", "policy_drafter", "pricing_analyst",
             "store_page_builder", "support_drafter"]
    for n in names:
        t = (root / f"{n}.md").read_text(encoding="utf-8")
        assert t.startswith(f"# {n}\n"), n
        pos = [t.index(h) for h in ("## Role", "## Task", "## Inputs", "## Output", "## Rules")]
        assert pos == sorted(pos), n
        assert "```json" in t and "<" in t.split("```json")[1], n
