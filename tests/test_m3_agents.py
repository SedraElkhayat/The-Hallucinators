"""Every Phase 2 and 3 agent: registered, prompt exists, mock run writes valid artifacts and log entries,
and a guardrail violation in the model output never reaches the artifacts."""
import json
from pathlib import Path

import pytest

try:
    from test_m3_helpers import (M3_AGENTS, NON_LLM_AGENTS, REQUIRED_LOG_KEYS, ROOT, STEPS, ScriptedLLM,
                                 fixture, get_agent, log_entries, make_ctx)
except ImportError:  # tests/ is a package
    from tests.test_m3_helpers import (M3_AGENTS, NON_LLM_AGENTS, REQUIRED_LOG_KEYS, ROOT, STEPS, ScriptedLLM,
                                       fixture, get_agent, log_entries, make_ctx)

VIOLATION = " We guarantee 5-star results, a great idea."


def _seed_for(agent):
    return list(getattr(agent, "inputs", [])) + list(getattr(agent, "optional_inputs", []))


def _run(name, tmp_path, llm=None):
    agent = get_agent(name)
    ctx = make_ctx(tmp_path, llm=llm, seed=_seed_for(agent))
    if name == "qa_agent":  # QA needs built files: run the builder on the seeded spec first
        get_agent("builder").run(ctx)
    result = agent.run(ctx)
    return agent, ctx, result


@pytest.mark.parametrize("name", M3_AGENTS)
def test_registered_with_prompt_and_fixture(name):
    from agents import all_agents
    registry = all_agents()
    names = registry.keys() if isinstance(registry, dict) else [getattr(a, "name", a) for a in registry]
    assert name in names
    agent = get_agent(name)
    assert agent.name == name and agent.step == STEPS[name]
    assert agent.phase == (2 if STEPS[name].startswith("phase2") else 3)
    assert list(agent.tools) == []
    assert (ROOT / "prompts" / f"{name}.md").exists()
    assert (ROOT / "tests" / "fixtures" / "mock" / f"{name}.json").exists()
    assert (ROOT / "agents" / f"{name}.py").exists()


@pytest.mark.parametrize("name", M3_AGENTS)
def test_mock_run_writes_artifact_and_log(name, tmp_path):
    agent, ctx, result = _run(name, tmp_path)
    step = STEPS[name]
    out = Path(ctx.out_dir)
    assert (out / f"{step}.json").exists() and (out / f"{step}.md").exists()
    data = json.loads((out / f"{step}.json").read_text(encoding="utf-8"))
    for key in agent.required_keys:
        assert key in data, f"{name}: missing {key}"
    entries = log_entries(ctx)
    assert any(e.get("agent") == name for e in entries)
    for e in entries:
        for key in REQUIRED_LOG_KEYS:
            assert key in e, f"log entry {e} misses {key}"


def _inject(agent, data):
    """Append a violation to the longest string in the model output."""
    best = [None, None, -1]

    def walk(obj):
        items = obj.items() if isinstance(obj, dict) else enumerate(obj) if isinstance(obj, list) else []
        for k, v in items:
            if isinstance(v, str) and len(v) > best[2] and k != "path":
                best[:] = [obj, k, len(v)]
            elif isinstance(v, (dict, list)):
                walk(v)
    walk(data)
    if best[0] is not None:
        best[0][best[1]] += VIOLATION
    return data


@pytest.mark.parametrize("name", sorted(set(M3_AGENTS) - NON_LLM_AGENTS))
def test_guardrail_violation_is_blocked(name, tmp_path):
    agent = get_agent(name)
    ctx = make_ctx(tmp_path, llm=ScriptedLLM(transform=_inject), seed=_seed_for(agent))
    try:
        agent.run(ctx)
    except Exception:  # noqa: BLE001 - refusing the output entirely also blocks it
        pass
    out = Path(ctx.out_dir)
    for f in out.rglob("*"):
        if f.is_file() and not f.name.endswith("_gate_criteria.json"):
            text = f.read_text(encoding="utf-8", errors="replace").lower()
            assert "we guarantee 5-star" not in text, f"{name}: violation leaked into {f.name}"


def test_demand_results_invalid_input_becomes_mocked_zero(tmp_path):
    agent = get_agent("demand_results")
    ctx = make_ctx(tmp_path, founder_answers={"demand_results": "lots of people"},
                   seed=["phase2_step3_demand_test_plan"])
    result = agent.run(ctx)
    assert result.data["signups"] == 0 and result.data["provenance"] == "MOCKED"
    assert result.data["note"]
    assert ctx.founder.calls == ["demand_results", "demand_results"]  # asked again once
    md = (Path(ctx.out_dir) / "phase2_step5_demand_results.md").read_text(encoding="utf-8")
    assert md.splitlines()[0] == "PROVENANCE: MOCKED"


def test_demand_results_real_banner_and_ratio(tmp_path):
    agent = get_agent("demand_results")
    ctx = make_ctx(tmp_path, founder_answers={"demand_results": '{"signups": 70, "days": 14, "provenance": "REAL"}'},
                   seed=["phase2_step3_demand_test_plan"])
    result = agent.run(ctx)
    assert result.data["ratio"] == 0.7 and result.data["provenance"] == "REAL"
    md = (Path(ctx.out_dir) / "phase2_step5_demand_results.md").read_text(encoding="utf-8")
    assert md.startswith("PROVENANCE: REAL")


def test_qa_never_passes_without_files(tmp_path):
    agent = get_agent("qa_agent")
    ctx = make_ctx(tmp_path, seed=["phase3_step1_spec", "phase3_step3_build"])
    result = agent.run(ctx)  # no files were built
    assert result.data["pass_ratio"] == 0.0
    assert all(r["passed"] is False for r in result.data["results"])
