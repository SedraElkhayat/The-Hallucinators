"""Smoke tests: the pipeline steps, the gate, and that nothing goes out without founder approval.

Offline (MockLLM, mocked search, scripted founder); run with `python -m pytest -q tests/test_smoke.py`.
The detailed tests live in the other tests/test_*.py files.
"""
import json

import pytest

import orchestrator
from approval import Approvals, NotApproved
from core.decision_log import DecisionLog
from core.founder import ScriptedInputs
from tests.helpers import assert_log_keys, make_ctx
from tests.test_m3_helpers import make_ctx as make_phase2_ctx
from tests.test_m3_phase2 import _artifacts, _gate

ROOT = orchestrator.ROOT


def test_smoke_pipeline_runs_all_six_phases_offline(tmp_path):
    """The strong demo brief goes through all six phases with the mock model; each phase leaves its gate files,
    the sale-to-cash log is written, and every decision-log entry has the required keys."""
    ctx = make_ctx(tmp_path, brief=(ROOT / "demo" / "brief_strong.md").read_text(encoding="utf-8"),
                   founder_inputs=ROOT / "demo" / "founder_inputs.json")
    result = orchestrator.run(ctx, through=6)
    phases = sorted({h[0] for h in result["history"]})
    assert phases == [1, 2, 3, 4, 5, 6]
    for n in phases:
        assert (ctx.out_dir / f"phase{n}_gate_criteria.json").exists()
        assert (ctx.out_dir / f"phase{n}_gate_decision.md").exists()
    assert (ctx.out_dir / "payment_test_log.md").exists()
    entries = json.loads(ctx.log.path.read_text(encoding="utf-8"))
    assert_log_keys(entries)
    assert all(e["approved_by"] in (None, "founder") for e in entries)


@pytest.mark.parametrize("signups,expected", [(100, "go"), (12, "stop")])
def test_smoke_gate_uses_the_preset_demand_target(tmp_path, signups, expected):
    """Target fixed before the evidence: 100 sign-ups in 14 days. 12 arrive -> the gate recommends STOP."""
    ctx = make_phase2_ctx(tmp_path)
    _artifacts(ctx, signups=signups, target=100)
    result = _gate(ctx)
    assert result.outcome == expected
    assert (ctx.out_dir / "phase2_gate_decision.md").exists()


def _approvals(tmp_path, answer: str):
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"approvals": {"default": answer}}), encoding="utf-8")
    log = DecisionLog(tmp_path / "log.json")
    return Approvals("scripted", log, scripted=ScriptedInputs(inputs)), log


def test_smoke_nothing_goes_out_without_founder_approval(tmp_path):
    """A rejected item is never released, and the block is logged; an approved one is released with
    approved_by: founder."""
    approvals, log = _approvals(tmp_path, "reject")
    with pytest.raises(NotApproved):
        approvals.release("launch_post", "Launch post 1", "draft text", phase=5)
    actions = [e["action"] for e in log.entries()]
    assert "release_blocked:launch_post" in actions
    assert not any(a.startswith("released:") for a in actions)

    (tmp_path / "ok").mkdir()
    approvals, log = _approvals(tmp_path / "ok", "approve")
    assert approvals.release("launch_post", "Launch post 1", "draft text", phase=5) is True
    released = [e for e in log.entries() if e["action"] == "released:launch_post"]
    assert released and released[0]["approved_by"] == "founder"
