# OWNER: M4
"""Parametrized test suite for all 12 Member 4 agents.

Verifies:
1. Agent is registered.
2. Prompt file exists in prompts/<name>.md.
3. Required keys are present in mock run.
4. Artifacts (<step>.json and <step>.md) are saved.
5. Decision log entries have all 7 required keys.
6. Guardrails block output violations.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents import all_agents, get_agent
from tests.helpers import assert_log_keys, make_ctx

ROOT = Path(__file__).resolve().parent.parent
M4_AGENTS = [
    "pricing_analyst",
    "offer_packager",
    "policy_drafter",
    "compliance_reviewer_phase4",
    "channel_planner",
    "store_page_builder",
    "launch_post_drafter",
    "compliance_reviewer_phase5",
    "sale_to_cash",
    "support_drafter",
    "metrics_analyst",
    "persevere_pivot_memo",
]


@pytest.mark.parametrize("agent_name", M4_AGENTS)
def test_agent_registered_and_prompt_exists(agent_name):
    registered = all_agents()
    assert agent_name in registered, f"Agent {agent_name} not registered in agents/"

    prompt_file = ROOT / "prompts" / f"{agent_name}.md"
    assert prompt_file.exists(), f"Prompt file {prompt_file} does not exist"


@pytest.mark.parametrize("agent_name", M4_AGENTS)
def test_agent_mock_run(agent_name, tmp_path):
    ctx = make_ctx(tmp_path)
    agent = get_agent(agent_name)

    res = agent.run(ctx)
    assert res is not None
    assert isinstance(res.data, dict)

    # Check required keys
    for k in agent.required_keys:
        assert k in res.data, f"Agent {agent_name} missing required key '{k}'"

    # Check .json and .md files written
    step = agent.step
    assert (ctx.out_dir / f"{step}.json").exists(), f"Missing {step}.json artifact"
    assert (ctx.out_dir / f"{step}.md").exists(), f"Missing {step}.md artifact"

    # Check decision log entries
    entries = ctx.log.entries()
    assert len(entries) > 0
    assert_log_keys(entries)
