# OWNER: M1
"""State machine over the six phases: pre-register gate, run stages, revise, measure, evaluate, founder approval.

Usage:
  python orchestrator.py --brief demo/brief_strong.md [--through N] [--out outputs] [--mock-llm]
                         [--founder-inputs demo/founder_inputs.json] [--founder web|cli|scripted]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import gates
from agents import get_agent, has_agent
from approval import Approvals
from core import cost as cost_mod
from core.artifacts import ArtifactStore
from core.contracts import Context
from core.decision_log import DecisionLog
from core.founder import FounderInput, ScriptedInputs
from core.llm import make_client
from core.tools import ToolBroker
from phases import load_phase

ROOT = Path(__file__).resolve().parent
MAX_PIVOTS = 2
MAX_REVISE_ROUNDS = 2
MAX_ATTEMPTS = 2  # hard cap even with founder overrides


def build_context(brief: str, out_dir: Path, log_path: Path, mock: bool, founder_mode: str,
                  founder_inputs: Path | None, input_fn=input) -> Context:
    out_dir.mkdir(parents=True, exist_ok=True)
    log = DecisionLog(log_path)
    scripted = ScriptedInputs(founder_inputs) if founder_inputs else None
    if founder_mode == "scripted" and scripted is None:
        raise SystemExit("--founder scripted needs --founder-inputs")
    return Context(
        brief=brief, out_dir=out_dir, store=ArtifactStore(out_dir), llm=make_client(mock),
        tools=ToolBroker(log, mock=mock), log=log,
        approvals=Approvals(founder_mode, log, scripted=scripted, input_fn=input_fn),
        founder=FounderInput(founder_mode, log, scripted=scripted, input_fn=input_fn), mock=mock)


def run_agent(ctx: Context, name: str) -> bool:
    try:
        get_agent(name).run(ctx)
        return True
    except Exception as e:  # an agent failure must not kill the run; the gate sees the missing artifact
        ctx.log.action(name, "agent_error", error=f"{type(e).__name__}: {e}"[:500])
        return False


def run_stages(ctx: Context, mod) -> None:
    workers = max(1, int(os.getenv("ORCH_CONCURRENCY", "2")))
    for stage in mod.STAGES:
        if ctx.extra.get("halt_phase"):
            ctx.log.action("orchestrator", "stages_skipped_after_halt", phase=mod.PHASE, reason=ctx.extra["halt_phase"])
            return
        names = [n for n in stage if has_agent(n)]
        for n in set(stage) - set(names):
            ctx.log.action("orchestrator", "agent_missing", phase=mod.PHASE, missing=n)
        if len(names) == 1 or workers == 1:
            for n in names:
                run_agent(ctx, n)
        else:
            with ThreadPoolExecutor(min(workers, len(names))) as pool:
                list(pool.map(lambda n: run_agent(ctx, n), names))


def revise_loop(ctx: Context, mod) -> None:
    pair = getattr(mod, "REVISE", None)
    if not pair or ctx.extra.get("halt_phase"):
        return
    producer, critic = pair
    for rnd in range(1, MAX_REVISE_ROUNDS + 1):
        crit_step = get_agent(critic).step if has_agent(critic) else None
        if not crit_step or not ctx.store.has(crit_step):
            return
        critique = ctx.store.get(crit_step)
        if critique.get("verdict") != "revise":
            return
        ctx.log.action("orchestrator", "revise_round", phase=mod.PHASE, round=rnd)
        ctx.extra["critique"] = critique
        run_agent(ctx, producer)
        run_agent(ctx, critic)
    ctx.extra.pop("critique", None)


def write_pivot_notes(ctx: Context, reason: str) -> None:
    alt = None
    if ctx.store.has("phase1_step7_opportunity_scores"):
        scores = ctx.store.get("phase1_step7_opportunity_scores")
        chosen = scores.get("chosen")
        ranked = [r for r in scores.get("ranked", []) if r.get("name") != chosen]
        alt = ranked[0] if ranked else None
    data = {"reason": reason, "next_best_alternative": alt}
    ctx.store.put("pivot_notes", data, f"# Pivot notes\n\nReason: {reason}\n\nNext best alternative: {alt}\n",
                  agent="orchestrator")
    ctx.log.action("orchestrator", "pivot_notes", reason=reason)


def gate_summary(phase: int, res: gates.GateResult) -> str:
    lines = [f"Gate {phase} recommends: {res.outcome.upper()}", "", "Metrics:", json.dumps(res.metrics, indent=1),
             "", "Reasons:"] + ([f"- {r}" for r in res.reasons] or ["- all checks passed"])
    return "\n".join(lines)


def founder_gate(ctx: Context, phase: int, res: gates.GateResult) -> str:
    approved = ctx.approvals.request("gate", f"Gate {phase}: {res.outcome}", gate_summary(phase, res), phase,
                                     outcome=res.outcome)
    if approved:
        return res.outcome
    choice = ctx.founder.ask(f"gate_override_{phase}",
                             f"You rejected the Gate {phase} verdict '{res.outcome}'. What should happen?",
                             ["go", "repeat", "pivot", "stop"]).strip().lower()
    if choice not in gates.SEVERITY:
        choice = "stop"
    ctx.log.action("founder", f"gate_override_{phase}", approved_by="founder", outcome=choice,
                   system_outcome=res.outcome)
    write_override(ctx, phase, res, choice)
    return choice


def write_override(ctx: Context, phase: int, res: gates.GateResult, choice: str) -> None:
    """Make a founder override visible next to the gate decision it overrides."""
    path = ctx.out_dir / f"phase{phase}_gate_founder_override.md"
    md = [f"# Gate {phase}: founder override", "",
          f"The system recommended **{res.outcome.upper()}**. The founder rejected that verdict and chose "
          f"**{choice.upper()}** (logged as `gate_override_{phase}`, `approved_by: founder`, "
          f"`system_outcome: {res.outcome}` in decision_log.json)."
          + (" This is the same as the system's verdict, so nothing changed." if choice == res.outcome else ""), "",
          f"The system's verdict and its checks are unchanged in `phase{phase}_gate_decision.md`.", "",
          "Reasons the system gave:"] + ([f"- {r}" for r in res.reasons] or ["- (none)"]) + [""]
    prev = path.read_text(encoding="utf-8") + "\n---\n\n" if path.exists() else ""
    path.write_text(prev + "\n".join(md), encoding="utf-8")


def final_report(ctx: Context, phase: int, outcome: str, history: list) -> None:
    t = cost_mod.totals()
    run_cost, run_tokens = cost_mod.cost_per_run(ctx.log), cost_mod.tokens_per_run(ctx.log)
    md = [f"# Run summary: ended at Gate {phase} with **{outcome.upper()}**", "",
          f"Mode: {'MOCKED (MockLLM, offline)' if ctx.mock else 'real model'}", "",
          "| Phase | Attempt | Outcome |", "|---|---|---|"]
    md += [f"| {p} | {a} | {o} |" for p, a, o in history]
    overrides = [e for e in ctx.log.entries() if str(e.get("action", "")).startswith("gate_override_")]
    if overrides:
        md += ["", "Founder overrides (the founder rejected the system's gate verdict):", ""]
        md += [f"- Gate {e['action'].rsplit('_', 1)[-1]}: system {str(e.get('system_outcome')).upper()}, "
               f"founder chose {str(e.get('outcome')).upper()}" for e in overrides]
    md += ["", f"Model calls: {t['calls']}, tokens in {run_tokens['tokens_in']}, out {run_tokens['tokens_out']}, "
               f"cost per run ${run_cost:.4f}", ""]
    (ctx.out_dir / f"phase{phase}_gate_final_report.md").write_text("\n".join(md), encoding="utf-8")
    ctx.log.action("orchestrator", "run_finished", outcome=outcome, phase=phase, cost=round(t["cost"], 6),
                   tokens_in=t["tokens_in"], tokens_out=t["tokens_out"], calls=t["calls"])


def run(ctx: Context, through: int = 6, start: int = 1) -> dict:
    cost_mod.reset()
    ctx.log.action("orchestrator", "run_started", mock=ctx.mock, through=through)
    phase, attempts, pivots, history = start, {}, 0, []
    outcome = "go"
    while phase <= through:
        mod = load_phase(phase)
        attempt = attempts.get(phase, 0)          # 0-based: first run is attempt 0
        attempts[phase] = attempt + 1
        if attempt > MAX_ATTEMPTS:
            ctx.log.action("orchestrator", "attempt_cap_reached", phase=phase)
            outcome = "stop"
            break
        ctx.extra.pop("halt_phase", None)
        # fresh tool budget per gate attempt: a REPEAT round must be able to search again
        if hasattr(ctx.tools, "reset_budget"):
            ctx.tools.reset_budget(f"phase {phase} attempt {attempt}")
        gates.preregister(ctx, phase, mod.gate_checks(ctx))
        if not mod.STAGES:
            ctx.log.action("orchestrator", "phase_stubbed", phase=phase, note="STUBBED: no agents yet")
        run_stages(ctx, mod)
        revise_loop(ctx, mod)
        metrics = mod.measure(ctx)
        res = gates.evaluate(ctx, phase, metrics, attempt=attempt)
        outcome = founder_gate(ctx, phase, res)
        history.append((phase, attempt, outcome))
        if outcome == "go":
            phase += 1
        elif outcome == "repeat":
            continue
        elif outcome == "pivot":
            target = getattr(mod, "PIVOT_TO", None)
            if target is None or pivots >= MAX_PIVOTS:
                outcome = "stop"
                ctx.log.action("orchestrator", "pivot_unavailable", phase=phase)
                break
            pivots += 1
            write_pivot_notes(ctx, "; ".join(res.reasons) or "gate pivot")
            for p in range(target, phase + 1):
                attempts.pop(p, None)
            phase = target
        else:
            break
    final_phase = min(phase, through)
    final_report(ctx, final_phase, outcome, history)
    return {"outcome": outcome, "phase": final_phase, "history": history}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--through", type=int, default=6)
    ap.add_argument("--out", default=None, help="default runs/<id>/outputs; 'outputs' only for the final demo run")
    ap.add_argument("--mock-llm", action="store_true")
    ap.add_argument("--founder-inputs", default=None)
    ap.add_argument("--founder", choices=["web", "cli", "scripted"], default=None)
    a = ap.parse_args(argv)

    founder_mode = a.founder or ("scripted" if a.founder_inputs else "cli")
    if a.out:
        out_dir = Path(a.out)
    else:
        rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
        out_dir = ROOT / "runs" / rid / "outputs"
    log_path = out_dir.parent / "decision_log.json"  # outputs/ -> repo-root decision_log.json
    brief = Path(a.brief).read_text(encoding="utf-8")
    ctx = build_context(brief, out_dir, log_path, a.mock_llm, founder_mode,
                        Path(a.founder_inputs) if a.founder_inputs else None)
    result = run(ctx, through=a.through)
    print(json.dumps({"out_dir": str(out_dir), "decision_log": str(log_path), **result}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
