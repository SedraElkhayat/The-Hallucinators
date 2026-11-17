"""demand_analyst: behaviour over opinion. Do people already pay for substitutes? Price signals and repeated
requests, each as a quote-checked claim."""
from agents.m2_common import DEMAND, ResearchAgent, as_list, short


class DemandAnalyst(ResearchAgent):
    name = "demand_analyst"
    phase = 1
    step = DEMAND
    required_keys = ["price_signals", "claims", "insufficient_evidence"]

    def queries(self, ctx, card):
        return [f"{short(card.get('solution'), 3)} price", short(card.get('problem'), 3),
                f"{short(card.get('customer'), 2)} {short(card.get('problem'), 1)}"]

    def post_process(self, ctx, data):
        data = super().post_process(ctx, data)
        sig = []
        for s in as_list(data.get("price_signals")):
            if isinstance(s, str):
                s = {"text": s, "claim_index": None}
            if isinstance(s, dict) and str(s.get("text", "")).strip():
                sig.append(s)
        data["price_signals"] = sig
        return data
