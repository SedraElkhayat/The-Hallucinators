# OWNER: M1
"""End-to-end mocked run: all six phases with MockLLM and the scripted demo founder."""
import json

import orchestrator
from agents import all_agents
from phases import load_phase
from tests.helpers import assert_log_keys, make_ctx


def test_e2e_mock_runs_all_phases(tmp_path):
    ctx = make_ctx(tmp_path, brief=(orchestrator.ROOT / "demo" / "brief_strong.md").read_text())
    result = orchestrator.run(ctx, through=6)
    assert result["outcome"] in {"go", "repeat", "pivot", "stop"}
    out = ctx.out_dir
    # every phase that ran wrote its criteria and a gate decision
    for phase, _, _ in result["history"]:
        assert (out / f"phase{phase}_gate_criteria.json").exists()
        assert (out / f"phase{phase}_gate_decision.md").exists()
    # every registered agent of every phase that went 'go' produced its artifact
    registered = all_agents()
    for phase, _, outcome in result["history"]:
        mod = load_phase(phase)
        for stage in mod.STAGES:
            for name in stage:
                if name in registered and outcome == "go":
                    assert ctx.store.has(registered[name].step), f"{name} artifact missing"
    entries = json.loads(ctx.log.path.read_text())
    assert entries
    assert_log_keys(entries)
    # nothing outward-facing without approval: every 'released' entry must be founder-approved
    for e in entries:
        if e["action"].startswith("released"):
            assert e["approved_by"] == "founder"
    assert any(e["action"] == "run_finished" for e in entries)
