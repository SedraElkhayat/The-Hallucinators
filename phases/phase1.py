# OWNER: M2
"""Phase 1: Discover.

Sharpen the founder's idea, score it against alternatives, define the market, collect evidence with
quote-checked sources, design and analyse Mom Test interviews, and challenge the result.

Founder input keys used in this phase (CONTEXT.md 4a item 5):
- ``clarify_<field>`` for target_customer, problem, product_type, budget, time_per_week, founder_skills,
  monetization_idea, distribution_channel, differentiation, values_and_limits (clarifier)
- ``option_<field>`` approve one suggested option, or "none of these" (option_suggester)
- ``idea_choice`` only when the brief has no idea (idea_generator)
- ``interview_notes`` the founder's notes from real interviews; SAMPLE in demo runs (interview_analyst)

Gate 1 metrics (computed in code from the artifacts; a missing artifact leaves its metric missing, which
fails the check):
- scope_ok: 1 if phase1_step1_scope.is_digital is true, else 0
- verified_claims: unique (url, quote) claims with verified true across opportunities, market,
  demand_signals and competitors
- competitors_found: competitors with a name and an http(s) URL
- kill_triggered: skeptic kill criteria with triggered true
- open_must_fix: must_fix issues in the last critique
"""
from agents.m2_common import COMPETITORS, CRITIQUE, EVIDENCE_STEPS, SCOPE, SKEPTIC, get_artifact
from core.claims import count_verified
from gates import Check

PHASE = 1
STAGES: list[list[str]] = [
    ["scope_classifier"],
    ["clarifier"],
    ["option_suggester"],
    ["idea_generator"],
    ["idea_sharpener"],
    ["opportunity_finder", "market_scout", "demand_analyst", "competitor_scanner", "founder_fit",
     "mom_test_designer"],
    ["feasibility_analyst", "interview_analyst"],
    ["opportunity_scorer"],
    ["skeptic"],
    ["discover_synthesizer"],
    ["critic_phase1"],
]
REVISE = ("discover_synthesizer", "critic_phase1")
PIVOT_TO = None


def gate_checks(ctx) -> list[Check]:
    return [
        Check("scope_is_digital", "scope_ok", "==", 1, "stop"),
        Check("min_verified_claims", "verified_claims", ">=", 3, "repeat"),
        Check("min_competitors", "competitors_found", ">=", 2, "repeat"),
        Check("no_kill_criterion", "kill_triggered", "==", 0, "stop"),
        Check("no_open_must_fix", "open_must_fix", "==", 0, "repeat"),
    ]


def measure(ctx) -> dict:
    m: dict = {}
    scope = get_artifact(ctx, SCOPE)
    if scope is not None:
        m["scope_ok"] = 1 if scope.get("is_digital") is True else 0
    evidence = [a for a in (get_artifact(ctx, s) for s in EVIDENCE_STEPS) if a is not None]
    if evidence:
        m["verified_claims"] = count_verified(evidence)
    comp = get_artifact(ctx, COMPETITORS)
    if comp is not None:
        m["competitors_found"] = sum(
            1 for c in comp.get("competitors") or []
            if isinstance(c, dict) and str(c.get("name", "")).strip()
            and str(c.get("url", "")).lower().startswith(("http://", "https://")))
    sk = get_artifact(ctx, SKEPTIC)
    if sk is not None:
        m["kill_triggered"] = sum(1 for k in sk.get("kill_criteria") or []
                                  if isinstance(k, dict) and k.get("triggered") is True)
    crit = get_artifact(ctx, CRITIQUE)
    if crit is not None:
        m["open_must_fix"] = sum(1 for i in crit.get("issues") or []
                                 if isinstance(i, dict) and i.get("severity") == "must_fix")
    return m
