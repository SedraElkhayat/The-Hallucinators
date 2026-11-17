# OWNER: M3
"""Phase 2: Validate (Lean Canvas, demand test against a pre-set target, scorecard, report).

Founder input keys used in this phase (CONTEXT.md section 4a item 5):
- ``demand_results``: JSON text ``{"signups": int, "days": int, "provenance": "REAL"|"MOCKED"}``,
  read by ``agents/demand_results.py``. Invalid input is asked again once, then recorded as
  0 sign-ups labeled MOCKED.
Approvals requested in this phase:
- ``landing_page`` (``agents/landing_page_builder.py``): the HTML draft; a rejection sets
  ``ctx.extra["halt_phase"]`` so the orchestrator skips to the gate.

Gate 2 metrics are computed in code from the artifacts by ``measure()``; the checks in
``gate_checks()`` are pre-registered before the phase runs (CONTEXT.md section 6).
"""
from gates import Check

PHASE = 2
STAGES = [
    ["competitor_analyst"],
    ["lean_canvas_drafter"],
    ["demand_test_designer"],
    ["landing_page_builder"],
    ["demand_results"],
    ["assumption_auditor"],
    ["risk_analyst"],
    ["scorecard_builder"],
    ["validation_synthesizer"],
    ["critic_phase2"],
]
REVISE = ("validation_synthesizer", "critic_phase2")
PIVOT_TO = 1

SCORECARD = "phase2_step8_scorecard"
PLAN = "phase2_step3_demand_test_plan"
RESULTS = "phase2_step5_demand_results"
RISKS = "phase2_step7_risks"
CRITIQUE = "phase2_step9_critique"
DIMENSIONS = ("problem_severity", "demand_evidence", "competition", "founder_fit", "feasibility", "monetization")


def gate_checks(ctx) -> list:
    return [
        Check("demand_known", "demand_unknown", "==", 0, "repeat"),
        Check("no_weak_dimension", "any_weak_dimension", "==", 0, "pivot"),
        Check("at_most_one_weak", "weak_count", "<=", 1, "stop"),
        Check("at_most_two_unknown", "unknown_count", "<=", 2, "repeat"),
        Check("demand_ratio_above_0_2", "demand_ratio", ">=", 0.2, "stop"),
        Check("demand_ratio_above_0_5", "demand_ratio", ">=", 0.5, "pivot"),
        Check("demand_ratio_reaches_target", "demand_ratio", ">=", 1.0, "repeat"),
        Check("no_kill_criterion", "kill_triggered", "==", 0, "stop"),
        Check("no_open_must_fix", "open_must_fix", "==", 0, "repeat"),
    ]


def _get(ctx, step):
    try:
        if hasattr(ctx.store, "has") and not ctx.store.has(step):
            return None
        data = ctx.store.get(step)
    except (KeyError, FileNotFoundError):
        return None
    return data if isinstance(data, dict) else None


def effective_ratings(scorecard: dict) -> dict:
    """Rating per dimension; anything other than unknown with no evidence_refs counts as unknown."""
    dims = (scorecard or {}).get("dimensions") or {}
    out = {}
    for d in DIMENSIONS:
        v = dims.get(d) if isinstance(dims.get(d), dict) else {}
        rating = str(v.get("rating", "unknown")).lower()
        refs = [r for r in (v.get("evidence_refs") or []) if str(r).strip()]
        if rating not in ("strong", "adequate", "weak", "unknown") or not refs:
            rating = "unknown"
        out[d] = rating
    return out


def measure(ctx) -> dict:
    """Gate 2 metrics from the artifacts. A metric whose artifact is missing is left out (its check fails)."""
    m = {}
    card = _get(ctx, SCORECARD)
    if card is not None:
        ratings = effective_ratings(card)
        weak = sum(1 for r in ratings.values() if r == "weak")
        m["demand_unknown"] = 1 if ratings["demand_evidence"] == "unknown" else 0
        m["weak_count"] = weak
        m["any_weak_dimension"] = 1 if weak else 0
        m["unknown_count"] = sum(1 for r in ratings.values() if r == "unknown")
    plan, results = _get(ctx, PLAN), _get(ctx, RESULTS)
    if plan is not None and results is not None:
        target = plan.get("target")
        signups = results.get("signups")
        if isinstance(target, int) and not isinstance(target, bool) and target > 0 \
                and isinstance(signups, int) and not isinstance(signups, bool) and signups >= 0:
            m["demand_ratio"] = round(signups / target, 4)
    risks = _get(ctx, RISKS)
    if risks is not None:
        m["kill_triggered"] = sum(1 for k in risks.get("kill_criteria") or []
                                  if isinstance(k, dict) and k.get("triggered") is True)
    critique = _get(ctx, CRITIQUE)
    if critique is not None:
        m["open_must_fix"] = sum(1 for i in critique.get("issues") or []
                                 if isinstance(i, dict) and str(i.get("severity", "")).lower() == "must_fix")
    return m
