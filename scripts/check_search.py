# OWNER: M1
"""Live check of web search on this machine: each backend, then search -> fetch -> quote verification.

    python -m scripts.check_search "notion templates for freelancers"

Nothing is written to outputs/ or decision_log.json (uses a throwaway log and cache).
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

from core import tools as T
from core.claims import quote_found


class _Log:
    def action(self, agent, action, sources=(), **extra):
        if action.endswith("failed"):
            print(f"    log: {action} {extra.get('backend', '')} {extra.get('error', '')}")


def main(query: str) -> int:
    print(f"query: {query!r}")
    print(f"SEARCH_BACKENDS={os.getenv('SEARCH_BACKENDS', T.DEFAULT_BACKENDS)}  SEARXNG_URL={os.getenv('SEARXNG_URL', '')!r}")
    print(f"backends in use: {T.backend_order()}\n")
    for name in T.backend_order():
        try:
            res = T.BACKENDS[name](query)
            print(f"[{'OK' if res else 'EMPTY'}] {name}: {len(res)} results" + (f"  e.g. {res[0]['url']}" if res else ""))
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {e}")
    broker = T.ToolBroker(_Log(), cache_dir=tempfile.mkdtemp(), allow={"check": ["search", "fetch"]}, budget=20)
    try:
        results = broker.search("check", query)
    except Exception as e:  # noqa: BLE001
        print(f"\nsearch through the broker FAILED: {e}")
        return 1
    print(f"\nbroker: {len(results)} results from {sorted({r['backend'] for r in results})}")
    for r in results[:5]:
        try:
            text = broker.fetch("check", r["url"])
        except Exception as e:  # noqa: BLE001
            print(f"  fetch FAIL {r['url']}: {str(e)[:100]}")
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 40 <= len(s.strip()) <= 200]
        if not sentences:
            print(f"  fetched {r['url']} ({len(text)} chars) but no sentence to quote")
            continue
        quote = sentences[len(sentences) // 2]
        ok, fake = quote_found(quote, text), quote_found(quote + " invented words", text)
        print(f"  fetched {r['url']} ({len(text)} chars)\n    real quote verified: {ok}; invented quote verified: {fake}")
        if ok and not fake:
            print("\nPASS: search -> fetch -> exact-quote verification works on the live web.")
            return 0
    print("\nNO VERIFIED RESULT: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:]) or "notion templates for freelancers"))
