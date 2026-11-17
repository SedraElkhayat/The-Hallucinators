# OWNER: M1
"""ToolBroker: the only door to the web. Allow-list, per-agent budget, disk cache, logged calls."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

SYSTEM_PREFIX = "system:"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
# Search backends, tried in this order until MIN_RESULTS distinct results are found.
# searxng is used only when SEARXNG_URL is set (docker compose sets it to its own container).
DEFAULT_BACKENDS = "searxng,bing,hn,duckduckgo"
MIN_RESULTS = 3


class ToolDenied(Exception):
    pass


class SearchBlocked(Exception):
    """A search engine answered with an error or a bot check instead of results (never a silent 0 results)."""


class FetchBlocked(Exception):
    """A page answered with a bot check instead of its content (never cached, never quoted)."""


# Bot-check and challenge pages: DuckDuckGo "anomaly", Bing/Google captcha, Cloudflare challenge.
_BLOCK_MARKERS = ("anomaly-modal", "anomaly.js", "challenge-form", "captcha", "unusual traffic",
                  "are you a robot", "/sorry/index", "cf-chl", "just a moment...")


def block_reason(status: int, text: str, found_any: bool) -> str | None:
    """Why a search/fetch answer is not real content, or None. A page with parsed results is accepted."""
    if status != 200:
        return f"HTTP {status}" + (" (bot check)" if status == 202 else "")
    if found_any:
        return None
    low = (text or "")[:300000].lower()
    for m in _BLOCK_MARKERS:
        if m in low:
            return f"bot check page ({m})"
    return None


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return " ".join(p.parts)


_DDG_LINK = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DDG_SNIP = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")


def parse_ddg(html_text: str, limit: int = 8) -> list[dict]:
    links, snips = _DDG_LINK.findall(html_text), _DDG_SNIP.findall(html_text)
    out = []
    for i, (href, title) in enumerate(links):
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            continue
        snippet = _TAGS.sub("", snips[i]) if i < len(snips) else ""
        out.append({"title": unescape(_TAGS.sub("", title)).strip(), "url": href, "snippet": unescape(snippet).strip()})
        if len(out) >= limit:
            break
    return out


_BING_ITEM = re.compile(r'<li class="b_algo"[^>]*>(.*?)</li>', re.S)
_BING_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BING_SNIP = re.compile(r'<p[^>]*>(.*?)</p>', re.S)


def _bing_target(href: str) -> str:
    """Bing wraps result links as bing.com/ck/a?...&u=a1<base64url>; return the real URL."""
    href = unescape(href)
    if "bing.com/ck/a" in href:
        u = parse_qs(urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            b = u[2:]
            try:
                return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "replace")
            except (ValueError, UnicodeDecodeError):
                return ""
    return href


def parse_bing(html_text: str, limit: int = 8) -> list[dict]:
    out = []
    for block in _BING_ITEM.findall(html_text):
        m = _BING_LINK.search(block)
        if not m:
            continue
        url = _bing_target(m.group(1))
        host = urlparse(url).hostname or ""
        if not url.startswith("http") or host.endswith("bing.com"):
            continue
        sn = _BING_SNIP.search(block)
        snippet = unescape(_TAGS.sub("", sn.group(1))).strip() if sn else ""
        out.append({"title": unescape(_TAGS.sub("", m.group(2))).strip(), "url": url, "snippet": snippet})
        if len(out) >= limit:
            break
    return out


def parse_hn(data: dict, limit: int = 8) -> list[dict]:
    """Hacker News Algolia API hits. Comments and Ask HN posts link to their item page (the quote is there)."""
    out = []
    for h in (data or {}).get("hits", []):
        oid = h.get("objectID")
        body = h.get("comment_text") or h.get("story_text") or ""
        url = h.get("url") if h.get("title") and h.get("url") else (
            f"https://news.ycombinator.com/item?id={oid}" if oid else "")
        if not url.startswith("http"):
            continue
        title = h.get("title") or h.get("story_title") or "Hacker News comment"
        snippet = re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", body))).strip()[:300]
        out.append({"title": title.strip(), "url": url, "snippet": snippet})
        if len(out) >= limit:
            break
    return out


def parse_searxng(data: dict, limit: int = 8) -> list[dict]:
    out = []
    for r in (data or {}).get("results", []):
        url = r.get("url") or ""
        if url.startswith("http"):
            out.append({"title": (r.get("title") or "").strip(), "url": url, "snippet": (r.get("content") or "").strip()})
        if len(out) >= limit:
            break
    return out


def _search_searxng(query: str) -> list[dict]:
    base = os.getenv("SEARXNG_URL", "").rstrip("/")
    r = requests.get(f"{base}/search", params={"q": query, "format": "json", "language": "en"},
                     headers={"User-Agent": UA}, timeout=15)
    if r.status_code == 403:
        raise SearchBlocked("HTTP 403 (is format json enabled in searxng/settings.yml?)")
    why = block_reason(r.status_code, "", True)
    if why:
        raise SearchBlocked(why)
    return parse_searxng(r.json())


def _search_bing(query: str) -> list[dict]:
    r = requests.get("https://www.bing.com/search", params={"q": query, "setlang": "en", "cc": "US"},
                     headers=HEADERS, timeout=10)
    res = parse_bing(r.text) if r.status_code == 200 else []
    why = block_reason(r.status_code, r.text, bool(res))
    if why:
        raise SearchBlocked(why)
    return res


def _search_hn(query: str) -> list[dict]:
    r = requests.get("https://hn.algolia.com/api/v1/search", params={"query": query, "hitsPerPage": 10},
                     headers={"User-Agent": UA}, timeout=10)
    why = block_reason(r.status_code, "", True)
    if why:
        raise SearchBlocked(why)
    return parse_hn(r.json())


def _search_ddg(query: str) -> list[dict]:
    r = requests.get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", headers=HEADERS, timeout=10)
    res = parse_ddg(r.text) if r.status_code == 200 else []
    why = block_reason(r.status_code, r.text, bool(res))
    if why:  # DuckDuckGo answers scripts with HTTP 202 + an "anomaly" page: an error, not 0 results
        raise SearchBlocked(why)
    return res


BACKENDS = {"searxng": _search_searxng, "bing": _search_bing, "hn": _search_hn, "duckduckgo": _search_ddg}


def backend_order() -> list[str]:
    names = [b.strip().lower() for b in os.getenv("SEARCH_BACKENDS", DEFAULT_BACKENDS).split(",") if b.strip()]
    names = ["duckduckgo" if b == "ddg" else b for b in names]
    return [b for b in names if b in BACKENDS and (b != "searxng" or os.getenv("SEARXNG_URL"))]


class ToolBroker:
    def __init__(self, log, cache_dir: Path | str | None = None, mock: bool = False,
                 budget: int | None = None, allow: dict | None = None):
        self.log = log
        self.mock = mock
        self.cache_dir = Path(cache_dir or os.getenv("TOOL_CACHE_DIR", ".cache/tools"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.budget = int(budget or os.getenv("TOOL_BUDGET", "8"))
        self.allow = allow  # optional override {agent: [tools]}
        self.used: dict[str, int] = {}
        self._lock = threading.Lock()

    # ---- policy ----
    def _allowed_tools(self, agent: str) -> list[str]:
        if self.allow is not None and agent in self.allow:
            return list(self.allow[agent])
        try:
            from agents import get_agent
            return list(get_agent(agent).tools)
        except Exception:
            return []

    def reset_budget(self, reason: str = "") -> None:
        """Give every agent a fresh budget (the orchestrator calls this on each gate attempt)."""
        with self._lock:
            self.used.clear()
        self.log.action("system:tool_broker", "tool_budget_reset", reason=reason)

    def _check(self, agent: str, tool: str, cached: bool = False) -> None:
        if agent.startswith(SYSTEM_PREFIX):
            return
        if tool not in self._allowed_tools(agent):
            self.log.action(agent, f"tool_denied:{tool}", outcome="denied")
            raise ToolDenied(f"{agent} may not use {tool}")
        if cached:  # answered from the disk cache: no network call, so no budget used
            return
        with self._lock:
            n = self.used.get(agent, 0)
            if n >= self.budget:
                self.log.action(agent, f"tool_budget_exceeded:{tool}", outcome="denied")
                raise ToolDenied(f"{agent} exceeded tool budget ({self.budget})")
            self.used[agent] = n + 1

    def _cache(self, kind: str, key: str):
        h = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:32]
        return self.cache_dir / f"{kind}_{h}.json"

    # ---- tools ----
    def search(self, agent: str, query: str) -> list[dict]:
        cp = None if self.mock else self._cache("search", query)
        cached = None
        if cp is not None and cp.exists():
            cached = json.loads(cp.read_text(encoding="utf-8")) or None  # an old empty cache entry is ignored
        self._check(agent, "search", cached=cached is not None)
        backends: list[str] = []
        if self.mock:
            res = [{"title": f"MOCKED result for {query}",
                    "url": f"https://example.com/mock/search/{quote_plus(query)}",
                    "snippet": "MOCKED search snippet"}]
        elif cached is not None:
            res = cached
            backends = sorted({x.get("backend", "") for x in res} - {""})
        else:
            res, errors, seen = [], [], set()
            for name in backend_order():
                try:
                    found = BACKENDS[name](query)
                except Exception as e:  # noqa: BLE001 - one backend down: try the next one
                    errors.append(f"{name}: {str(e)[:120]}")
                    self.log.action(agent, "search_backend_failed", backend=name, query=query, error=str(e)[:200])
                    continue
                new = [dict(x, backend=name) for x in found if x["url"] not in seen]
                seen.update(x["url"] for x in new)
                if new:
                    backends.append(name)
                res += new
                if len(res) >= MIN_RESULTS:
                    break
            res = res[:8]
            if not res and errors:
                raise SearchBlocked("all search backends failed: " + "; ".join(errors))
            if res:  # never cache an empty answer: a blocked search must be retried next time
                cp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        if not agent.startswith(SYSTEM_PREFIX):
            self.log.action(agent, "search", sources=[x["url"] for x in res], query=query, backends=backends)
        return res

    def fetch(self, agent: str, url: str) -> str:
        cp = None if self.mock else self._cache("fetch", url)
        self._check(agent, "fetch", cached=cp is not None and cp.exists())
        if self.mock:
            text = f"MOCKED page text for {url}"
        elif cp.exists():
            text = json.loads(cp.read_text(encoding="utf-8"))["text"]
        else:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            text = html_to_text(r.text) if "html" in ctype else r.text
            if len(text) < 2000:  # a real page with content is longer than a challenge page
                why = block_reason(200, r.text, False)
                if why:
                    raise FetchBlocked(f"{url}: {why}")
            text = text[:20000]
            cp.write_text(json.dumps({"url": url, "text": text}, ensure_ascii=False), encoding="utf-8")
        if not agent.startswith(SYSTEM_PREFIX):
            self.log.action(agent, "fetch", sources=[url])
        return text
