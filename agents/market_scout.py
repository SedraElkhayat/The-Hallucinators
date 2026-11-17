"""market_scout: define the market segment and check whether people want this; claims with exact quotes."""
from agents.m2_common import MARKET, ResearchAgent, short


class MarketScout(ResearchAgent):
    name = "market_scout"
    phase = 1
    step = MARKET
    required_keys = ["market_definition", "claims", "insufficient_evidence"]

    def queries(self, ctx, card):
        return [short(card.get('customer'), 3), short(card.get('problem'), 3),
                f"{short(card.get('customer'), 2)} survey"]

    def post_process(self, ctx, data):
        data = super().post_process(ctx, data)
        md = data.get("market_definition")
        if not isinstance(md, dict):
            md = {"segment": str(md or "unknown"), "size_note": "unknown"}
        md.setdefault("segment", "unknown")
        md.setdefault("size_note", "unknown")
        data["market_definition"] = md
        return data
