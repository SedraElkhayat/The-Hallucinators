"""The founder website (Phase 3 contract): template, escaping, evidence labels, links, sections, the one
demo sign-up form, QA site_checks, the Gate 3 metric, the publish guide and a missing template."""
import json
import re
from pathlib import Path

import pytest

import gates
from agents.m3_site import (DEMO_FORM_LABEL, PHASE3_POLICIES, PHASE3_PRICE, REQUIRED_SECTIONS, TEMPLATE_PATH,
                            check_site, check_site_dir, fill_template, sanitize_content)
from phases import phase3
from tests.test_m3_helpers import ScriptedLLM, fixture, get_agent, make_ctx, put

SITE = "phase3_step3_site"
DEMO_FORM = ('<form aria-label="Demo sign-up box"><p><span class="label">Demo only: nothing is sent or stored</span>'
             '</p><input type="email" placeholder="you@example.com" disabled>'
             '<button type="button" disabled>Join the waitlist</button></form>')


def _content(**over):
    c = {"headline": "Onboarding kit for solo designers", "value_proposition": "Templates for each new client.",
         "features": ["Onboarding checklist", "Intake questionnaire"],
         "faq": [{"q": "What formats?", "a": "Markdown and plain text."}],
         "claims": [{"claim": "Rival A sells kits to agencies", "source_url": "https://example.com/a", "verified": True}]}
    c.update(over)
    return c


def _site(tmp_path, page):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    return check_site(page, tmp_path)


def _build(tmp_path, resp=None):
    agent = get_agent("builder")
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"builder": resp}) if resp else None, seed=agent.inputs)
    data = agent.run(ctx).data
    return ctx, data


# ---------------------------------------------------------------- template

def test_template_is_one_self_contained_mobile_ready_file():
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    low = text.lower()
    assert "<style>" in low and "<script" not in low and "<link" not in low and "@import" not in low
    assert not re.search(r"(src|href)\s*=\s*[\"']?(https?:)?//", low)
    assert 'name="viewport"' in text and "width=device-width" in text
    for sid in REQUIRED_SECTIONS:
        assert f'id="{sid}"' in text
    assert DEMO_FORM_LABEL in text
    assert [p.name for p in TEMPLATE_PATH.parent.iterdir()] == ["index.html"]  # no separate .css file


def test_filled_phase3_page_passes_and_shows_placeholders(tmp_path):
    page = fill_template(_content())
    assert PHASE3_PRICE in page and PHASE3_POLICIES in page
    assert _site(tmp_path, page) == {"passed": True, "failures": []}


# ---------------------------------------------------------------- escaping and injection

def test_script_injected_through_model_content_is_escaped(tmp_path):
    page = fill_template(_content(headline="<script>alert(1)</script>", features=["<b>bold</b>"]))
    assert "<script" not in page.lower() and "&lt;script&gt;" in page and "<b>" not in page
    assert _site(tmp_path, page)["passed"]


def test_quote_injected_through_model_content_cannot_open_an_attribute(tmp_path):
    payload = '" onmouseover="alert(1)'
    page = fill_template(_content(value_proposition=payload,
                                  claims=[{"claim": "x claim", "source_url": "https://e.com/a" + payload, "verified": True}]))
    assert 'onmouseover="alert' not in page
    assert "&quot; onmouseover=&quot;alert(1)" in page
    claim = [line for line in page.splitlines() if "x claim" in line][0]
    assert "href" not in claim and "ASSUMPTION" in claim  # an invalid source URL is never linked
    assert _site(tmp_path, page)["passed"]


def test_template_slot_injected_through_model_content_is_not_expanded(tmp_path):
    page = fill_template(_content(headline="{{FEATURES}} {{PRICE}}"))
    assert "{{" not in page and "&#123;&#123;FEATURES&#125;&#125;" in page
    assert _site(tmp_path, page)["passed"]


def test_builder_drops_injected_markup_and_keeps_the_page_valid(tmp_path):
    resp = dict(fixture("builder"), headline='<img src=x onerror="alert(1)">',
                features=fixture("builder")["features"] + ['"><script>fetch("https://evil.example")</script>'])
    ctx, data = _build(tmp_path, resp)
    page = (Path(ctx.out_dir) / SITE / "index.html").read_text(encoding="utf-8")
    assert "<script" not in page.lower() and "onerror" not in page and "evil.example" not in page
    assert {d["field"] for d in data["dropped"]} >= {"headline", "features"}
    result = check_site_dir(Path(ctx.out_dir) / SITE)
    assert not result["passed"] and "value proposition has no headline" in result["failures"]


