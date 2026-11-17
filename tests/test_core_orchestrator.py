# OWNER: M1
"""Orchestrator behaviour with tiny fake agents and fake phase modules (no network, no model)."""
import threading
import types

import pytest

import agents as agents_pkg
import orchestrator
from agents.base import Agent
from gates import Check
from tests.helpers import make_ctx

CALLS: list[str] = []


class Fake(Agent):
    kind = "code"
    barrier = None

    def run(self, ctx):
        if self.barrier is not None:
            self.barrier.wait()  # only passes if both agents of the stage run at the same time
        CALLS.append(self.name)
        n = CALLS.count(self.name)
        data = {"n": n}
        if self.name == "critic":
            data["verdict"] = "revise" if n == 1 else "ok"
        if self.name == "halter":
            ctx.extra["halt_phase"] = "scope check failed"
        return self.save(ctx, data, markdown=f"# {self.name}\n")


def _agent(name, **kw):
    return type(f"F_{name}", (Fake,), {"name": name, "phase": 1, "step": f"phase1_step9_{name}", **kw})


def _phase(n, stages, checks=(), measure=None, revise=None, pivot_to=None):
    return types.SimpleNamespace(PHASE=n, STAGES=stages, REVISE=revise, PIVOT_TO=pivot_to,
                                 gate_checks=lambda ctx: list(checks),
                                 measure=measure or (lambda ctx: {}))


@pytest.fixture
def env(tmp_path, monkeypatch):
    CALLS.clear()
    reg = dict(agents_pkg.all_agents())
    monkeypatch.setattr(agents_pkg, "_REGISTRY", reg)
    phases = {}
    monkeypatch.setattr(orchestrator, "load_phase", lambda n: phases[n])
    monkeypatch.setenv("ORCH_CONCURRENCY", "2")

    def add(*classes):
        for c in classes:
            reg[c.name] = c
    return make_ctx(tmp_path), phases, add


def test_stage_order_and_parallel_stage(env):
    ctx, phases, add = env
    barrier = threading.Barrier(2, timeout=5)
    add(_agent("a"), _agent("b", barrier=barrier), _agent("c", barrier=barrier), _agent("d"))
    phases[1] = _phase(1, [["a"], ["b", "c"], ["d"]])
    r = orchestrator.run(ctx, through=1)
    assert r["outcome"] == "go"
    assert CALLS[0] == "a" and set(CALLS[1:3]) == {"b", "c"} and CALLS[3] == "d"
    assert (ctx.out_dir / "phase1_gate_decision.md").exists()
    assert (ctx.out_dir / "phase1_gate_criteria.json").exists()


def test_revise_loop(env):
    ctx, phases, add = env
    add(_agent("producer"), _agent("critic"))
    phases[1] = _phase(1, [["producer"], ["critic"]], revise=("producer", "critic"))
    orchestrator.run(ctx, through=1)
    assert CALLS == ["producer", "critic", "producer", "critic"]
    assert any(e["action"] == "revise_round" for e in ctx.log.entries())


def test_repeat_once_then_go(env):
    ctx, phases, add = env
    add(_agent("a"))
    phases[1] = _phase(1, [["a"]], checks=[Check("ok", "runs", ">=", 2, "repeat")],
                       measure=lambda c: {"runs": CALLS.count("a")})
    r = orchestrator.run(ctx, through=1)
    assert [h[2] for h in r["history"]] == ["repeat", "go"]


def test_repeat_twice_becomes_stop(env):
    ctx, phases, add = env
    add(_agent("a"))
    phases[1] = _phase(1, [["a"]], checks=[Check("never", "x", ">=", 1, "repeat")])
    r = orchestrator.run(ctx, through=1)
    assert [h[2] for h in r["history"]] == ["repeat", "stop"] and r["outcome"] == "stop"


