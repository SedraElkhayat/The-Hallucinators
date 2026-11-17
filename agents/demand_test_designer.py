"""demand_test_designer: waitlist test with a target fixed before any result exists."""
from agents.base import Agent
from agents.m3_common import (DEFAULT_TARGET, DEFAULT_WINDOW_DAYS, M3InputsMixin, P1_IDEA_CARD,
                              P2_CANVAS, P2_COMPETITOR_ANALYSIS, P2_PLAN, P2_RESULTS,
                              get_artifact, positive_int)


class DemandTestDesigner(M3InputsMixin, Agent):
    name = "demand_test_designer"
    phase = 2
    step = P2_PLAN
    inputs = [P2_CANVAS, P1_IDEA_CARD, P2_COMPETITOR_ANALYSIS]
    tools = []
    required_keys = ["hypothesis", "metric", "target", "window_days", "traffic_sources", "reading_rule"]
    kind = "llm"

    def post_process(self, ctx, data: dict) -> dict:
        data["metric"] = "waitlist_signups"
        target = positive_int(data.get("target"))
        window = positive_int(data.get("window_days"))
        data["target"] = target or DEFAULT_TARGET
        data["window_days"] = window or DEFAULT_WINDOW_DAYS
        if target is None or window is None:
            data["defaults_applied"] = True
        # Never move the goalposts: if a result already exists (a repeat round),
        # keep the target and window that were set before that result.
        previous = get_artifact(ctx, P2_PLAN)
        if previous and get_artifact(ctx, P2_RESULTS) is not None:
            prev_t, prev_w = positive_int(previous.get("target")), positive_int(previous.get("window_days"))
            if prev_t and prev_w:
                data["target"], data["window_days"] = prev_t, prev_w
                data["target_locked"] = True
        ts = data.get("traffic_sources")
        if isinstance(ts, str):
            ts = [ts]
        data["traffic_sources"] = [str(t) for t in (ts or [])]
        data["reading_rule"] = str(data.get("reading_rule") or "") or (
            f"ratio = sign-ups / {data['target']}. ratio >= 1.0 go; 0.5 to 1.0 repeat; 0.2 to 0.5 pivot; below 0.2 stop.")
        return data