# ---------------------------------------------------------------- empty content

def test_empty_content_fails_the_site_checks(tmp_path):
    result = _site(tmp_path, fill_template({}))
    assert not result["passed"]
    assert "value proposition has no headline" in result["failures"]
    assert "value proposition is empty" in result["failures"]
    assert "features section lists no features" in result["failures"]


def test_empty_page_fails(tmp_path):
    assert check_site("", tmp_path) == {"passed": False, "failures": ["page is empty"]}


# ---------------------------------------------------------------- evidence

def test_only_verified_claims_with_https_source_are_shown_as_facts(tmp_path):
    claims = [{"claim": "Verified claim", "source_url": "https://example.com/v", "verified": True},
              {"claim": "Unverified claim", "source_url": "https://example.com/u", "verified": False},
              {"claim": "Verified but http", "source_url": "http://example.com/h", "verified": True},
              {"claim": "No source at all", "verified": True},
              {"claim": "Already labeled ASSUMPTION", "verified": False}]
    page = fill_template(_content(claims=claims))
    lines = {c["claim"]: [l for l in page.splitlines() if c["claim"].replace(" ASSUMPTION", "") in l][0]
             for c in claims}
    assert 'href="https://example.com/v"' in lines["Verified claim"] and "ASSUMPTION" not in lines["Verified claim"]
    for name in ("Unverified claim", "Verified but http", "No source at all"):
        assert "ASSUMPTION" in lines[name] and "href" not in lines[name]
    assert lines["Already labeled ASSUMPTION"].count("ASSUMPTION") == 1
    assert _site(tmp_path, page)["passed"]


def test_builder_uses_claim_checker_not_the_model_verified_flag(tmp_path):
    resp = dict(fixture("builder"), claims=[{"claim": "Model says verified", "source_url": "https://real.example/x",
                                             "verified": True}])
    ctx, data = _build(tmp_path, resp)
    claim = data["claims"][0]
    # Mock mode marks only https://example.com/mock/ sources verified; the model's own flag is not trusted.
    assert claim["shown_as"] == "ASSUMPTION"
    page = (Path(ctx.out_dir) / SITE / "index.html").read_text(encoding="utf-8")
    assert "real.example" not in page


def test_unsourced_claim_on_page_fails(tmp_path):
    page = _page_replace('<ul>\n        <li class="claim fact">', '<ul>\n        <li class="claim">Half of designers hate onboarding</li>\n        <li class="claim fact">')
    result = _site(tmp_path, page)
    assert any("no https source link and no ASSUMPTION label" in f for f in result["failures"])


def test_number_without_source_outside_evidence_fails_unless_simulated(tmp_path):
    page = _page_replace("<li>Onboarding checklist</li>", "<li>Saves 5 hours a week</li>")
    assert "number without a source outside the evidence section" in _site(tmp_path, page)["failures"]
    page = _page_replace("<li>Onboarding checklist</li>", "<li>40 sign-ups (SIMULATED, not real users)</li>")
    assert _site(tmp_path / "b", page)["passed"]
    content, dropped = sanitize_content(_content(features=["Saves 5 hours a week"]))
    assert content["features"] == [] and dropped[0]["reasons"] == ["number without a source"]


# ---------------------------------------------------------------- links and sections

def _page_replace(old, new):
    page = fill_template(_content())
    assert old in page
    return page.replace(old, new, 1)


@pytest.mark.parametrize("href,expected", [
    ("missing.html", "points to a missing file"),
    ("#nowhere", "anchor #nowhere does not exist"),
    ("../index.html", "leaves the site folder"),
    ("http://example.com", "must be https://"),
    ("https://exa mple.com", "malformed external link"),
    ("https://nodot", "malformed external link"),
    ("javascript:alert(1)", "must be https://"),
    ("//cdn.example.com/x", "must be https://"),
    ("policies/terms.html#refunds", "points to a missing file"),
])
def test_broken_links_fail(tmp_path, href, expected):
    page = _page_replace("<li>Onboarding checklist</li>", f'<li><a href="{href}">Onboarding checklist</a></li>')
    result = _site(tmp_path, page)
    assert any(expected in f for f in result["failures"]), result["failures"]


