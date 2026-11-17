# OWNER: M1
"""Real-mode search and fetch with a fake network: block detection, backend fallback, cache, budget."""
import base64

import pytest
import requests

from core import tools as T
from core.claims import quote_found
from core.tools import SearchBlocked, ToolBroker, ToolDenied, parse_bing, parse_hn


class Resp:
    def __init__(self, status=200, text="", data=None, ctype="text/html"):
        self.status_code, self.text, self._data = status, text, data
        self.headers = {"content-type": ctype}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class Log:
    def __init__(self):
        self.items = []

    def action(self, agent, action, sources=(), **extra):
        self.items.append(dict(agent=agent, action=action, sources=list(sources), **extra))

    def names(self):
        return [e["action"] for e in self.items]


DDG_BLOCKED = Resp(202, '<html><div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div></html>')
_ck = base64.urlsafe_b64encode(b"https://www.notion.com/templates/freelance").decode().rstrip("=")
BING_HTML = ('<ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1' + _ck +
             '&amp;ntb=1">Freelance <strong>templates</strong></a></h2>'
             '<div class="b_caption"><p>Templates for freelancers &amp; designers.</p></div></li>'
             '<li class="b_algo"><h2><a href="https://example.org/a">A</a></h2><p>s</p></li></ol>')
HN_DATA = {"hits": [
    {"objectID": "1", "title": "Show HN: Notion CRM", "url": "https://x.dev/crm", "story_text": None},
    {"objectID": "2", "title": None, "story_title": "Ask HN", "url": None,
     "comment_text": "I would <i>pay</i> for a client tracker."},
]}


def broker(tmp_path, monkeypatch, routes, backends="bing,hn,duckduckgo"):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        for key, resp in routes.items():
            if key in url:
                return resp(url) if callable(resp) else resp
        raise requests.ConnectionError(f"no route for {url}")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setenv("SEARCH_BACKENDS", backends)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    b = ToolBroker(Log(), cache_dir=tmp_path / "cache", allow={"scout": ["search", "fetch"]})
    return b, calls


def test_parse_bing_decodes_redirect_links():
    res = parse_bing(BING_HTML)
    assert res[0] == {"title": "Freelance templates", "url": "https://www.notion.com/templates/freelance",
                      "snippet": "Templates for freelancers & designers."}
    assert res[1]["url"] == "https://example.org/a"


def test_parse_hn_links_comments_to_item_page():
    res = parse_hn(HN_DATA)
    assert res[0]["url"] == "https://x.dev/crm"
    assert res[1]["url"] == "https://news.ycombinator.com/item?id=2"
    assert res[1]["snippet"] == "I would pay for a client tracker."


def test_ddg_202_is_an_error_not_zero_results(tmp_path, monkeypatch):
    b, _ = broker(tmp_path, monkeypatch, {"duckduckgo.com": DDG_BLOCKED}, backends="duckduckgo")
    with pytest.raises(SearchBlocked, match="202"):
        b.search("scout", "notion templates")
    assert "search_backend_failed" in b.log.names()
    assert not list((tmp_path / "cache").glob("search_*"))  # nothing cached


def test_fallback_to_next_backend_and_merge(tmp_path, monkeypatch):
    b, _ = broker(tmp_path, monkeypatch, {"bing.com": Resp(200, BING_HTML), "algolia": Resp(200, data=HN_DATA),
                                          "duckduckgo.com": DDG_BLOCKED})
    res = b.search("scout", "notion templates")
    assert [r["backend"] for r in res] == ["bing", "bing", "hn", "hn"]  # bing gave 2 < 3, HN tops up
    log = [e for e in b.log.items if e["action"] == "search"][-1]
    assert log["backends"] == ["bing", "hn"] and len(log["sources"]) == 4


def test_bing_captcha_falls_back(tmp_path, monkeypatch):
    b, _ = broker(tmp_path, monkeypatch, {"bing.com": Resp(200, "<html>solve the captcha</html>"),
                                          "algolia": Resp(200, data=HN_DATA)}, backends="bing,hn")
    assert [r["backend"] for r in b.search("scout", "q")] == ["hn", "hn"]


def test_empty_answer_not_cached_and_old_empty_cache_ignored(tmp_path, monkeypatch):
    routes = {"algolia": Resp(200, data={"hits": []})}
    b, calls = broker(tmp_path, monkeypatch, routes, backends="hn")
    assert b.search("scout", "q") == []
    assert not list((tmp_path / "cache").glob("search_*"))
    b._cache("search", "q2").write_text("[]", encoding="utf-8")  # left by the old code
    routes["algolia"] = Resp(200, data=HN_DATA)
    assert len(b.search("scout", "q2")) == 2


def test_cache_hits_do_not_use_budget(tmp_path, monkeypatch):
    b, calls = broker(tmp_path, monkeypatch, {"algolia": Resp(200, data=HN_DATA)}, backends="hn")
    b.budget = 2
    b.search("scout", "q")
    for _ in range(5):
        b.search("scout", "q")  # cached
    assert len(calls) == 1 and b.used["scout"] == 1


def test_budget_reset_for_each_attempt(tmp_path, monkeypatch):
    b, _ = broker(tmp_path, monkeypatch, {"algolia": Resp(200, data=HN_DATA)}, backends="hn")
    b.budget = 2
    b.search("scout", "a"), b.search("scout", "b")
    with pytest.raises(ToolDenied):
        b.search("scout", "c")
    b.reset_budget("phase 1 attempt 1")
    assert b.search("scout", "c")
    assert "tool_budget_reset" in b.log.names()


def test_fetch_challenge_page_raises_and_is_not_cached(tmp_path, monkeypatch):
    b, _ = broker(tmp_path, monkeypatch, {"x.dev": Resp(200, "<title>Just a moment...</title><div id=cf-chl></div>")})
    with pytest.raises(T.FetchBlocked):
        b.fetch("scout", "https://x.dev/crm")
    assert not list((tmp_path / "cache").glob("fetch_*"))


def test_search_fetch_then_quote_verifies(tmp_path, monkeypatch):
    """End to end on a fake web: search finds a page, fetch reads it, the exact quote is found in the page."""
    page = "<html><body><p>Freelance designers told us they <b>would pay $20</b> for a client tracker.</p></body></html>"
    b, _ = broker(tmp_path, monkeypatch, {"algolia": Resp(200, data=HN_DATA),
                                          "news.ycombinator.com": Resp(200, page)}, backends="hn")
    url = b.search("scout", "client tracker")[1]["url"]
    text = b.fetch("scout", url)
    assert quote_found("they would pay $20 for a client tracker", text)
    assert not quote_found("they would pay $50 for a client tracker", text)



def test_default_order_has_no_bing(monkeypatch):
    from core.tools import backend_order
    monkeypatch.delenv("SEARCH_BACKENDS", raising=False)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    assert backend_order() == ["hn", "duckduckgo"]
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    assert backend_order() == ["searxng", "hn", "duckduckgo"]
    monkeypatch.setenv("SEARCH_BACKENDS", "bing,hn")
    assert backend_order() == ["bing", "hn"]  # still available when asked for


def test_hn_query_words_are_optional(monkeypatch):
    import requests
    import core.tools as T
    seen = {}

    class R:
        status_code, text = 200, ""

        def json(self):
            return {"hits": []}
    monkeypatch.setattr(requests, "get", lambda url, params=None, headers=None, timeout=None: (seen.update(params or {}), R())[1])
    T._search_hn("freelance designers project status")
    assert seen["optionalWords"] == "freelance designers project status"
