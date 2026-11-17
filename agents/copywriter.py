"""copywriter: product page copy reusing the tested landing copy; features and FAQ."""
from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P2_CANVAS, P2_LANDING, P3_COPY, P3_SPEC,
                              content_violations, get_artifact)


class Copywriter(M3InputsMixin, Agent):
    name = "copywriter"
    phase = 3
    step = P3_COPY
    inputs = [P2_LANDING, P3_SPEC, P2_CANVAS]
    tools = []
    required_keys = ["headline", "features", "faq", "cta"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        removed = []
        feats = data.get("features")
        feats = [feats] if isinstance(feats, str) else [str(f) for f in (feats or [])]
        kept = []
        for f in feats:
            (removed if content_violations(f) else kept).append(f)
        data["features"] = kept
        faq = []
        for item in data.get("faq") or []:
            if isinstance(item, dict) and (item.get("q") or item.get("question")):
                q = str(item.get("q") or item.get("question"))
                a = str(item.get("a") or item.get("answer") or "")
                if content_violations(q + " " + a):
                    removed.append(q)
                else:
                    faq.append({"q": q, "a": a})
        data["faq"] = faq
        landing = get_artifact(ctx, P2_LANDING) or {}
        if not str(data.get("headline") or "").strip() or content_violations(str(data.get("headline"))):
            data["headline"] = landing.get("headline", "")
        if not str(data.get("cta") or "").strip() or content_violations(str(data.get("cta"))):
            data["cta"] = landing.get("call_to_action") or "Join the waitlist"
        data["reused_tested_headline"] = data["headline"] == landing.get("headline")
        if removed:
            data["removed_by_code"] = removed
        return data