def test_valid_local_link_and_anchor_resolve(tmp_path):
    (tmp_path / "policies").mkdir(parents=True)
    (tmp_path / "policies" / "terms.html").write_text('<!DOCTYPE html><h2 id="refunds">x</h2>', encoding="utf-8")
    page = _page_replace("<li>Onboarding checklist</li>",
                         '<li><a href="policies/terms.html#refunds">terms</a> <a href="#faq">FAQ</a> '
                         '<a href="https://example.com/docs">docs</a></li>')
    assert _site(tmp_path, page)["passed"]
    page2 = page.replace("#refunds", "#missing")
    assert any("anchor #missing does not exist" in f for f in _site(tmp_path, page2)["failures"])


@pytest.mark.parametrize("sid", REQUIRED_SECTIONS)
def test_missing_section_fails(tmp_path, sid):
    page = fill_template(_content()).replace(f'<section id="{sid}">', '<section id="other">', 1)
    page = page.replace(f'href="#{sid}"', 'href="#other"')
    result = _site(tmp_path, page)
    assert f'missing section "{sid}"' in result["failures"]


def test_external_requests_fail(tmp_path):
    for snippet, expected in [('<img src="https://cdn.example.com/a.png" alt="">', "external request"),
                              ("<style>@import url(https://fonts.example.com/x.css);</style>", "external request in CSS"),
                              ('<link rel="stylesheet" href="https://cdn.example.com/a.css">', "external request")]:
        page = _page_replace("</ul>", "</ul>" + snippet)
        assert any(expected in f for f in _site(tmp_path, page)["failures"]), snippet


def test_unclosed_markup_and_unfilled_slot_fail(tmp_path):
    assert any("not closed" in f or "unclosed" in f
               for f in _site(tmp_path, _page_replace("<h2>Features</h2>", "<h2>Features</h2><div>"))["failures"])
    assert "unfilled template slot" in _site(tmp_path, _page_replace("<h2>FAQ</h2>", "<h2>FAQ {{X}}</h2>"))["failures"]


def test_phase3_price_and_policy_placeholders_are_required(tmp_path):
    page = _page_replace(PHASE3_PRICE, "Price: $19")
    failures = _site(tmp_path, page)["failures"]
    assert any("price slot must read" in f for f in failures)


def test_phase5_fill_with_price_and_policy_pages(tmp_path):
    (tmp_path / "policies").mkdir(parents=True)
    (tmp_path / "policies" / "terms.html").write_text("<!DOCTYPE html><title>t</title>", encoding="utf-8")
    page = fill_template(_content(), phase=5, price_text="Price: 19 USD, one-time (Phase 4)",
                         policy_links=[{"title": "Terms (needs legal review)", "href": "policies/terms.html"}])
    assert "Price: 19 USD" in page and 'href="policies/terms.html"' in page
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    result = check_site(page, tmp_path, phase=5)
    assert all("price" not in f.lower() or "number" in f for f in result["failures"])
    (tmp_path / "policies" / "terms.html").unlink()
    assert any("missing file" in f for f in check_site(page, tmp_path, phase=5)["failures"])


# ---------------------------------------------------------------- the sign-up box

def _with_form(form):
    page = fill_template(_content())
    start, end = page.index("<form"), page.index("</form>") + len("</form>")
    return page[:start] + form + page[end:]


def test_the_labeled_demo_form_passes(tmp_path):
    assert _site(tmp_path, _with_form(DEMO_FORM))["passed"]


@pytest.mark.parametrize("form,expected", [
    (DEMO_FORM.replace("<form ", '<form action="https://example.com/s" '), "action attribute"),
    (DEMO_FORM.replace("<form ", '<form method="post" '), "method attribute"),
    (DEMO_FORM.replace("<form ", '<form method="get" '), "method attribute"),
    (DEMO_FORM.replace('type="button" disabled', 'type="submit"'), 'button of type="submit"'),
    (DEMO_FORM.replace('type="button" disabled', 'type="submit" disabled'), 'button of type="submit"'),
    (DEMO_FORM.replace('<button type="button" disabled>', "<button>"), "would submit"),
    (DEMO_FORM.replace('<input type="email"', '<input type="password"'), "password input"),
    (DEMO_FORM.replace('placeholder="you@example.com"', 'name="card_number"'), "password or payment field"),
    (DEMO_FORM.replace('placeholder="you@example.com"', 'autocomplete="cc-csc" name="cvc"'), "password or payment field"),
    (DEMO_FORM.replace(" disabled>Join", ">Join").replace('type="email" placeholder="you@example.com" disabled',
                                                         'type="email"'), "must be disabled or readonly"),
    (DEMO_FORM.replace(DEMO_FORM_LABEL, "Sign up now"), "missing the visible label"),
    (DEMO_FORM.replace("<button", '<button formaction="https://x.example/s"'), "formaction"),
])
def test_every_other_form_fails(tmp_path, form, expected):
    result = _site(tmp_path, _with_form(form))
    assert not result["passed"]
    assert any(expected in f for f in result["failures"]), result["failures"]


