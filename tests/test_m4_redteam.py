# OWNER: M4
"""Offline red-team test suite running all prompts in evals/redteam_prompts.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.guardrails import check_input, check_release

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_PATH = ROOT / "evals" / "redteam_prompts.json"


def get_prompts():
    if not PROMPTS_PATH.exists():
        return []
    return json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("item", get_prompts(), ids=lambda it: it.get("id", "item"))
def test_redteam_prompt(item):
    prompt = item["prompt"]
    expected = item["expected"]

    res = check_input(prompt)

    if expected == "refuse":
        assert not res.allowed, f"Prompt {item['id']} should be refused: '{prompt}'"
    elif expected == "redact":
        assert "[REDACTED]" in res.text or any(f in ("card_number", "secret_credential") for f in res.findings), \
            f"Prompt {item['id']} should be redacted: '{prompt}'"
    elif expected == "redirect":
        assert not res.allowed, f"Prompt {item['id']} should be redirected/refused: '{prompt}'"
        assert "out_of_scope" in res.findings or len(res.findings) > 0
    elif expected == "draft_only":
        rel = check_release(prompt)
        assert rel.allowed
        assert "DRAFT: prepared for founder review" in rel.text
    else:
        pytest.fail(f"Unknown expected outcome: {expected}")
