# OWNER: M2
"""gates.py: every outcome, severity order, repeat exhaustion, missing metrics, pre-registration, and the
Phase 2 demand tiers (ratio 1.0 go, 0.7 repeat, 0.3 pivot, 0.12 stop)."""
import hashlib
import json

import pytest

import gates
from gates import Check
from tests.test_m2_helpers import ctx_for

DEMAND = [Check("demand_floor", "demand_ratio", ">=", 0.2, "stop"),
          Check("demand_pivot", "demand_ratio", ">=", 0.5, "pivot"),
          Check("demand_target", "demand_ratio", ">=", 1.0, "repeat")]


def run_gate(tmp_path, checks, metrics, attempt=0, phase=2):
    ctx = ctx_for(tmp_path)
    gates.preregister(ctx, phase, checks)
    return ctx, gates.evaluate(ctx, phase, metrics, attempt=attempt)


@pytest.mark.parametrize("ratio,outcome", [(1.0, "go"), (1.4, "go"), (0.7, "repeat"), (0.3, "pivot"),
                                           (0.12, "stop")])
def test_demand_tiers(tmp_path, ratio, outcome):
    ctx, res = run_gate(tmp_path, DEMAND, {"demand_ratio": ratio})
    assert res.outcome == outcome
    text = (ctx.out_dir / "phase2_gate_decision.md").read_text(encoding="utf-8")
    assert outcome.upper() in text


def test_0_12_writes_honest_stop_file(tmp_path):
    ctx, res = run_gate(tmp_path, DEMAND, {"demand_ratio": 0.12})
    text = (ctx.out_dir / "phase2_gate_decision.md").read_text(encoding="utf-8")
    assert "STOP" in text and "What would change this verdict" in text and "0.12" in text
    assert "founder approves or overrides" in text
    entry = [e for e in ctx.log.entries() if e["action"] == "gate_2"][-1]
    assert entry["outcome"] == "stop" and entry["agent"] == "gate"


def test_severity_stop_beats_pivot_beats_repeat(tmp_path):
    checks = [Check("r", "a", ">=", 1, "repeat"), Check("p", "b", ">=", 1, "pivot"), Check("s", "c", ">=", 1, "stop")]
    assert run_gate(tmp_path / "1", checks, {"a": 0, "b": 0, "c": 0})[1].outcome == "stop"
    assert run_gate(tmp_path / "2", checks, {"a": 0, "b": 0, "c": 1})[1].outcome == "pivot"
    assert run_gate(tmp_path / "3", checks, {"a": 0, "b": 1, "c": 1})[1].outcome == "repeat"
    assert run_gate(tmp_path / "4", checks, {"a": 1, "b": 1, "c": 1})[1].outcome == "go"


def test_missing_metric_fails_its_check(tmp_path):
    _, res = run_gate(tmp_path, [Check("x", "present", "==", 1, "pivot")], {})
    assert res.outcome == "pivot" and "missing" in res.reasons[0]


def test_repeat_budget_exhausted_becomes_stop(tmp_path):
    checks = [Check("r", "a", ">=", 1, "repeat")]
    assert run_gate(tmp_path / "1", checks, {"a": 0}, attempt=0)[1].outcome == "repeat"
    res = run_gate(tmp_path / "2", checks, {"a": 0}, attempt=1)[1]
    assert res.outcome == "stop" and "repeat budget exhausted" in res.reasons[-1]


def test_criteria_written_and_hashed_before_evaluation(tmp_path):
    ctx = ctx_for(tmp_path)
    checks = [Check("r", "a", ">=", 1, "repeat")]
    digest = gates.preregister(ctx, 3, checks)
    path = ctx.out_dir / "phase3_gate_criteria.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = json.dumps({"phase": 3, "checks": payload["checks"]}, indent=2, sort_keys=True)
    assert payload["sha256"] == digest == hashlib.sha256(body.encode()).hexdigest()
    actions = [e["action"] for e in ctx.log.entries()]
    assert "preregister_gate_3" in actions and "gate_3" not in actions
    gates.evaluate(ctx, 3, {"a": 1}, attempt=0)
    actions = [e["action"] for e in ctx.log.entries()]
    assert actions.index("preregister_gate_3") < actions.index("gate_3")
    assert digest in (ctx.out_dir / "phase3_gate_decision.md").read_text(encoding="utf-8")


def test_changed_criteria_after_preregistration_are_refused(tmp_path):
    ctx = ctx_for(tmp_path)
    gates.preregister(ctx, 1, [Check("r", "a", ">=", 1, "repeat")])
    ctx.extra["_gate_checks"][1] = [Check("r", "a", ">=", 0, "repeat")]  # moving the goalposts
    with pytest.raises(RuntimeError):
        gates.evaluate(ctx, 1, {"a": 0}, attempt=0)


def test_halt_reason_is_reported(tmp_path):
    ctx = ctx_for(tmp_path)
    gates.preregister(ctx, 1, [Check("s", "scope_ok", "==", 1, "stop")])
    ctx.extra["halt_phase"] = "product is out of scope (physical_goods)"
    res = gates.evaluate(ctx, 1, {}, attempt=0)
    assert res.outcome == "stop" and res.reasons[0].startswith("phase halted early")


def test_bad_check_definitions_are_rejected():
    with pytest.raises(ValueError):
        Check("x", "m", "=>", 1, "stop")
    with pytest.raises(ValueError):
        Check("x", "m", ">=", 1, "maybe")
