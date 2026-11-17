# OWNER: M1
import json

from core.llm import MockLLM, RealClient, make_client, parse_json


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def test_make_client():
    assert isinstance(make_client(True), MockLLM)
    assert isinstance(make_client(False), RealClient)


def test_fixture_is_used(tmp_path):
    (tmp_path / "my_agent.json").write_text(json.dumps({"summary": "MOCKED summary"}))
    r = MockLLM(fixture_dir=tmp_path).chat("s", "u", agent="my_agent")
    assert r.data["summary"] == "MOCKED summary" and r.cost == 0.0 and r.model == "mock-llm"
    assert "MOCKED" in r.text


def test_placeholder_without_fixture_is_deterministic_and_marked(tmp_path, monkeypatch):
    m = MockLLM(fixture_dir=tmp_path)
    monkeypatch.setattr(m, "_required_keys", lambda agent: ["summary", "claims", "findings"])
    a, b = m.chat("s", "u", agent="x"), m.chat("s", "u", agent="x")
    assert a.text == b.text
    assert set(["summary", "claims", "findings"]) <= set(a.data)
    assert all("MOCKED" in s for s in _strings(a.data["summary"]))
    assert all("MOCKED" in s or s.startswith("https://example.com/mock/") for s in _strings(a.data["claims"]))


def test_parse_json_tolerant():
    assert parse_json('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('noise {"b": 2} noise') == {"b": 2}
    assert parse_json("not json") is None


class _Resp:
    status_code, headers, text = 200, {}, ""

    def __init__(self, content):
        self._c = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}


def _capture(monkeypatch, content='<think>\n\n</think>\n{"ok": true}'):
    import requests
    sent = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        sent.update(url=url, body=json)
        return _Resp(content)
    monkeypatch.setattr(requests, "post", fake_post)
    return sent


def test_real_client_turns_qwen3_thinking_off_and_parses(monkeypatch):
    monkeypatch.delenv("LLM_NO_THINK", raising=False)
    sent = _capture(monkeypatch)
    r = RealClient(base_url="http://x/v1", model="qwen3:8b").chat("SYS", "USER", agent="a")
    assert sent["url"] == "http://x/v1/chat/completions"
    assert sent["body"]["messages"][0]["content"].endswith("/no_think")
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert r.data == {"ok": True} and (r.tokens_in, r.tokens_out, r.cost) == (7, 3, 0.0)


def test_real_client_leaves_other_models_alone(monkeypatch):
    monkeypatch.delenv("LLM_NO_THINK", raising=False)
    sent = _capture(monkeypatch, '{"ok": true}')
    RealClient(base_url="http://x/v1", model="gpt-oss:20b").chat("SYS", "USER", agent="a")
    assert sent["body"]["messages"][0]["content"] == "SYS"
    monkeypatch.setenv("LLM_NO_THINK", "false")
    sent = _capture(monkeypatch)
    RealClient(base_url="http://x/v1", model="qwen3:8b").chat("SYS", "USER", agent="a")
    assert sent["body"]["messages"][0]["content"] == "SYS"


def test_real_client_default_timeout_allows_slow_cpu(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    assert RealClient(base_url="http://x/v1").timeout == 900
    monkeypatch.setenv("LLM_TIMEOUT", "120")
    assert RealClient(base_url="http://x/v1").timeout == 120


class _R:
    def __init__(self, status, content='{"ok": true}', headers=None, text=""):
        self.status_code, self.headers, self.text, self._c = status, headers or {}, text, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}


def _sequence(monkeypatch, responses):
    import time as _time
    import requests
    calls, waits = [], []
    it = iter(responses)
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None, headers=None: (calls.append(json), next(it))[1])
    monkeypatch.setattr(_time, "sleep", lambda s: waits.append(s))
    return calls, waits


def test_rate_limit_waits_and_retries(monkeypatch):
    calls, waits = _sequence(monkeypatch, [_R(429, headers={"retry-after": "7"}), _R(503), _R(200)])
    r = RealClient(base_url="http://x/v1", model="openai/gpt-oss-120b").chat("S", "U", agent="a")
    assert r.data == {"ok": True} and len(calls) == 3
    assert waits[0] == 7.0 and waits[1] >= 1.0


def test_rate_limit_gives_up_after_retries(monkeypatch):
    monkeypatch.setenv("LLM_RETRIES", "2")
    _sequence(monkeypatch, [_R(429), _R(429), _R(429)])
    import pytest
    with pytest.raises(RuntimeError):
        RealClient(base_url="http://x/v1", model="m").chat("S", "U", agent="a")


def test_json_mode_rejected_falls_back_to_plain_text(monkeypatch):
    calls, _ = _sequence(monkeypatch, [_R(400, text="response_format is not supported"), _R(200, 'Here: {"ok": true}')])
    c = RealClient(base_url="http://x/v1", model="m")
    assert c.chat("S", "U", agent="a").data == {"ok": True}
    assert "response_format" in calls[0] and "response_format" not in calls[1] and c.json_mode_supported is False


def test_reasoning_effort_only_when_set(monkeypatch):
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    calls, _ = _sequence(monkeypatch, [_R(200), _R(200)])
    RealClient(base_url="http://x/v1", model="m").chat("S", "U", agent="a")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    RealClient(base_url="http://x/v1", model="openai/gpt-oss-120b").chat("S", "U", agent="a")
    assert "reasoning_effort" not in calls[0] and calls[1]["reasoning_effort"] == "low"
