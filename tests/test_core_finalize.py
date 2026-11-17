# OWNER: M1
"""finalize_outputs: the main run is copied unchanged; a weak run adds only its gate files and tagged log."""
import json

from scripts.finalize_outputs import main


def _run(path, files, log):
    (path / "outputs").mkdir(parents=True)
    for name, text in files.items():
        (path / "outputs" / name).write_text(text, encoding="utf-8")
    (path / "decision_log.json").write_text(json.dumps(log), encoding="utf-8")
    return path


def test_weak_run_gate_files_and_log_are_added(tmp_path):
    e = {"timestamp": "t", "agent": "gate", "action": "evidence_gate", "sources": [], "model": None,
         "cost": 0, "approved_by": None}
    strong = _run(tmp_path / "s", {"phase1_gate_decision.md": "GO", "phase1_step1_scope.md": "x"}, [e])
    weak = _run(tmp_path / "w", {"phase1_gate_decision.md": "STOP", "phase1_gate_criteria.json": "{}",
                                 "phase1_step1_scope.md": "y"}, [{**e, "outcome": "stop"}])
    root = tmp_path / "repo"
    root.mkdir()
    assert main(str(strong), str(weak), root=root) == 0
    out = root / "outputs"
    assert sorted(p.name for p in out.iterdir()) == sorted(["phase1_gate_decision.md", "phase1_step1_scope.md",
                                                            "phase1_gate_weak_criteria.json",
                                                            "phase1_gate_weak_decision.md"])
    assert (out / "phase1_gate_weak_decision.md").read_text() == "STOP"
    assert (out / "phase1_gate_decision.md").read_text() == "GO"
    log = json.loads((root / "decision_log.json").read_text())
    assert [x["run"] for x in log] == ["strong", "weak"] and log[1]["outcome"] == "stop"


def test_single_run_copies_log_unchanged(tmp_path):
    strong = _run(tmp_path / "s", {"phase1_gate_decision.md": "GO"}, [{"action": "a"}])
    root = tmp_path / "repo"
    root.mkdir()
    assert main(str(strong), root=root) == 0
    assert json.loads((root / "decision_log.json").read_text()) == [{"action": "a"}]
