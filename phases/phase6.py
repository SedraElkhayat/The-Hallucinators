# OWNER: M4
"""Phase 6: Operate and Learn (support replies, metrics analysis, persevere-or-pivot memo).

Founder keys used in this phase:
- "support_questions" (founder provides customer support questions)
- "phase6_results" (founder provides operational results as CSV text)
"""
from __future__ import annotations

from core.contracts import Context
from agents.m4_common import supported_recommendations
from gates import Check

PHASE = 6
STAGES: list[list[str]] = [
    ["support_drafter"],
    ["metrics_analyst"],
    ["persevere_pivot_memo"],
]
REVISE = None
PIVOT_TO = None


def gate_checks(ctx: Context) -> list[Check]:
    return [
        Check("chk_p6_inputs_labeled", "inputs_labeled", ">=", 1.0, "repeat"),
        Check("chk_p6_memo_written", "memo_written", ">=", 1.0, "repeat"),
        Check("chk_p6_memo_backed", "memo_backed_by_metrics", ">=", 1.0, "repeat"),
    ]


def measure(ctx: Context) -> dict:
    inputs_labeled = 0
    if ctx.store.has("phase6_step2_metrics"):
        m_data = ctx.store.get("phase6_step2_metrics")
        prov = str(m_data.get("provenance", "")).upper()
        # Labeled = provenance is stated (SAMPLE, MOCKED or FOUNDER-PROVIDED), never blank.
        if prov and prov != "NONE PROVIDED":
            inputs_labeled = 1

    memo_written = 0
    memo_backed = 0
    if ctx.store.has("phase6_step3_persevere_pivot_memo"):
        memo_data = ctx.store.get("phase6_step3_persevere_pivot_memo")
        rec = str(memo_data.get("recommendation", "")).lower()
        if rec in ("persevere", "pivot", "stop"):
            memo_written = 1
        m = ctx.store.get("phase6_step2_metrics") if ctx.store.has("phase6_step2_metrics") else {}
        status = (m.get("comparison") or {}).get("target_status", "unknown")
        if rec in supported_recommendations(status, m.get("provenance", "")):
            memo_backed = 1

    return {
        "inputs_labeled": inputs_labeled,
        "memo_written": memo_written,
        "memo_backed_by_metrics": memo_backed,
    }
