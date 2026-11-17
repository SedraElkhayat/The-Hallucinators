# OWNER: M4
"""persevere_pivot_memo agent for Phase 6 Operate and Learn.

Synthesizes launch and operational metrics to recommend persevere, pivot, or stop.
"""
from __future__ import annotations

from agents.m4_common import M4Agent, supported_recommendations
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
        metrics = ctx.store.get("phase6_step2_metrics") if ctx.store.has("phase6_step2_metrics") else {}
        status = str((metrics.get("comparison") or {}).get("target_status", "unknown"))
        prov = str(metrics.get("provenance", "")).upper()
        rec = str(data.get("recommendation", "")).strip().lower()
        fallback = False
        supported = supported_recommendations(status, prov)
        if rec not in ("persevere", "pivot", "stop"):
            rec = supported[0]
            fallback = True
        elif rec not in supported:
            # The recommendation must be backed by the metrics (e.g. never persevere on a missed target or on
            # MOCKED numbers). Code applies the rule and keeps the model's choice visible.
            data["model_recommendation"] = rec
            data["overridden"] = (f"Code rule: with target {status} and {prov or 'unlabeled'} data the metrics back "
                                  f"{' or '.join(supported)}, not {rec}.")
            rec = supported[0]
        data["recommendation"] = rec
        data["supported_by_metrics"] = supported

        reasons = data.get("reasons")
        if not isinstance(reasons, list) or not reasons:
            data["reasons"] = [f"STUBBED: the model gave no reasons. Phase 6 result versus the Phase 2 target: {status}."]
            fallback = True
        experiments = data.get("experiments")
        if not isinstance(experiments, list) or not experiments:
            data["experiments"] = ["STUBBED: the model proposed no experiments; the founder defines the next test."]
            fallback = True
        data["experiments"] = data["experiments"][:3]
        data["evidence_status"] = status
        if prov in ("SAMPLE", "MOCKED"):
            # Demo inputs are SAMPLE/MOCKED: say so, never present them as real customers or feedback.
            label = f"[{prov} data]"
            data["reasons"] = [r if ("SAMPLE" in str(r).upper() or "MOCKED" in str(r).upper()) else f"{label} {r}"
                               for r in data["reasons"]]
            data["inputs_provenance"] = prov
        if fallback:
            data["stubbed"] = "Part of this memo was filled by a code rule because the model output was incomplete."
        data.pop("mocked", None)
        return data
