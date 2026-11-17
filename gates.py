# OWNER: M2
"""Gate engine: criteria are pre-registered before a phase runs, then applied in code.

preregister(ctx, phase, checks) -> sha256 of the criteria; writes <out_dir>/phase<N>_gate_criteria.json
                                    and logs ``preregister_gate_<N>`` BEFORE any agent of the phase runs.
evaluate(ctx, phase, metrics, attempt, max_repeats=1) -> GateResult
    - every pre-registered check is applied to the metrics computed in code (phases/phaseN.measure);
    - a missing metric fails its check;
    - severity stop > pivot > repeat > go: the most severe failed check decides;
    - ``repeat`` at attempt >= max_repeats becomes ``stop`` ("repeat budget exhausted");
    - writes <out_dir>/phase<N>_gate_decision.md (outcome, every check pass/fail, metrics, reasons,
      what would change this verdict, criteria hash) and logs ``gate_<N>`` with ``outcome``.
The system only recommends; the founder approves or overrides (orchestrator.founder_gate).
"""
from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import asdict, dataclass

OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt, "<": operator.lt}
SEVERITY = {"go": 0, "repeat": 1, "pivot": 2, "stop": 3}
OUTCOME_TEXT = {
    "go": "GO: move on to the next phase.",
    "repeat": "REPEAT: run this phase again to collect the missing evidence.",
    "pivot": "PIVOT: go back and work on the next-best alternative.",
    "stop": "STOP: the evidence does not support continuing.",
}


@dataclass
class Check:
    id: str
    metric: str
    op: str
    value: float
    on_fail: str  # repeat | pivot | stop

    def __post_init__(self):
        if self.op not in OPS:
            raise ValueError(f"check {self.id}: unknown op {self.op!r}")
        if self.on_fail not in ("repeat", "pivot", "stop"):
            raise ValueError(f"check {self.id}: on_fail must be repeat, pivot or stop")


@dataclass
class GateResult:
    outcome: str  # go | repeat | pivot | stop
    reasons: list[str]
    metrics: dict
    attempt: int


def _criteria_path(ctx, phase: int):
    return ctx.out_dir / f"phase{phase}_gate_criteria.json"


