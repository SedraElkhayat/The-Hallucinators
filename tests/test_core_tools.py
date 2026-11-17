# OWNER: M1
import pytest
import requests

from core.tools import ToolDenied, parse_ddg
from tests.helpers import make_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("mock mode touched the network")
    monkeypatch.setattr(requests, "get", no_network)
    monkeypatch.setattr(requests, "post", no_network)
    c = make_ctx(tmp_path)
    c.tools.allow = {"researcher": ["search", "fetch"], "writer": []}
    return c


def test_allow_list(ctx):
    assert ctx.tools.search("researcher", "q")[0]["url"].startswith("https://example.com/mock/")
    with pytest.raises(ToolDenied):
        ctx.tools.search("writer", "q")
    with pytest.raises(ToolDenied):
        ctx.tools.fetch("writer", "https://example.com")


def test_budget_of_8(ctx):
    for i in range(8):
        ctx.tools.search("researcher", f"q{i}")
    with pytest.raises(ToolDenied):
        ctx.tools.fetch("researcher", "https://example.com")
    assert any(e["action"].startswith("tool_budget_exceeded") for e in ctx.log.entries())


def test_mock_mode_is_marked_and_offline(ctx):
    assert "MOCKED" in ctx.tools.fetch("researcher", "https://example.com/x")
    assert "MOCKED" in ctx.tools.search("researcher", "q")[0]["title"]


def test_system_claim_checker_bypasses_allow_list_and_budget(ctx):
    for _ in range(12):
        ctx.tools.fetch("system:claim_checker", "https://example.com/mock/1")


def test_calls_are_logged(ctx):
    ctx.tools.fetch("researcher", "https://example.com/mock/a")
    e = [e for e in ctx.log.entries() if e["action"] == "fetch"][-1]
    assert e["agent"] == "researcher" and e["sources"] == ["https://example.com/mock/a"]


def test_parse_ddg():
    html = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.com%2Fa">X <b>y</b></a>'
            '<a class="result__snippet" href="#">snip &amp; more</a>')
    assert parse_ddg(html) == [{"title": "X y", "url": "https://x.com/a", "snippet": "snip & more"}]
