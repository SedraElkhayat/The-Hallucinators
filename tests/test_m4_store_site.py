# OWNER: M4
"""Phase 5 store website (CONTEXT.md 4b.7) and gate outcomes per CONTEXT.md section 6."""
from __future__ import annotations

import gates
from agents import get_agent
from agents.m4_store_site import (SITE_DIR, basic_site_checks, build_store_site, render_store_site, site_checks,
                                  write_site)
from phases import phase4, phase5, phase6
from tests.helpers import make_ctx

PHASE3 = {"headline": "Client tracker for freelance designers", "value_proposition": "Track client work in one place.",
          "features": ["Project board"], "faq": [{"q": "Is it bilingual?", "a": "Yes, Arabic and English."}],
          "claims": [{"claim": "MOCKED rival sells templates", "source_url": "https://example.com/mock/1",
                      "quote": "MOCKED quote", "verified": True}]}
DOCS = [{"name": "Refund Policy", "text": "Refund window: [FOUNDER TO SET: refund window].", "needs_legal_review": True},
        {"name": "Terms of Service", "text": "Draft terms <b>x</b>", "needs_legal_review": True}]


def put(ctx, step, data):
    ctx.store.put(step, data, "# test", "test")


def _run_builder(tmp_path, pricing):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase4_step1_pricing", pricing)
    put(ctx, "phase4_step3_policies", {"documents": DOCS})
    put(ctx, "phase3_step3_build", PHASE3)
    out = get_agent("store_page_builder").post_process(
        ctx, {"title": "Kit <script>", "description": "Tracks client work.", "price_usd": 5, "bullets": ["Arabic and English"]})
    return ctx, out


def test_store_site_written_and_checked(tmp_path):
    ctx, out = _run_builder(tmp_path, {"price_usd": 19.0, "is_assumption": False})
    root = ctx.out_dir / SITE_DIR
    index = (root / "index.html").read_text(encoding="utf-8")
    assert (root / "policies" / "refund-policy.html").exists()
    assert (root / "policies" / "terms-of-service.html").exists()
    # M3's cleaner drops the unsafe headline; the Phase 3 headline is used instead
    assert "<script" not in index.lower() and "script" not in index.lower()
    assert "Client tracker for freelance designers" in index
    assert "Tracks client work." in index and "Arabic and English" in index
    assert 'href="policies/refund-policy.html"' in index and "needs legal review" in index
    price = index.split('id="price"')[1].split("</section>")[0]
    assert "Price: 19.00 USD" in price and "ASSUMPTION" not in price
    assert "checkout" not in index.lower()
    assert out["site"]["site_checks"]["passed"] is True, out["site"]["site_checks"]
    for f in root.rglob("*"):
        assert f.is_dir() or f.suffix in (".html",)
    # no buy button or payment UI on the website, one honest line in the price section
    # the only button is the template's disabled demo sign-up button, never a buy button
    assert index.lower().count("<button") == 1 and "Demo only: nothing is sent or stored" in index
    assert "buy" not in index.lower() and "pay now" not in index.lower()
    assert "MOCKED checkout" not in index
    assert "Purchasing is not open yet; the founder sets it up." in index
    # the single-page draft for M1's e2e test keeps its labeled MOCKED checkout button
    draft = (ctx.out_dir / "phase5_step2_store_page.html").read_text(encoding="utf-8")
    assert "MOCKED checkout: no real payment" in draft


def test_store_site_price_assumption_label(tmp_path):
    ctx, _ = _run_builder(tmp_path, {"price_usd": 19.0, "is_assumption": True})
    index = (ctx.out_dir / SITE_DIR / "index.html").read_text(encoding="utf-8")
    assert "ASSUMPTION" in index.split('id="price"')[1].split("</section>")[0]


def test_policy_pages_marked_needs_legal_review(tmp_path):
    files = build_store_site({"title": "t", "description": "d", "bullets": ["f"]}, DOCS, False, PHASE3)
    assert set(files) == {"index.html", "policies/refund-policy.html", "policies/terms-of-service.html"}
    for rel, text in files.items():
        if rel.startswith("policies/"):
            assert "needs legal review" in text
    assert "&lt;b&gt;" in files["policies/terms-of-service.html"]


def test_store_site_uses_m3_template_and_checks(tmp_path):
    files = build_store_site({"title": "Store kit", "description": "d", "bullets": ["f"], "price_usd": 19.0},
                             DOCS, True, PHASE3)
    index = files["index.html"]
    for sid in ("value-proposition", "features", "evidence", "price", "faq", "policies", "signup"):
        assert f'id="{sid}"' in index
    assert "Price: 19.00 USD (ASSUMPTION" in index and "Price: set in Phase 4" not in index
    root = write_site(tmp_path, files)
    res = site_checks(root)
    assert res["passed"], res["failures"]


def test_store_site_fallback_without_template(tmp_path):
    files = render_store_site({"title": "t", "description": "d", "bullets": ["f"]}, DOCS, False)
    assert "Purchasing is not open yet; the founder sets it up." in files["index.html"]
    res = basic_site_checks(write_site(tmp_path, files))
    assert res["passed"], res["failures"]


def test_site_checks_catch_problems(tmp_path):
    root = write_site(tmp_path, {
        "index.html": '<html><body><script>x</script><a href="missing.html">m</a><a href="#nope">n</a>'
                      '<form action="https://x.example" method="post"></form>'
                      '<p>Join 2,000 designers today</p></body></html>'})
    for res in (site_checks(root), basic_site_checks(root)):
        assert res["passed"] is False
        text = " ".join(res["failures"]).lower()
        for needle in ("script", "missing.html", "nope", "form"):
            assert needle in text, (needle, res["failures"])


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


def test_policy_payment_words_reworded_so_site_checks_pass(tmp_path):
    from agents.policy_drafter import enforce_policy_rules
    doc = enforce_policy_rules({"name": "Privacy Policy",
                                "text": "We do not collect client data, passwords or card numbers. Checkout runs on Stripe."})
    low = doc["text"].lower()
    assert "card number" not in low and "checkout" not in low and "stripe" not in low
    assert "payment card details" in low
    files = build_store_site({"title": "t", "description": "d", "bullets": ["f"]}, [doc], False, PHASE3)
    res = site_checks(write_site(tmp_path, files))
    assert res["passed"], res["failures"]
