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
