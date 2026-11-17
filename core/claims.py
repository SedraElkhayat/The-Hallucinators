# OWNER: M2
"""Claim checker: re-check every claim by fetching its source and looking for the exact quote.

A claim is ``{"claim", "source_url", "quote", "verified", "assumption"}``.

Rules (code, not prompt):
- no http(s) source_url -> verified False, assumption True;
- mock mode (CONTEXT.md 4a.3): ``https://example.com/mock/...`` sources with a quote -> verified True, mocked
  True (offline tests only; in a real run a mock source is always downgraded);
- a quote shorter than 20 characters -> verified False, assumption True;
- real mode: fetch the page through ``ctx.tools.fetch("system:claim_checker", url)``; verified True only if
  the normalized quote is a substring of the normalized page text; else verified False, assumption True;
- local or private network addresses are never fetched;
- duplicate (url, quote) pairs inside one artifact are marked ``duplicate: true`` (gates count them once).
Every downgraded claim is logged as ``claim_downgraded`` (agent ``claim_checker``).
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from urllib.parse import urlparse

MOCK_PREFIX = "https://example.com/mock/"
CHECKER = "system:claim_checker"
MIN_QUOTE = 20

_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
           "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
           "–": "-", "—": "-", "−": "-", "…": "...", " ": " "}
_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat and tatweel
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",  # alef forms
                         "ى": "ي",                                                    # alef maqsura -> yeh
                         "ة": "ه"})                                                   # teh marbuta -> heh


def normalize(text: str) -> str:
    """Lowercase, NFKC, straight quotes, no zero-width characters, Arabic letters unified, single spaces."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _ZERO_WIDTH.sub("", t)
    for a, b in _QUOTES.items():
        t = t.replace(a, b)
    t = _AR_DIACRITICS.sub("", t).translate(_AR_MAP)
    t = t.lower()
    return re.sub(r"\s+", " ", t).strip()


def quote_found(quote: str, page: str) -> bool:
    q = normalize(quote).strip(" .\"'")
    return bool(q) and q in normalize(page)


def _public_http(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return True


def _downgrade(ctx, c: dict, reason: str, agent_hint: str = "") -> None:
    c["verified"] = False
    c["assumption"] = True
    c["check"] = reason
    ctx.log.action("claim_checker", "claim_downgraded",
                   sources=[c["source_url"]] if _public_http(c.get("source_url") or "") else [],
                   reason=reason, claim=str(c.get("claim", ""))[:200], for_agent=agent_hint or None)


def verify_claims(ctx, data: dict) -> dict:
    """Check every claim in ``data["claims"]`` in place and return ``data``."""
    claims = data.get("claims")
    if not isinstance(claims, list):
        return data
    hint = str((data.get("_meta") or {}).get("agent", "")) if isinstance(data.get("_meta"), dict) else ""
    seen: set = set()
    pages: dict[str, str | None] = {}
    for c in claims:
        if not isinstance(c, dict):
            continue
        url = str(c.get("source_url") or "").strip()
        quote = str(c.get("quote") or "").strip()
        c["source_url"], c["quote"] = url, quote
        key = (url, normalize(quote))
        if key in seen and url:
            c["duplicate"] = True
        seen.add(key)
        if not url.lower().startswith(("http://", "https://")):
            _downgrade(ctx, c, "no source URL", hint)
            continue
        if url.startswith(MOCK_PREFIX):
            # CONTEXT.md 4a.3: offline tests accept mock sources (labeled mocked); a real run never does.
            if getattr(ctx, "mock", False) and quote:
                c["verified"], c["assumption"], c["mocked"] = True, False, True
                c["check"] = "MOCKED: mock source accepted in mock mode"
            else:
                _downgrade(ctx, c, "mock source in a real run" if quote else "no quote", hint)
            continue
        if len(quote) < MIN_QUOTE:
            _downgrade(ctx, c, f"quote shorter than {MIN_QUOTE} characters", hint)
            continue
        if not _public_http(url):
            _downgrade(ctx, c, "source is not a public web address", hint)
            continue
        if url not in pages:
            try:
                pages[url] = ctx.tools.fetch(CHECKER, url)
            except Exception as e:  # noqa: BLE001 - an unreachable source cannot verify anything
                pages[url] = None
                c["fetch_error"] = f"{type(e).__name__}"[:80]
        page = pages[url]
        if page is None:
            _downgrade(ctx, c, "source could not be fetched", hint)
        elif quote_found(quote, page):
            c["verified"], c["assumption"] = True, False
            c["check"] = "quote found on the source page"
        else:
            _downgrade(ctx, c, "quote not found on the source page", hint)
    return data


def count_verified(artifacts: list[dict]) -> int:
    """Unique (url, normalized quote) pairs with verified True across artifacts (duplicates count once)."""
    pairs = set()
    for art in artifacts:
        for c in (art or {}).get("claims", []) or []:
            if isinstance(c, dict) and c.get("verified") is True:
                pairs.add((str(c.get("source_url", "")).strip(), normalize(str(c.get("quote", "")))))
    return len(pairs)
