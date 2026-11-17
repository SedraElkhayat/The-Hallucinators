"""M3 prompts and model messages stay small: truncation, compact inputs, builder claims only, prompt format."""
import json
import re

import pytest

from agents.m3_common import MAX_ARTIFACT_CHARS, TRUNCATED, _clip, inputs_message
from tests.test_m3_helpers import M3_AGENTS, NON_LLM_AGENTS, ROOT, fixture, get_agent, make_ctx, put


def _data(message: str) -> dict:
    return json.loads(re.search(r"<data>\n(.*)\n</data>", message, re.S).group(1))


def test_clip_keeps_the_start_and_marks_truncation():
    small = {"a": "x" * 10}
    assert _clip(small) is small
    big = {"first": "START", "rest": "y" * (MAX_ARTIFACT_CHARS * 2)}
    out = _clip(big)
    assert isinstance(out, str) and out.startswith('{"first":"START"') and out.endswith(TRUNCATED)
    assert len(out) == MAX_ARTIFACT_CHARS + len(TRUNCATED)


def test_inputs_message_is_compact_drops_bookkeeping_and_keeps_honesty_flags(tmp_path):
    ctx = make_ctx(tmp_path)
    claim = {"claim": "c", "source_url": "https://example.com/mock/1", "quote": "q", "verified": True,
             "assumption": False, "check": "MOCKED: accepted", "fetch_error": None, "duplicate": True, "_x": 1}
    put(ctx, "phase1_step5_market", {"claims": [claim], "insufficient_evidence": False})
    msg = inputs_message(ctx, ["phase1_step5_market"])
    sent = _data(msg)["inputs"]["phase1_step5_market"]["claims"][0]
    assert sent == {"claim": "c", "source_url": "https://example.com/mock/1", "quote": "q", "verified": True,
                    "assumption": False}
    assert "\n " not in msg.split("<data>\n", 1)[1]  # no indentation inside the data block


def test_big_artifact_is_sent_truncated_from_the_start(tmp_path):
    ctx = make_ctx(tmp_path)
    put(ctx, "phase1_step5_market", {"claims": [], "notes": "BEGIN " + "z" * 10000})
    sent = _data(inputs_message(ctx, ["phase1_step5_market"]))["inputs"]["phase1_step5_market"]
    assert isinstance(sent, str) and sent.startswith('{"claims":[],"notes":"BEGIN') and sent.endswith(TRUNCATED)


def test_builder_sees_spec_copy_idea_card_and_only_verified_claims(tmp_path):
    agent = get_agent("builder")
    assert agent.inputs == ["phase3_step1_spec", "phase3_step2_page_copy"]
    assert agent.optional_inputs == ["phase1_step4_idea_card", "phase2_step1_competitor_analysis"]
    ctx = make_ctx(tmp_path, seed=agent.inputs + ["phase1_step4_idea_card", "phase2_step2_lean_canvas",
                                                  "phase1_step5_market"])
    analysis = fixture("competitor_analyst")
    analysis["claims"] = [
        {"claim": "V1", "source_url": "https://example.com/mock/1", "quote": "q1", "verified": True, "check": "x"},
        {"claim": "U1", "source_url": "https://example.com/mock/2", "quote": "q2", "verified": False}]
    put(ctx, "phase2_step1_competitor_analysis", analysis)
    data = _data(agent.build_user_message(ctx))
    assert set(data["inputs"]) == {"phase3_step1_spec", "phase3_step2_page_copy", "phase1_step4_idea_card"}
    assert data["verified_claims"] == [{"claim": "V1", "source_url": "https://example.com/mock/1", "quote": "q1"}]


def test_builder_sends_at_most_six_claims(tmp_path):
    agent = get_agent("builder")
    ctx = make_ctx(tmp_path, seed=agent.inputs)
    put(ctx, "phase2_step1_competitor_analysis", {"claims": [
        {"claim": f"C{i}", "source_url": f"https://example.com/mock/{i}", "quote": "q", "verified": True}
        for i in range(10)]})
    assert len(_data(agent.build_user_message(ctx))["verified_claims"]) == 6


LIMITS = {"landing_page_builder": 5, "risk_analyst": 5, "copywriter": 5, "user_docs_writer": 5,
          "spec_writer": 6, "validation_synthesizer": 6, "builder": 6, "critic_phase2": 6, "content_reviewer": 6,
          "competitor_analyst": 6, "assumption_auditor": 6, "scorecard_builder": 3}


@pytest.mark.parametrize("name", M3_AGENTS)
def test_prompt_keeps_format_example_and_length_rule(name):
    text = (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    assert text.startswith(f"# {name}\n")
    positions = [text.index(h) for h in ("## Role", "## Task", "## Inputs", "## Output", "## Rules")]
    assert positions == sorted(positions)
    example = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
    assert all(k in example for k in get_agent(name).required_keys)
    if name not in NON_LLM_AGENTS:
        rule = re.search(r"Keep every text value short \(one or two sentences\); no more than (\d+) items per list", text)
        assert rule, name
        if name in LIMITS:
            assert int(rule.group(1)) == LIMITS[name]


def test_specific_list_limits_are_stated():
    read = lambda n: (ROOT / "prompts" / f"{n}.md").read_text(encoding="utf-8")
    assert "features 5, faq 5, claims 6" in read("builder")
    assert "features 5, faq 5" in read("copywriter")
    assert "acceptance tests 6" in read("spec_writer")
    assert "findings 6" in read("validation_synthesizer")
    assert "risks 5" in read("risk_analyst")
