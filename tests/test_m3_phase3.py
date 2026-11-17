"""Phase 3: builder sandbox rules, QA pass ratio, honesty counting, nothing deployed, Gate 3."""
from pathlib import Path

import pytest

import gates
from phases import phase3

from tests.test_m3_helpers import PHASE3_AGENTS, ScriptedLLM, fixture, get_agent, make_ctx, put

from agents.builder import check_file, validate_files
from agents.qa_agent import run_check


def test_stages_and_constants():
    assert phase3.PHASE == 3 and phase3.PIVOT_TO == 2
    assert [a for stage in phase3.STAGES for a in stage] == PHASE3_AGENTS
    assert {c.metric for c in phase3.gate_checks(None)} == {"acceptance_pass_ratio", "honesty_must_fix", "deployed"}


@pytest.mark.parametrize("path,content", [
    ("../escape.md", "# ok"),
    ("/etc/passwd.txt", "ok"),
    ("a/../../b.md", "ok"),
    ("C:/x.md", "ok"),
    ("run.py", "print(1)"),
    ("page.html", "<html><script>alert(1)</script></html>"),
    ("page.html", "<form action='/buy'><input name='x'></form>"),
    ("pay.md", "Enter your card number and CVV at checkout"),
    ("pay.md", "Pay with Stripe or PayPal"),
    ("p.html", '<img src="https://tracker.example/p.gif" width="1" height="1">'),
    ("t.md", "Testimonial: this kit changed my life"),
    ("big.md", "x" * 20001),
    ("empty.md", ""),
])
def test_builder_rejects_unsafe_files(path, content):
    _, reasons = check_file(path, content)
    assert reasons


def test_builder_accepts_clean_files_and_limits_count():
    files = [{"path": f"f{i}.md", "content": f"# File {i}"} for i in range(8)]
    accepted, rejected = validate_files(files)
    assert len(accepted) == 8 and not rejected  # the cap of 6 is applied when writing


def test_builder_run_writes_only_inside_sandbox(tmp_path):
    bad = {"files": [
        {"path": "index.html", "content": "<html><body><h1>Kit MOCKED</h1></body></html>"},
        {"path": "../outside.md", "content": "# escape"},
        {"path": "pay.html", "content": "<form>card number</form>"},
        *({"path": f"extra{i}.md", "content": f"# extra {i} MOCKED"} for i in range(7)),
    ], "notes": "MOCKED"}
    agent = get_agent("builder")
    llm = ScriptedLLM({"builder": bad})
    ctx = make_ctx(tmp_path, llm=llm, seed=agent.inputs)
    data = agent.run(ctx).data
    root = Path(ctx.out_dir) / "phase3_build"
    written = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert len(written) == 6 and "index.html" in written
    assert not (Path(ctx.out_dir) / "outside.md").exists() and not (tmp_path / "outside.md").exists()
    dropped = {d["path"] for d in data["dropped"]}
    assert {"../outside.md", "pay.html"} <= dropped
    assert llm.calls.count("builder") == 2  # one rewrite chance
    assert phase3.measure(ctx)["deployed"] == 0


def test_qa_pass_ratio(tmp_path):
    ctx = make_ctx(tmp_path)
    root = Path(ctx.out_dir) / "phase3_build"
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


def test_run_check_on_missing_build_dir(tmp_path):
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
    root = Path(ctx.out_dir) / "phase3_build"
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
    assert m == {"acceptance_pass_ratio": 1.0, "honesty_must_fix": 0, "deployed": 0}
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, m, 0).outcome == "go"
    assert (Path(ctx.out_dir) / "phase3_gate_decision.md").exists()


def test_gate3_failures(tmp_path):
    ctx = make_ctx(tmp_path)
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, {"acceptance_pass_ratio": 0.5, "honesty_must_fix": 0, "deployed": 0}, 0).outcome == "repeat"
    assert gates.evaluate(ctx, 3, {"acceptance_pass_ratio": 1.0, "honesty_must_fix": 0, "deployed": 1}, 0).outcome == "stop"


def test_script_or_form_is_honesty_repeat_not_deployed(tmp_path):
    ctx = make_ctx(tmp_path)
    root = Path(ctx.out_dir) / "phase3_build"
    root.mkdir(parents=True)
    (root / "index.html").write_text("<script>alert(1)</script><form><input></form>", encoding="utf-8")
    put(ctx, "phase3_step6_content_review", {"issues": [], "verdict": "ok"})
    put(ctx, "phase3_step3_build", {"files": [{"path": "index.html"}], "notes": ""})
    m = phase3.measure(ctx)
    assert m["deployed"] == 0 and m["honesty_must_fix"] >= 2
    m["acceptance_pass_ratio"] = 1.0
    gates.preregister(ctx, 3, phase3.gate_checks(ctx))
    assert gates.evaluate(ctx, 3, m, 0).outcome == "repeat"


def test_unsafe_manifest_path_counts_as_deployed(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase3_step3_build", {"files": [{"path": "../../public/index.html"}], "notes": ""})
    assert phase3.measure(ctx)["deployed"] == 1
