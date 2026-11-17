"""demand_results (founder kind): records the founder's demand-test result with its provenance.

Founder input key: ``demand_results`` = JSON text {"signups": int, "days": int, "provenance": "REAL"|"MOCKED"}.
Invalid input is asked again once; if it is still invalid, no result is recorded and
``ctx.extra["halt_phase"]`` is set with the reason.
"""
import json

from agents.base import Agent
from agents.m3_common import P2_PLAN, P2_RESULTS, plan_target
from core.contracts import AgentResult


def _int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, float) and v.is_integer() and v >= 0:
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def parse_demand_results(raw):
    """Return (dict, None) when valid, else (None, reason)."""
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        return None, f"not valid JSON ({exc})"
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    signups, days = _int(obj.get("signups")), _int(obj.get("days"))
    prov = str(obj.get("provenance", "")).strip().upper()
    if signups is None:
        return None, "signups must be a whole number >= 0"
    if days is None:
        return None, "days must be a whole number >= 0"
    if prov not in ("REAL", "MOCKED"):
        return None, 'provenance must be "REAL" or "MOCKED"'
    return {"signups": signups, "days": days, "provenance": prov}, None


class DemandResults(Agent):
    name = "demand_results"
    phase = 2
    step = P2_RESULTS
    inputs = [P2_PLAN]
    tools = []
    required_keys = ["signups", "days", "provenance", "ratio"]
    kind = "founder"

    def run(self, ctx):
        self.check_inputs(ctx)
        target, window = plan_target(ctx)
        prompt = (f"Enter the demand-test result as JSON: "
                  f'{{"signups": <whole number>, "days": <whole number>, "provenance": "REAL" or "MOCKED"}}. '
                  f"The target set before the test was {target} sign-ups in {window} days. "
                  f"Use MOCKED unless the sign-ups came from real visitors.")
        parsed, reason = None, None
        for attempt in range(2):  # ask, then ask again once
            ask = prompt if attempt == 0 else f"{prompt} The previous answer was invalid: {reason}."
            try:
                raw = ctx.founder.provide("demand_results", ask)
            except Exception as exc:  # noqa: BLE001 - missing input counts as invalid
                parsed, reason = None, f"no input ({exc})"
                continue
            parsed, reason = parse_demand_results(raw)
            if parsed:
                break
        if not parsed:
            # No result is recorded (never a made-up 0): the phase halts and the gate cannot pass.
            why = f"demand results invalid after asking twice: {reason}"
            ctx.extra["halt_phase"] = why
            ctx.log.action(self.name, "demand_results_invalid", reason=reason, outcome="halt_phase")
            md = f"# Demand test results\n\nNo result recorded: {why}.\n"
            return AgentResult(data={"error": why}, markdown=md, sources=[], model=None, cost=0.0, mocked=False)

        ratio = round(parsed["signups"] / target, 4)
        data = dict(parsed, ratio=ratio, target=target, window_days=window)
        prov = parsed["provenance"]
        md = (f"PROVENANCE: {prov}\n\n# Demand test results\n\n"
              f"- Sign-ups: {parsed['signups']} in {parsed['days']} days\n"
              f"- Target set before the test: {target} in {window} days\n"
              f"- Ratio (sign-ups / target): {ratio}\n")
        if prov == "MOCKED":
            md += "\nThis result is MOCKED: it did not come from real visitors.\n"
        return self.save(ctx, data, markdown=md, sources=[], model=None, cost=0.0, mocked=(prov == "MOCKED"),
                         action="record_demand_results", provenance=prov, ratio=ratio)