def test_a_second_form_fails(tmp_path):
    page = _with_form(DEMO_FORM).replace("<h2>FAQ</h2>", "<h2>FAQ</h2>" + DEMO_FORM, 1)
    failures = _site(tmp_path, page)["failures"]
    assert any("2 forms found" in f for f in failures) and "a form outside the sign-up section" in failures


def test_demo_form_with_script_or_network_call_fails(tmp_path):
    page = _with_form(DEMO_FORM + "<script>fetch('https://x.example')</script>")
    failures = _site(tmp_path, page)["failures"]
    assert "banned content: script tag" in failures and "network code present" in failures


def test_missing_form_fails(tmp_path):
    assert "sign-up box has no form" in _site(tmp_path, _with_form("<p>Sign-up coming soon</p>"))["failures"]


# ---------------------------------------------------------------- builder, QA, gate, guide

def test_builder_writes_the_site_folder_manifest_and_publish_guide(tmp_path):
    ctx, data = _build(tmp_path)
    out = Path(ctx.out_dir)
    assert re.fullmatch(r"phase\d+_step\d+_[\w-]+", SITE) and (out / SITE / "index.html").is_file()
    assert not (out / "phase3_build").exists()
    assert data["site_dir"] == SITE and data["deployed"] is False and data["files"][0]["path"] == "index.html"
    assert (out / "phase3_step3_build.json").exists()
    guide = json.loads((out / "phase3_step7_publish_guide.json").read_text(encoding="utf-8"))
    md = (out / "phase3_step7_publish_guide.md").read_text(encoding="utf-8")
    assert guide["system_publishes"] is False and guide["published_by"] == "founder"
    assert {o["name"] for o in guide["options"]} == {"GitHub Pages", "Netlify"}
    assert "never publishes" in md and "GitHub Pages" in md and "Netlify" in md
    assert check_site_dir(out / SITE)["passed"]


def test_missing_template_writes_no_site_and_gate3_repeats(tmp_path, monkeypatch):
    import agents.m3_site as m3_site
    monkeypatch.setattr(m3_site, "TEMPLATE_PATH", tmp_path / "nope" / "index.html")
    with pytest.raises(FileNotFoundError):
        fill_template(_content())
    ctx, data = _build(tmp_path / "run")
    assert "site template not found" in data["error"] and data["files"] == []
    assert not (Path(ctx.out_dir) / SITE / "index.html").exists()
    put(ctx, "phase3_step1_spec", fixture("spec_writer"))
    qa = get_agent("qa_agent").run(ctx).data
    assert qa["site_checks"]["passed"] is False
    assert qa["site_checks"]["failures"] == [f"{SITE}/index.html missing"]
    m = phase3.measure(ctx)
    assert m["site_checks_passed"] == 0
    put(ctx, "phase3_step6_content_review", {"issues": [], "verdict": "ok"})
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, phase3.measure(ctx), 0).outcome == "repeat"


def test_qa_reports_site_checks_and_gate_metric(tmp_path):
    ctx, _ = _build(tmp_path)
    put(ctx, "phase3_step1_spec", fixture("spec_writer"))
    qa = get_agent("qa_agent").run(ctx).data
    assert qa["site_checks"] == {"passed": True, "failures": []} and qa["pass_ratio"] == 1.0
    assert phase3.measure(ctx)["site_checks_passed"] == 1
    page = Path(ctx.out_dir) / SITE / "index.html"
    page.write_text(page.read_text(encoding="utf-8").replace('href="#faq"', 'href="#gone"'), encoding="utf-8")
    qa = get_agent("qa_agent").run(ctx).data
    assert qa["site_checks"]["passed"] is False and phase3.measure(ctx)["site_checks_passed"] == 0


def test_site_checks_metric_is_zero_without_a_qa_report(tmp_path):
    ctx = make_ctx(tmp_path)
    assert phase3.measure(ctx)["site_checks_passed"] == 0
