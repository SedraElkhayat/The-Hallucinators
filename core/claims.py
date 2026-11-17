# OWNER: M2
# STUB: replace the contents, keep the public names. (Working minimal version of the frozen contract.)
"""Re-check every claim: fetch the source and look for the exact quote."""
from __future__ import annotations

import re

MOCK_PREFIX = "https://example.com/mock/"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def verify_claims(ctx, data: dict) -> dict:
    for c in data.get("claims", []) or []:
        if not isinstance(c, dict):
            continue
        url, quote = c.get("source_url") or "", c.get("quote") or ""
        if ctx.mock and url.startswith(MOCK_PREFIX):
            c["verified"], c["mocked"] = True, True
            c.setdefault("assumption", False)
            continue
        verified = False
        if url.startswith("http") and quote:
            try:
                page = ctx.tools.fetch("system:claim_checker", url)
                verified = _norm(quote) in _norm(page)
            except Exception:
                verified = False
        c["verified"] = verified
        if not verified:
            c["assumption"] = True
    return data
