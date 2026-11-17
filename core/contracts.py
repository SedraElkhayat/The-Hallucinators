# OWNER: M1
"""Frozen shared contracts. Changes only via M1 (see team chat)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DECISION_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")


@dataclass
class AgentResult:
    data: dict
    markdown: str
    sources: list[str] = field(default_factory=list)
    model: Optional[str] = None
    cost: float = 0.0
    mocked: bool = False


@dataclass
class LLMResponse:
    text: str
    data: Optional[dict]
    model: str
    tokens_in: int
    tokens_out: int
    cost: float


@dataclass
class Context:
    brief: str
    out_dir: Path
    store: Any          # core.artifacts.ArtifactStore
    llm: Any            # core.llm.LLMClient
    tools: Any          # core.tools.ToolBroker
    log: Any            # core.decision_log.DecisionLog
    approvals: Any      # approval.Approvals
    founder: Any        # core.founder.FounderInput
    mock: bool = False
    extra: dict = field(default_factory=dict)
