"""Landing page: static, honest HTML; the founder approval is requested in code."""
from pathlib import Path

from tests.test_m3_helpers import ScriptedLLM, fixture, get_agent, make_ctx

from agents.landing_page_builder import DRAFT_LINE, render_landing_html

FORBIDDEN = ("<script", "countdown", "testimonial", "visitors", "counter", "<form", "http://", "https://", "<img",
             "<link")


def _html(tmp_path, copy=None, approve=True):
    agent = get_agent("landing_page_builder")
    llm = ScriptedLLM({"landing_page_builder": copy}) if copy else None
    ctx = make_ctx(tmp_path, llm=llm, approve=approve, seed=agent.inputs)
    agent.run(ctx)
    return ctx, (Path(ctx.out_dir) / "phase2_step4_landing_page.html").read_text(encoding="utf-8")


def test_generated_html_is_static_and_honest(tmp_path):
    ctx, page = _html(tmp_path)
    low = page.lower()
    for bad in FORBIDDEN:
        assert bad not in low, bad
    assert DRAFT_LINE in page
    assert fixture("landing_page_builder")["headline"] in page


def test_approval_is_requested_with_the_page(tmp_path):
    ctx, page = _html(tmp_path)
    assert len(ctx.approvals.requests) == 1
    req = ctx.approvals.requests[0]
    assert req["kind"] == "landing_page" and req["phase"] == 2 and req["content"] == page
    assert "halt_phase" not in ctx.extra


def test_dishonest_copy_is_removed(tmp_path):
    copy = {"headline": "Join 5,000 designers today",
            "subheadline": "Only 3 spots left, countdown ends tonight. Just $29.",
            "bullets": ["A checklist", "Testimonial: best kit ever", "Loved by 900 users already", "Costs $19 USD"],
            "call_to_action": "Join the waitlist"}
    ctx, page = _html(tmp_path, copy=copy)
    low = page.lower()
    for bad in ("5,000", "spots left", "countdown", "$29", "testimonial", "900", "$19", "<script"):
        assert bad not in low, bad
    assert "A checklist" in page and DRAFT_LINE in page


def test_price_shown_only_when_plan_has_one():
    copy = {"headline": "Kit", "subheadline": "Templates", "bullets": ["Costs $19"], "call_to_action": "Join"}
    page, removed = render_landing_html(copy, {})
    assert "$19" not in page and removed
    page, _ = render_landing_html(copy, {"price": "$19"})
    assert "$19" in page


def test_text_is_escaped():
    page, _ = render_landing_html({"headline": "<b>Kit</b>", "subheadline": "", "bullets": [],
                                   "call_to_action": "Join"}, {})
    assert "<b>Kit</b>" not in page and "&lt;b&gt;Kit&lt;/b&gt;" in page
