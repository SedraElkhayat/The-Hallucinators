"""Phase 3: the website builder sandbox rules, QA pass ratio, honesty counting, nothing deployed, Gate 3."""
from pathlib import Path

import pytest

import gates
from phases import phase3

from tests.test_m3_helpers import PHASE3_AGENTS, ScriptedLLM, fixture, get_agent, make_ctx, put

from agents.m3_site import check_site, fill_template
from agents.qa_agent import run_check

SITE = "phase3_step3_site"


def _good_content():
    return {"headline": "Onboarding kit", "value_proposition": "Templates for each new client.",
            "features": ["Onboarding checklist"], "faq": [{"q": "Formats?", "a": "Markdown."}],
            "claims": [{"claim": "Rival A sells kits", "source_url": "https://example.com/a", "verified": True}]}


def _page_with(snippet: str) -> str:
    """A valid filled page with raw markup inserted into the features section (bypassing the builder)."""
    page = fill_template(_good_content())
    return page.replace("<li>Onboarding checklist</li>", f"<li>Onboarding checklist</li>{snippet}", 1)


def test_stages_and_constants():
    assert phase3.PHASE == 3 and phase3.PIVOT_TO == 2
    assert [a for stage in phase3.STAGES for a in stage] == PHASE3_AGENTS
    assert {c.metric for c in phase3.gate_checks(None)} == {"acceptance_pass_ratio", "honesty_must_fix",
                                                           "site_checks_passed", "deployed"}
    site = [c for c in phase3.gate_checks(None) if c.id == "site_checks"][0]
    assert (site.metric, site.op, site.value, site.on_fail) == ("site_checks_passed", "==", 1, "repeat")


@pytest.mark.parametrize("href", ["../escape.md", "/etc/passwd.txt", "a/../../b.md", "C:/x.md", "run.py"])
def test_site_rejects_links_that_leave_or_miss_the_folder(tmp_path, href):
    page = _page_with(f'<li><a href="{href}">x</a></li>')
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    assert not check_site(page, tmp_path)["passed"]


@pytest.mark.parametrize("content", [
    "<script>alert(1)</script>",
    "<form action='/buy'><input name='x'></form>",
    "<li>Enter your card number and CVV at checkout</li>",
    "<li>Pay with Stripe or PayPal</li>",
    '<img src="https://tracker.example/p.gif" width="1" height="1">',
    "<li>Testimonial: this kit changed my life</li>",
])
def test_site_rejects_unsafe_content(tmp_path, content):
    page = _page_with(content)
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    assert not check_site(page, tmp_path)["passed"]


@pytest.mark.parametrize("content", [
    "<script>alert(1)</script>",
    "<form action='/buy'><input name='x'></form>",
    "Enter your card number and CVV at checkout",
    "Pay with Stripe or PayPal",
    '<img src="https://tracker.example/p.gif" width="1" height="1">',
    "Testimonial: this kit changed my life",
])
def test_unsafe_model_content_never_reaches_the_site(tmp_path, content):
    resp = dict(fixture("builder"), features=fixture("builder")["features"] + [content])
    agent = get_agent("builder")
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"builder": resp}), seed=agent.inputs)
    data = agent.run(ctx).data
    page = (Path(ctx.out_dir) / SITE / "index.html").read_text(encoding="utf-8")
    assert content not in page and content.lower() not in page.lower()
    assert any(d["field"] == "features" for d in data["dropped"])
    assert check_site(page, Path(ctx.out_dir) / SITE)["passed"]


def test_oversized_and_empty_model_content(tmp_path):
    agent = get_agent("builder")
    big = dict(fixture("builder"), headline="x" * 20001)
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"builder": big}), seed=agent.inputs)
    data = agent.run(ctx).data
    assert len(data["headline"]) <= 160
    empty = {"headline": "", "value_proposition": "", "features": [], "faq": [], "claims": []}
    ctx = make_ctx(tmp_path / "e", llm=ScriptedLLM({"builder": empty}), seed=agent.inputs)
    agent.run(ctx)
    result = check_site((Path(ctx.out_dir) / SITE / "index.html").read_text(encoding="utf-8"), Path(ctx.out_dir) / SITE)
    assert not result["passed"]
    assert "value proposition has no headline" in result["failures"]
    assert "features section lists no features" in result["failures"]


def test_builder_limits_lists():
    from agents.m3_site import sanitize_content
    content, _ = sanitize_content({"headline": "h", "value_proposition": "v",
                                   "features": [f"Feature {chr(65 + i)}" for i in range(12)],
                                   "faq": [{"q": f"q{i}", "a": "a"} for i in range(12)],
                                   "claims": [{"claim": f"claim {i}"} for i in range(15)]})
    assert len(content["features"]) == 8 and len(content["faq"]) == 8 and len(content["claims"]) == 10


def test_builder_run_writes_only_inside_the_site_folder(tmp_path):
    resp = dict(fixture("builder"), files=[{"path": "../outside.md", "content": "# escape"},
                                           {"path": "pay.html", "content": "<form>card number</form>"}])
    agent = get_agent("builder")
    llm = ScriptedLLM({"builder": resp})
    ctx = make_ctx(tmp_path, llm=llm, seed=agent.inputs)
    data = agent.run(ctx).data
    root = Path(ctx.out_dir) / SITE
    written = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert written == ["index.html"]
    assert not (Path(ctx.out_dir) / "outside.md").exists() and not (tmp_path / "outside.md").exists()
    assert not (Path(ctx.out_dir) / "pay.html").exists()
    assert data["files"] == [{"path": "index.html", "chars": len((root / "index.html").read_text(encoding="utf-8"))}]
    assert llm.calls.count("builder") == 1  # the model never writes files, so there is nothing to rewrite
    assert phase3.measure(ctx)["deployed"] == 0


