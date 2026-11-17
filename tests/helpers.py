# OWNER: M1
"""Shared test helpers. Use make_ctx(tmp_path) to get an offline, mocked Context."""
from __future__ import annotations

import json
from pathlib import Path

from orchestrator import build_context

ROOT = Path(__file__).resolve().parent.parent
DEMO_INPUTS = ROOT / "demo" / "founder_inputs.json"
DECISION_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")


def make_ctx(tmp_path: Path, brief: str = "SAMPLE brief: a Notion template pack for freelance designers.",
             founder_inputs: Path | dict | None = None):
    """Offline Context: MockLLM, mocked tools, scripted founder."""
    if isinstance(founder_inputs, dict):
        tmp_path.mkdir(parents=True, exist_ok=True)
        p = tmp_path / "founder_inputs.json"
        p.write_text(json.dumps(founder_inputs), encoding="utf-8")
        founder_inputs = p
    return build_context(brief, tmp_path / "outputs", tmp_path / "decision_log.json", mock=True,
                         founder_mode="scripted", founder_inputs=founder_inputs or DEMO_INPUTS)


def log_entries(ctx) -> list[dict]:
    return ctx.log.entries()


def assert_log_keys(entries: list[dict]) -> None:
    for e in entries:
        missing = [k for k in DECISION_KEYS if k not in e]
        assert not missing, f"decision log entry {e.get('action')} missing {missing}"
