# OWNER: M4
"""persevere_pivot_memo agent for Phase 6 Operate and Learn.

Synthesizes launch and operational metrics to recommend persevere, pivot, or stop.
"""
from __future__ import annotations

from agents.m4_common import M4Agent
from core.contracts import Context


class PerseverePivotMemo(M4Agent):
    name = "persevere_pivot_memo"
    phase = 6
    step = "phase6_step3_persevere_pivot_memo"
    inputs = ["phase6_step2_metrics", "phase2_step9_validation_report"]
    tools = []
    required_keys = ["recommendation", "reasons", "experiments"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def post_process(self, ctx: Context, data: dict) -> dict:
        rec = str(data.get("recommendation", "persevere")).strip().lower()
        if rec not in ("persevere", "pivot", "stop"):
            rec = "persevere"
        data["recommendation"] = rec

        reasons = data.get("reasons")
        if not isinstance(reasons, list) or not reasons:
            data["reasons"] = [
                "Phase 2 demand targets were met or exceeded.",
                "Simulated sales show healthy initial interest.",
                "Refund rates remain within acceptable bounds.",
            ]

        experiments = data.get("experiments")
        if not isinstance(experiments, list) or not experiments:
            data["experiments"] = [
                "Test targeted design creator affiliate partnerships.",
                "Produce YouTube workflow tutorial in Arabic.",
            ]
        data["experiments"] = data["experiments"][:3]
        data["mocked"] = True
        return data
