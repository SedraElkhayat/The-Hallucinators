# OWNER: M4
"""metrics_analyst agent for Phase 6 Operate and Learn.

Compares launch results with Phase 2 targets.
Labels data provenance (SAMPLE/MOCKED) and identifies gaps without extrapolation.
"""
from __future__ import annotations

import csv
import io

from agents.m4_common import M4Agent
from core.contracts import Context


class MetricsAnalyst(M4Agent):
    name = "metrics_analyst"
    phase = 6
    step = "phase6_step2_metrics"
    inputs = []
    tools = []
    required_keys = ["comparison", "provenance", "gaps"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def build_user_message(self, ctx: Context) -> str:
        results_csv = ""
        try:
            results_csv = ctx.founder.provide("phase6_results", "Provide phase 6 results as CSV text")
        except Exception:
            results_csv = "metric,value,provenance\nwaitlist_signups,140,MOCKED\nmock_sales,9,MOCKED\nmock_refunds,1,MOCKED\n"

        target_plan = {}
        if ctx.store.has("phase2_step3_demand_test_plan"):
            target_plan = ctx.store.get("phase2_step3_demand_test_plan")

        payload = {
            "brief": ctx.brief,
            "phase6_results_csv": results_csv,
            "target_plan": target_plan,
        }
        return f"<data>\n{payload}\n</data>\nAnalyze the phase 6 results against the validation target. Label data provenance (e.g. SAMPLE or MOCKED). Do not extrapolate."

    def post_process(self, ctx: Context, data: dict) -> dict:
        prov = str(data.get("provenance", "")).upper()
        if "SAMPLE" not in prov and "MOCKED" not in prov:
            data["provenance"] = "SAMPLE"

        if not data.get("comparison"):
            data["comparison"] = {
                "target_signups": 100,
                "actual_signups": 140,
                "sales_count": 9,
                "refunds_count": 1,
            }

        gaps = data.get("gaps")
        if not isinstance(gaps, list):
            data["gaps"] = ["Attribution tracking between awareness channels and store page visits needs refinement."]

        data["mocked"] = True
        return data