def test_pivot_writes_notes_and_returns(env):
    ctx, phases, add = env
    add(_agent("a"), _agent("b"))
    ctx.store.put("phase1_step7_opportunity_scores",
                  {"ranked": [{"name": "Idea A", "score": 7, "reasons": []},
                              {"name": "Idea B", "score": 6, "reasons": []}], "chosen": "Idea A"}, "", agent="t")
    phases[1] = _phase(1, [["a"]])
    phases[2] = _phase(2, [["b"]], checks=[Check("demand", "pivot_ok", "==", 1, "pivot")],
                       measure=lambda c: {"pivot_ok": 1 if c.store.has("pivot_notes") else 0}, pivot_to=1)
    r = orchestrator.run(ctx, through=2)
    assert [(h[0], h[2]) for h in r["history"]] == [(1, "go"), (2, "pivot"), (1, "go"), (2, "go")]
    notes = ctx.store.get("pivot_notes")
    assert notes["next_best_alternative"]["name"] == "Idea B"


def test_stop_ends_run_with_report(env):
    ctx, phases, add = env
    add(_agent("a"), _agent("b"))
    demand = [Check("d_stop", "demand_ratio", ">=", 0.2, "stop"), Check("d_pivot", "demand_ratio", ">=", 0.5, "pivot"),
              Check("d_repeat", "demand_ratio", ">=", 1.0, "repeat")]
    phases[1] = _phase(1, [["a"]], checks=demand, measure=lambda c: {"demand_ratio": 12 / 100})
    phases[2] = _phase(2, [["b"]])
    r = orchestrator.run(ctx, through=2)
    assert r["outcome"] == "stop" and "b" not in CALLS
    assert "STOP" in (ctx.out_dir / "phase1_gate_decision.md").read_text()
    assert (ctx.out_dir / "phase1_gate_final_report.md").exists()
    gate = [e for e in ctx.log.entries() if e["action"] == "gate_1"][0]
    assert gate["outcome"] == "stop"


def test_early_halt_skips_rest_of_phase(env):
    ctx, phases, add = env
    add(_agent("halter"), _agent("later"))
    phases[1] = _phase(1, [["halter"], ["later"]], checks=[Check("scope", "scope_ok", "==", 1, "stop")])
    r = orchestrator.run(ctx, through=1)
    assert CALLS == ["halter"] and r["outcome"] == "stop"
    assert "scope check failed" in (ctx.out_dir / "phase1_gate_decision.md").read_text()


def test_gate_rejection_uses_founder_override(env, tmp_path):
    ctx, phases, add = env
    ctx = make_ctx(tmp_path / "o", founder_inputs={"approvals": {"gate": "reject"}, "gate_override_1": "stop"})
    add(_agent("a"))
    phases[1] = _phase(1, [["a"]])
    r = orchestrator.run(ctx, through=1)
    assert r["outcome"] == "stop"
    e = [e for e in ctx.log.entries() if e["action"] == "gate_override_1"][0]
    assert e["approved_by"] == "founder" and e["system_outcome"] == "go"


def test_override_only_gate_1_and_visible_in_outputs(env, tmp_path):
    ctx, phases, add = env
    ctx = make_ctx(tmp_path / "o", founder_inputs={"approvals": {"default": "approve", "gate_1": "reject"},
                                                   "gate_override_1": "go",
                                                   "prefix_defaults": {"gate_override_": "stop"}})
    add(_agent("a"))
    add(_agent("b"))
    phases[1] = _phase(1, [["a"]])
    phases[2] = _phase(2, [["b"]])
    r = orchestrator.run(ctx, through=2)
    assert r["outcome"] == "go" and r["history"] == [(1, 0, "go"), (2, 0, "go")]
    acts = [e["action"] for e in ctx.log.entries()]
    assert "gate_override_1" in acts and "gate_override_2" not in acts
    text = (ctx.out_dir / "phase1_gate_founder_override.md").read_text()
    assert "chose **GO**" in text
    assert not (ctx.out_dir / "phase2_gate_founder_override.md").exists()
    assert "Gate 1: system GO, founder chose GO" in (ctx.out_dir / "phase2_gate_final_report.md").read_text()


def test_demo_inputs_override_gate_1_only():
    import json
    from core.founder import ScriptedInputs
    from tests.helpers import DEMO_INPUTS
    s = ScriptedInputs(DEMO_INPUTS)
    assert json.loads(DEMO_INPUTS.read_text())["gate_override_1"] == "go"
    assert s.approval("gate", 1) == "reject" and s.lookup("gate_override_1") == "go"
    assert all(s.approval("gate", n) == "approve" for n in range(2, 7))
    assert s.approval("page", 3) == "approve"