def _hash(phase: int, checks: list[Check]) -> str:
    text = json.dumps({"phase": phase, "checks": [asdict(c) for c in checks]}, indent=2, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def preregister(ctx, phase: int, checks: list[Check]) -> str:
    digest = _hash(phase, checks)
    payload = {"phase": phase, "checks": [asdict(c) for c in checks], "sha256": digest,
               "note": "Written before the phase ran. The gate applies exactly these checks."}
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    _criteria_path(ctx, phase).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ctx.log.action("gate", f"preregister_gate_{phase}", criteria_sha256=digest, checks=len(checks))
    reg = ctx.extra.setdefault("_gate_checks", {})
    reg[phase] = list(checks)
    ctx.extra.setdefault("_gate_hashes", {})[phase] = digest
    return digest


def _load_checks(ctx, phase: int) -> tuple[list[Check], str | None]:
    checks = ctx.extra.get("_gate_checks", {}).get(phase)
    digest = ctx.extra.get("_gate_hashes", {}).get(phase)
    path = _criteria_path(ctx, phase)
    if checks is None and path.exists():  # e.g. evaluate in a new process
        payload = json.loads(path.read_text(encoding="utf-8"))
        checks = [Check(**c) for c in payload.get("checks", [])]
        digest = payload.get("sha256")
    checks = checks or []
    if digest is None and checks:
        digest = _hash(phase, checks)
    # Integrity: the checks applied must be the ones pre-registered on disk.
    if path.exists() and checks:
        on_disk = json.loads(path.read_text(encoding="utf-8")).get("sha256")
        if on_disk and on_disk != _hash(phase, checks):
            raise RuntimeError(f"gate {phase}: criteria changed after pre-registration")
    return checks, digest


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return "missing" if v is None else str(v)


def _would_change(ctx, phase: int, failed: list[tuple[Check, object]]) -> list[str]:
    lines = []
    for c, val in failed:
        if val is None:
            lines.append(f"`{c.metric}` was not measured (an artifact is missing); producing it and reaching "
                         f"{c.op} {_fmt(c.value)} would clear `{c.id}`.")
        else:
            lines.append(f"`{c.metric}` would need to be {c.op} {_fmt(c.value)} (it is {_fmt(val)}) to clear `{c.id}`.")
    # What the phase's own risk agents said would change their mind (skeptic, risk analyst).
    try:
        for name in ctx.store.names():
            if not name.startswith(f"phase{phase}_"):
                continue
            art = ctx.store.get(name)
            for w in (art.get("would_change_mind") or [])[:3] if isinstance(art, dict) else []:
                if isinstance(w, str) and w.strip():
                    lines.append(f"{w.strip()} (from `{name}`)")
    except Exception:  # noqa: BLE001 - the decision file must still be written
        pass
    return lines


def evaluate(ctx, phase: int, metrics: dict, attempt: int, max_repeats: int = 1) -> GateResult:
    """Score the metrics against the checks pre-registered for this phase and return go/repeat/pivot/stop.

    The most severe failed check wins (stop > pivot > repeat); a missing metric fails its check; a repeat at
    ``attempt >= max_repeats`` becomes stop. Writes phase<N>_gate_decision.md and logs action "gate_<N>"."""
    checks, digest = _load_checks(ctx, phase)
    outcome, reasons, rows, failed = "go", [], [], []
    for c in checks:
        val = metrics.get(c.metric)
        try:
            ok = val is not None and bool(OPS[c.op](val, c.value))
        except TypeError:
            ok = False
        rows.append((c, val, ok))
        if not ok:
            failed.append((c, val))
            reasons.append(f"{c.id}: {c.metric}={_fmt(val)} fails {c.op} {_fmt(c.value)} -> {c.on_fail}")
            if SEVERITY[c.on_fail] > SEVERITY[outcome]:
                outcome = c.on_fail
    if outcome == "repeat" and attempt >= max_repeats:
        reasons.append(f"repeat budget exhausted (attempt {attempt}, max repeats {max_repeats}) -> stop")
        outcome = "stop"
    halted = ctx.extra.get("halt_phase")
    if halted:
        reasons.insert(0, f"phase halted early: {halted}")
    result = GateResult(outcome=outcome, reasons=reasons, metrics=dict(metrics), attempt=attempt)

    md = [f"# Gate {phase} decision: **{outcome.upper()}**", "",
          f"System recommendation: {OUTCOME_TEXT[outcome]}",
          "The founder approves or overrides this recommendation; an override is logged.", ""]
    if getattr(ctx, "mock", False):
        md += ["> **MOCKED** run: metrics come from MockLLM and mock tools, not real evidence.", ""]
    md += [f"Attempt: {attempt} (max repeats {max_repeats})",
           f"Criteria hash (sha256, pre-registered before the phase ran): `{digest or 'none'}`", "",
           "## Checks", "", "| Check | Metric | Rule | Value | Result | On fail |", "|---|---|---|---|---|---|"]
    md += [f"| `{c.id}` | `{c.metric}` | {c.op} {_fmt(c.value)} | {_fmt(v)} | {'PASS' if ok else 'FAIL'} | {c.on_fail} |"
           for c, v, ok in rows] or ["| none | | | | | |"]
    md += ["", "## Reasons", ""] + ([f"- {r}" for r in reasons] or ["- all pre-registered checks passed"])
    md += ["", "## What would change this verdict", ""]
    md += [f"- {line}" for line in _would_change(ctx, phase, failed)] or [
        "- A failed check in a later run, or new evidence that triggers a kill criterion."]
    md += ["", "## Metrics (computed in code from the artifacts)", "", "```json",
           json.dumps(metrics, indent=2, default=str), "```", ""]
    (ctx.out_dir / f"phase{phase}_gate_decision.md").write_text("\n".join(md), encoding="utf-8")
    ctx.log.action("gate", f"gate_{phase}", outcome=outcome, reasons=reasons, metrics=metrics,
                   attempt=attempt, criteria_sha256=digest)
    return result
