# OWNER: M4
"""metrics_analyst agent for Phase 6 Operate and Learn.

Compares launch results with Phase 2 targets.
Labels data provenance (SAMPLE/MOCKED) and identifies gaps without extrapolation.
"""
from __future__ import annotations

import csv
import io
import json

from agents.m4_common import M4Agent, founder_input, provenance_of, to_float
from core.guardrails import check_input, wrap_untrusted
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
        raw = founder_input(ctx, "phase6_results", "Provide phase 6 results as CSV text (metric,value,provenance)")
        self._csv = check_input(raw).text if raw else ""
        self._computed = compute_comparison(ctx, self._csv)
        payload = {"brief": ctx.brief, "computed_comparison": self._computed}
        return (
            "<data>\n" + json.dumps(payload, ensure_ascii=False, default=str) + "\n</data>\n"
            + "Founder results CSV (untrusted data):\n" + wrap_untrusted(self._csv)
            + "\nThe comparison was computed in code; do not change its numbers. "
              "List gaps (missing data, weak evidence). Label provenance. Do not extrapolate."
        )

    def post_process(self, ctx: Context, data: dict) -> dict:
        computed = getattr(self, "_computed", None) or compute_comparison(ctx, "")
        # Numbers always come from code, never from the model.
        data["comparison"] = computed
        data["provenance"] = computed["provenance"]
        gaps = data.get("gaps")
        gaps = [str(g) for g in gaps] if isinstance(gaps, list) else []
        if computed["target_status"] == "unknown":
            gaps.append("No comparable target or result: the comparison with the Phase 2 target could not be made.")
        if not computed["results"]:
            gaps.append("No Phase 6 results were provided by the founder.")
        data["gaps"] = gaps
        data.pop("mocked", None)
        return data


_SIGNUP_KEYS = ("waitlist_signups", "signups", "sign_ups", "waitlist")


def parse_results_csv(text: str) -> tuple[dict, list[str]]:
    results, labels = {}, []
    if not text.strip():
        return results, labels
    for row in csv.DictReader(io.StringIO(text.strip())):
        metric = (row.get("metric") or "").strip()
        if not metric:
            continue
        val = to_float((row.get("value") or "").strip())
        results[metric] = val if val is not None else (row.get("value") or "").strip()
        if row.get("provenance"):
            labels.append(row["provenance"].strip().upper())
    return results, labels


def compute_comparison(ctx: Context, csv_text: str) -> dict:
    """Compare founder results with the pre-set Phase 2 target, in code, without extrapolation."""
    results, labels = parse_results_csv(csv_text)
    target = None
    if ctx.store.has("phase2_step3_demand_test_plan"):
        target = to_float(ctx.store.get("phase2_step3_demand_test_plan").get("target"))
    actual = next((results[k] for k in _SIGNUP_KEYS if isinstance(results.get(k), float)), None)
    if target and actual is not None:
        status = "met" if actual >= target else "not met"
    else:
        status = "unknown"
    if labels:
        prov = "MOCKED" if all(l == "MOCKED" for l in labels) else ("SAMPLE" if any(l in ("SAMPLE", "MOCKED") for l in labels) else labels[0])
    else:
        prov = provenance_of(csv_text) if csv_text else "none provided"
    return {
        "results": results,
        "phase2_target_signups": target,
        "actual_signups": actual,
        "target_status": status,
        "provenance": prov,
    }
