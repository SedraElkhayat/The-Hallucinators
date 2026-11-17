"""competitor_scanner: brief scan of the top rivals and substitutes and what they charge, as stated on their
pages. A competitor's pricing counts as sourced only when a verified claim from its URL backs it."""
from urllib.parse import urlparse

from agents.m2_common import COMPETITORS, ResearchAgent, as_list, short


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


class CompetitorScanner(ResearchAgent):
    name = "competitor_scanner"
    phase = 1
    step = COMPETITORS
    required_keys = ["competitors", "claims", "insufficient_evidence"]

    def queries(self, ctx, card):
        return [f"{short(card.get('solution'), 6)} alternatives pricing", f"best {short(card.get('solution'), 6)}"]

    def post_process(self, ctx, data):
        data = super().post_process(ctx, data)
        verified_hosts = {_host(c.get("source_url", "")) for c in data["claims"] if c.get("verified") is True}
        comps = []
        for c in as_list(data.get("competitors")):
            if isinstance(c, str):
                c = {"name": c}
            if not isinstance(c, dict) or not str(c.get("name", "")).strip():
                continue
            c.setdefault("url", "")
            c.setdefault("pricing", "unknown")
            c.setdefault("positioning", "unknown")
            c["pricing_sourced"] = bool(c["url"]) and _host(c["url"]) in verified_hosts
            if not c["pricing_sourced"] and c["pricing"] != "unknown" and "ASSUMPTION" not in str(c["pricing"]):
                c["pricing"] = f"ASSUMPTION: {c['pricing']}"
            comps.append(c)
        data["competitors"] = comps[:8]
        return data
