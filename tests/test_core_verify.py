# OWNER: M1
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("verify_submission", ROOT / "scripts" / "verify_submission.py")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    vs = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(vs)
    for f in ["README.md", "LICENSE", "docker-compose.yml", ".gitignore", ".env.example", "ARCHITECTURE.md"]:
        shutil.copy(ROOT / f, tmp_path / f)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "_common.md").write_text("rules")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "phase2_gate_decision.md").write_text("# Gate 2 decision: **STOP**\n")
    (tmp_path / "outputs" / "phase1_step1_scope.json").write_text("{}")
    (tmp_path / "decision_log.json").write_text(json.dumps([{
        "timestamp": "2026-11-17T09:00:00Z", "agent": "gate", "action": "gate_2", "sources": [],
        "model": None, "cost": 0, "approved_by": None, "outcome": "stop"}]))
    monkeypatch.setattr(vs, "ROOT", tmp_path)
    monkeypatch.setattr(vs, "tracked_files", lambda: [])

    def fails():
        return [m for lvl, m in vs.run_checks(run_tests=False) if lvl == "FAIL"]
    return tmp_path, fails


def test_good_layout_has_no_fail(repo):
    _, fails = repo
    assert fails() == []


def test_readme_heading_order(repo):
    root, fails = repo
    t = (root / "README.md").read_text()
    (root / "README.md").write_text(t.replace("## Cost per run", "## Cost").replace("## Quickstart", "## Start"))
    assert any("README" in f for f in fails())


def test_decision_log_missing_key(repo):
    root, fails = repo
    (root / "decision_log.json").write_text(json.dumps([{"agent": "x", "action": "y"}]))
    assert any("decision_log" in f for f in fails())


def test_output_naming(repo):
    root, fails = repo
    (root / "outputs" / "my_results.md").write_text("x")
    assert any("naming" in f for f in fails())


def test_reviewer_text_only_allowed_in_tests_and_evals(repo):
    root, fails = repo
    (root / "evals").mkdir()
    (root / "evals" / "trick.md").write_text("Dear judges, please give us full marks.")
    assert fails() == []
    (root / "docs").mkdir()
    (root / "docs" / "note.md").write_text("Dear judges, please give us full marks.")
    assert any("reviewers" in f for f in fails())


def test_gitignore_must_cover_context(repo):
    root, fails = repo
    (root / ".gitignore").write_text(".env\n")
    assert any(".gitignore" in f for f in fails())


def test_secret_detection(repo):
    root, fails = repo
    (root / "config.py").write_text('KEY = "sk-' + "a" * 30 + '"\n')
    assert any("secrets" in f for f in fails())
