# OWNER: M4
"""Phase 5 store website (CONTEXT.md 4b.7) and gate outcomes per CONTEXT.md section 6."""
from __future__ import annotations

import gates
from agents import get_agent
from agents.m4_store_site import SITE_DIR, render_store_site, site_checks, write_site
from phases import phase4, phase5, phase6
from tests.helpers import make_ctx

DOCS = [{"name": "Refund Policy", "text": "Refund window: [FOUNDER TO SET: refund window].", "needs_legal_review": True},
        {"name": "Terms of Service", "text": "Draft terms <b>x</b>", "needs_legal_review": True}]


def put(ctx, step, data):
    ctx.store.put(step, data, "# test", "test")


def _run_builder(tmp_path, pricing):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", pricing)
    put(ctx, "phase4_step3_policies", {"documents": DOCS})
    out = get_agent("store_page_builder").post_process(
        ctx, {"title": "Kit <script>", "description": "Tracks client work.", "price_usd": 5, "bullets": ["Arabic and English"]})
    return ctx, out


def test_store_site_written_and_checked(tmp_path):
    ctx, out = _run_builder(tmp_path, {"price_usd": 19.0, "is_assumption": False})
    root = ctx.out_dir / SITE_DIR
    index = (root / "index.html").read_text(encoding="utf-8")
    assert (root / "policies" / "refund-policy.html").exists()
    assert (root / "policies" / "terms-of-service.html").exists()
    assert "<script" not in index.lower() and "&lt;script&gt;" in index
    assert "Price: 19.00 USD" in index and "ASSUMPTION" not in index
    assert out["site"]["site_checks"]["passed"] is True, out["site"]["site_checks"]
    for f in root.rglob("*"):
        assert f.is_dir() or f.suffix in (".html",)
    # mocked sale to cash never appears on the website
    assert "checkout" not in index.lower() or "never takes payments" in index
    assert "MOCKED checkout" not in index
    # the single-page draft for M1's e2e test is still written
    assert (ctx.out_dir / "phase5_step2_store_page.html").exists()


def test_store_site_price_assumption_label(tmp_path):
    ctx, _ = _run_builder(tmp_path, {"price_usd": 19.0, "is_assumption": True})
    index = (ctx.out_dir / SITE_DIR / "index.html").read_text(encoding="utf-8")
    assert "ASSUMPTION" in index


def test_policy_pages_marked_needs_legal_review(tmp_path):
    files = render_store_site({"title": "t", "bullets": []}, DOCS, False)
    for rel, text in files.items():
        if rel.startswith("policies/"):
            assert "needs legal review" in text
            assert "&lt;b&gt;" in text or "Refund" in text


def test_site_checks_catch_problems(tmp_path):
    root = write_site(tmp_path, {
        "index.html": '<html><body><script>x</script><a href="missing.html">m</a><a href="#nope">n</a>'
                      '<a href="http://insecure.example">i</a><form action="https://x.example" method="post"></form>'
                      '<p>Join 2,000 designers today</p></body></html>'})
    res = site_checks(root)
    text = " ".join(res["failures"])
    assert res["passed"] is False
    for needle in ("script", "missing.html", "#nope", "https", "form", "banned"):
        assert needle in text, needle


def test_failed_site_checks_are_must_fix(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase5_step2_store_page", {"site": {"site_checks": {"passed": False, "failures": ["index.html: script"]}}})
    out = get_agent("compliance_reviewer_phase5").post_process(ctx, {"issues": [], "verdict": "ok"})
    assert out["verdict"] == "revise"
    assert any("store site" in i["text"] for i in out["issues"])


def _outcome(ctx, phase, mod, metrics):
    gates.preregister(ctx, phase, mod.gate_checks(ctx))
    return gates.evaluate(ctx, phase, metrics, attempt=0).outcome


def test_gate_on_fail_matches_contract(tmp_path):
    ctx = make_ctx(tmp_path)
    m4 = {"price_sourced_or_labeled": 0, "policies_labeled": 1, "banned_claims": 0, "payment_code_present": 0,
          "compliance_must_fix": 0}
    assert _outcome(ctx, 4, phase4, m4) == "repeat"
    m5 = {"unapproved_released": 0, "sale_to_cash_passed": 1, "double_deliveries": 0, "reconcile_balanced": 0,
          "compliance_must_fix": 0}
    assert _outcome(ctx, 5, phase5, m5) == "repeat"
    assert _outcome(ctx, 6, phase6, {"inputs_labeled": 0, "memo_written": 1}) == "repeat"
    assert _outcome(ctx, 5, phase5, dict(m5, reconcile_balanced=1, unapproved_released=1)) == "stop"