def test_qa_pass_ratio(tmp_path):
    ctx = make_ctx(tmp_path)
    root = Path(ctx.out_dir) / SITE
    root.mkdir(parents=True)
    (root / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    (root / "guide.md").write_text("# Guide\nFirst call", encoding="utf-8")
    spec = {"mvp_scope": [], "user_stories": [], "out_of_scope": [], "acceptance_tests": [
        {"id": "T1", "description": "", "check": {"type": "file_exists", "path": "index.html", "text": ""}},
        {"id": "T2", "description": "", "check": {"type": "text_contains", "path": "guide.md", "text": "First call"}},
        {"id": "T3", "description": "", "check": {"type": "text_contains", "path": "guide.md", "text": "Missing"}},
        {"id": "T4", "description": "", "check": {"type": "file_exists", "path": "../secret.md", "text": ""}},
        {"id": "T5", "description": "", "check": {"type": "looks_good", "path": "index.html", "text": ""}},
    ]}
    put(ctx, "phase3_step1_spec", spec)
    put(ctx, "phase3_step3_build", {"files": [{"path": "index.html"}, {"path": "guide.md"}], "notes": ""})
    data = get_agent("qa_agent").run(ctx).data
    assert [r["passed"] for r in data["results"]] == [True, True, False, False, False]
    assert data["pass_ratio"] == 0.4
    assert phase3.measure(ctx)["acceptance_pass_ratio"] == 0.4


def test_run_check_on_missing_site_dir(tmp_path):
    passed, detail = run_check(tmp_path / "nope", {"type": "file_exists", "path": "a.md"})
    assert not passed and "not found" in detail


def test_content_reviewer_must_fix_counted(tmp_path):
    agent = get_agent("content_reviewer")
    resp = {"issues": [{"severity": "must_fix", "text": "MOCKED invented number", "file": "index.html"},
                       {"severity": "should_fix", "text": "MOCKED wording", "file": "x"}], "verdict": "ok"}
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"content_reviewer": resp}), seed=agent.inputs)
    data = agent.run(ctx).data
    assert data["verdict"] == "revise"
    assert phase3.measure(ctx)["honesty_must_fix"] == 1


def test_honesty_counts_code_found_violations(tmp_path):
    ctx = make_ctx(tmp_path)
    root = Path(ctx.out_dir) / SITE
    root.mkdir(parents=True)
    (root / "index.html").write_text("<p>Trusted by 10,000 designers</p><script>fetch('x')</script>", encoding="utf-8")
    put(ctx, "phase3_step6_content_review", {"issues": [], "verdict": "ok"})
    put(ctx, "phase3_step3_build", {"files": [{"path": "index.html"}], "notes": ""})
    m = phase3.measure(ctx)
    assert m["honesty_must_fix"] >= 2
    assert m["deployed"] == 1  # network code present


def _full_phase3(tmp_path):
    seeds = ["phase2_step2_lean_canvas", "phase2_step9_validation_report", "phase2_step3_demand_test_plan",
             "phase1_step4_idea_card", "phase1_step2_clarification", "phase2_step4_landing_page"]
    ctx = make_ctx(tmp_path, seed=seeds)
    for stage in phase3.STAGES:
        for name in stage:
            get_agent(name).run(ctx)
    return ctx


def test_mock_phase3_run_passes_gate3_and_deploys_nothing(tmp_path):
    ctx = _full_phase3(tmp_path)
    m = phase3.measure(ctx)
    assert m == {"acceptance_pass_ratio": 1.0, "site_checks_passed": 1, "honesty_must_fix": 0, "deployed": 0}
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, m, 0).outcome == "go"
    assert (Path(ctx.out_dir) / "phase3_gate_decision.md").exists()


def test_gate3_failures(tmp_path):
    ctx = make_ctx(tmp_path)
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    ok = {"acceptance_pass_ratio": 1.0, "site_checks_passed": 1, "honesty_must_fix": 0, "deployed": 0}
    assert gates.evaluate(ctx, 3, ok, 0).outcome == "go"
    assert gates.evaluate(ctx, 3, dict(ok, acceptance_pass_ratio=0.5), 0).outcome == "repeat"
    assert gates.evaluate(ctx, 3, dict(ok, site_checks_passed=0), 0).outcome == "repeat"
    assert gates.evaluate(ctx, 3, dict(ok, deployed=1), 0).outcome == "stop"
    assert gates.evaluate(ctx, 3, dict(ok, site_checks_passed=0, deployed=1), 0).outcome == "stop"


def test_script_or_form_is_honesty_repeat_not_deployed(tmp_path):
    ctx = make_ctx(tmp_path)
    root = Path(ctx.out_dir) / SITE
    root.mkdir(parents=True)
    (root / "index.html").write_text("<script>alert(1)</script><form><input></form>", encoding="utf-8")
    put(ctx, "phase3_step6_content_review", {"issues": [], "verdict": "ok"})
    put(ctx, "phase3_step3_build", {"files": [{"path": "index.html"}], "notes": ""})
    m = phase3.measure(ctx)
    assert m["deployed"] == 0 and m["honesty_must_fix"] >= 2
    m["acceptance_pass_ratio"] = 1.0
    m["site_checks_passed"] = 1  # isolate the honesty rule
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, m, 0).outcome == "repeat"


def test_unsafe_manifest_path_counts_as_deployed(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase3_step3_build", {"files": [{"path": "../../public/index.html"}], "notes": ""})
    assert phase3.measure(ctx)["deployed"] == 1
