# OWNER: M1
import json

import pytest

from agents import all_agents
from agents.base import Agent
from core.llm import MockLLM
from tests.helpers import DECISION_KEYS, make_ctx


class _Echo(Agent):
    name = ""  # test-only, never registered
    phase, step, required_keys = 1, "phase1_step0_echo", ["summary", "claims"]

    def system_prompt(self):
        return "test"


def _run(tmp_path, data, name="echo_test"):
    ctx = make_ctx(tmp_path)
    (tmp_path / "fx").mkdir(exist_ok=True)
    (tmp_path / "fx" / f"{name}.json").write_text(json.dumps(data))
    ctx.llm = MockLLM(fixture_dir=tmp_path / "fx")
    a = _Echo()
    a.name = name
    return ctx, a


def test_run_writes_artifact_and_one_log_entry(tmp_path):
    ctx, a = _run(tmp_path, {"summary": "MOCKED ok", "claims": [
        {"claim": "c", "source_url": "https://example.com/mock/1", "quote": "c", "verified": None, "assumption": False}]})
    res = a.run(ctx)
    assert res.mocked and res.data["claims"][0]["verified"] is True
    assert (ctx.out_dir / "phase1_step0_echo.json").exists()
    assert "MOCKED" in (ctx.out_dir / "phase1_step0_echo.md").read_text()
    entries = [e for e in ctx.log.entries() if e["agent"] == "echo_test"]
    assert [e["action"] for e in entries] == ["run_echo_test"]
    assert all(k in entries[0] for k in DECISION_KEYS)


def test_guardrail_block_is_dropped_and_logged(tmp_path):
    ctx, a = _run(tmp_path, {"summary": "We guarantee you will earn money.", "claims": []}, "echo_bad")
    res = a.run(ctx)
    assert res.data["summary"].startswith("[BLOCKED by guardrails]")
    assert any(e["action"] == "guardrail_drop" for e in ctx.log.entries())


def test_missing_keys_raise_after_retries(tmp_path):
    ctx, a = _run(tmp_path, {"summary": "MOCKED only"}, "echo_missing")
    with pytest.raises(ValueError):
        a.run(ctx)


def test_registry_has_no_name_clashes():
    agents = all_agents()
    assert all(cls.name == name for name, cls in agents.items())
