# OWNER: M2
# STUB: replace the contents, keep the public names. (Working minimal version of the frozen contract.)
"""Pre-registered gate checks and evaluation."""
from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import asdict, dataclass

OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt, "<": operator.lt}
SEVERITY = {"go": 0, "repeat": 1, "pivot": 2, "stop": 3}


@dataclass
class Check:
    id: str
    metric: str
    op: str
    value: float
    on_fail: str  # repeat | pivot | stop


@dataclass
class GateResult:
    outcome: str  # go | repeat | pivot | stop
    reasons: list[str]
    metrics: dict
    attempt: int


def preregister(ctx, phase: int, checks: list[Check]) -> str:
    payload = {"phase": phase, "checks": [asdict(c) for c in checks]}
    text = json.dumps(payload, indent=2, sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    payload["sha256"] = digest
    (ctx.out_dir / f"phase{phase}_gate_criteria.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ctx.log.action("gate", f"preregister_gate_{phase}", criteria_sha256=digest)
    ctx.extra.setdefault("_gate_checks", {})[phase] = checks
    return digest


def evaluate(ctx, phase: int, metrics: dict, attempt: int, max_repeats: int = 1) -> GateResult:
    checks = ctx.extra.get("_gate_checks", {}).get(phase, [])
    outcome, reasons = "go", []
    for c in checks:
        val = metrics.get(c.metric)
        ok = val is not None and OPS[c.op](val, c.value)
        if not ok:
            reasons.append(f"{c.id}: {c.metric}={val!r} fails {c.op} {c.value} -> {c.on_fail}")
            if SEVERITY[c.on_fail] > SEVERITY[outcome]:
                outcome = c.on_fail
    if outcome == "repeat" and attempt >= max_repeats:
        reasons.append(f"repeat budget used (attempt {attempt} of {max_repeats}) -> stop")
        outcome = "stop"
    if ctx.extra.get("halt_phase"):
        reasons.insert(0, f"phase halted early: {ctx.extra['halt_phase']}")
    result = GateResult(outcome=outcome, reasons=reasons, metrics=metrics, attempt=attempt)
    md = [f"# Gate {phase} decision: **{outcome.upper()}**", "",
          f"Attempt: {attempt}", "", "## Metrics (computed in code)", "",
          "```json", json.dumps(metrics, indent=2), "```", "", "## Checks (pre-registered)", ""]
    md += [f"- `{c.id}`: {c.metric} {c.op} {c.value} (on fail: {c.on_fail})" for c in checks] or ["- none"]
    md += ["", "## Reasons", ""] + ([f"- {r}" for r in reasons] or ["- all checks passed"])
    (ctx.out_dir / f"phase{phase}_gate_decision.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    ctx.log.action("gate", f"gate_{phase}", outcome=outcome, reasons=reasons, metrics=metrics)
    return result
