# OWNER: M1
"""ToolBroker: the only door to the web. Allow-list, per-agent budget, disk cache, logged calls."""
from __future__ import annotations

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


class ToolDenied(Exception):
    pass


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

    def _check(self, agent: str, tool: str) -> None:
        if agent.startswith(SYSTEM_PREFIX):
            return
        if tool not in self._allowed_tools(agent):
            self.log.action(agent, f"tool_denied:{tool}", outcome="denied")
            raise ToolDenied(f"{agent} may not use {tool}")
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
        self._check(agent, "search")
        if self.mock:
            res = [{"title": f"MOCKED result for {query}",
                    "url": f"https://example.com/mock/search/{quote_plus(query)}",
                    "snippet": "MOCKED search snippet"}]
        else:
            cp = self._cache("search", query)
            if cp.exists():
                res = json.loads(cp.read_text(encoding="utf-8"))
            else:
                r = requests.get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                                 headers={"User-Agent": UA}, timeout=10)
                r.raise_for_status()
                res = parse_ddg(r.text)
                cp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        if not agent.startswith(SYSTEM_PREFIX):
            self.log.action(agent, "search", sources=[x["url"] for x in res], query=query)
        return res

    def fetch(self, agent: str, url: str) -> str:
        self._check(agent, "fetch")
        if self.mock:
            text = f"MOCKED page text for {url}"
        else:
            cp = self._cache("fetch", url)
            if cp.exists():
                text = json.loads(cp.read_text(encoding="utf-8"))["text"]
            else:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                text = html_to_text(r.text) if "html" in ctype else r.text
                text = text[:20000]
                cp.write_text(json.dumps({"url": url, "text": text}, ensure_ascii=False), encoding="utf-8")
        if not agent.startswith(SYSTEM_PREFIX):
            self.log.action(agent, "fetch", sources=[url])
        return text
