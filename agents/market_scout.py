"""market_scout: define the market segment and check whether people want this; claims with exact quotes."""
from agents.m2_common import MARKET, ResearchAgent, short, topic_queries


class MarketScout(ResearchAgent):
    name = "market_scout"
    phase = 1
    step = MARKET
    required_keys = ["market_definition", "claims", "insufficient_evidence"]

    def queries(self, ctx, card):
        t = topic_queries(card)
        return [f"{short(card.get('customer'), 3)} statistics", f"{t['cust']} {t['prob']}", f"{t['cust']} survey report"]

    def post_process(self, ctx, data):
        data = super().post_process(ctx, data)
        md = data.get("market_definition")
        if not isinstance(md, dict):
            md = {"segment": str(md or "unknown"), "size_note": "unknown"}
        md.setdefault("segment", "unknown")
        md.setdefault("size_note", "unknown")
        data["market_definition"] = md
        return data
