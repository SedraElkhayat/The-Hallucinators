# OWNER: M1
"""LLM clients: a real OpenAI-compatible client (Ollama by default) and a deterministic MockLLM."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import requests

from core import cost as cost_mod
from core.contracts import LLMResponse

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mock"
MOCK_MARKER = "MOCKED"


def parse_json(text: str) -> Optional[dict]:
    """Best-effort JSON extraction (strips <think> blocks and code fences)."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


class LLMClient:
    """Interface (CONTEXT.md section 4). RealClient and MockLLM implement it."""

    def chat(self, system: str, user: str, agent: str, json_mode: bool = True) -> LLMResponse:
        raise NotImplementedError


class RealClient(LLMClient):
    """OpenAI-compatible chat endpoint (Ollama exposes /v1). Local open-weight model: cost 0.0."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 api_key: Optional[str] = None, timeout: int = 300):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://ollama:11434/v1")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "qwen3:8b")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "ollama")
        self.timeout = int(os.getenv("LLM_TIMEOUT", timeout))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1500"))
        # qwen3 "thinks" before answering by default; the thinking can use the whole token budget
        # and leave no JSON. "auto" turns thinking off for qwen3 models with the documented /no_think switch.
        self.no_think = os.getenv("LLM_NO_THINK", "auto").strip().lower()

    def thinking_off(self) -> bool:
        if self.no_think in ("1", "true", "yes", "on"):
            return True
        return self.no_think == "auto" and "qwen3" in self.model.lower()

    def chat(self, system: str, user: str, agent: str, json_mode: bool = True) -> LLMResponse:
        if self.thinking_off():
            system = f"{system}\n\n/no_think"
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                          headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        payload = r.json()
        text = payload["choices"][0]["message"].get("content") or ""
        usage = payload.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        c = cost_mod.compute(self.model, tin, tout)  # 0.0 for local models
        return LLMResponse(text=text, data=parse_json(text) if json_mode else None,
                           model=self.model, tokens_in=tin, tokens_out=tout, cost=c)


def _placeholder(key: str):
    """A schema-shaped placeholder for a required key. Always marked MOCKED."""
    k = key.lower()
    if k == "claims":
        return [{"claim": "MOCKED placeholder claim", "source_url": "https://example.com/mock/MOCKED",
                 "quote": "MOCKED placeholder claim", "verified": None, "assumption": False}]
    if k in ("insufficient_evidence",):
        return True
    if k in ("rating",):
        return "unknown"
    if k in ("verdict",):
        return "ok"
    if k in ("confidence",):
        return "low"
    if k in ("issues", "risks", "kill_criteria", "findings", "assumptions", "limitations",
             "would_change_mind", "hypotheses", "ranked", "competitors", "results", "reasons",
             "experiments", "evidence_refs", "documents", "acceptance_tests", "mvp_scope"):
        return []
    return f"{MOCK_MARKER} placeholder for {key}"


class MockLLM(LLMClient):
    """Deterministic, offline. Reads tests/fixtures/mock/<agent>.json, else builds a placeholder."""

    def __init__(self, fixture_dir: Optional[Path] = None):
        self.base_url = None
        self.fixture_dir = Path(fixture_dir) if fixture_dir else FIXTURE_DIR
        self.model = "mock-llm"

    def _required_keys(self, agent: str) -> list[str]:
        try:
            from agents import get_agent
            return list(get_agent(agent).required_keys)
        except Exception:
            return []

    def chat(self, system: str, user: str, agent: str, json_mode: bool = True) -> LLMResponse:
        fixture = self.fixture_dir / f"{agent}.json"
        if fixture.exists():
            data = json.loads(fixture.read_text(encoding="utf-8"))
        else:
            data = {k: _placeholder(k) for k in self._required_keys(agent)}
        data.setdefault("mocked", True)
        data.setdefault("_marker", MOCK_MARKER)
        text = json.dumps(data, ensure_ascii=False)
        return LLMResponse(text=text, data=data if json_mode else None, model="mock-llm",
                           tokens_in=0, tokens_out=0, cost=0.0)


def make_client(mock: bool) -> LLMClient:
    return MockLLM() if mock else RealClient()
