"""What happens after a STOP: the founder sees other directions instead of a dead end.

The alternatives are not invented here. They are the next-best ideas the Phase 1 scorer already ranked from the
evidence, so every option has its scores and reasons. The founder may pick one (the run restarts from Phase 1 with
that direction added to the brief, at most once) or stop. Nothing is chosen for the founder, and the choice is logged.
"""
from __future__ import annotations

STOP_HERE = "stop here"
MAX_ALTERNATIVES = 3
MAX_RESTARTS = 1


def build(ctx, phase: int, reasons: list[str]) -> dict:
    """Ranked alternatives (not the idea that just stopped) plus what would change the verdict."""
    ranked = []
    if ctx.store.has("phase1_step7_opportunity_scores"):
        scores = ctx.store.get("phase1_step7_opportunity_scores")
        chosen = scores.get("chosen")
        ranked = [r for r in scores.get("ranked", []) if isinstance(r, dict) and r.get("name") and r.get("name") != chosen]
    return {"phase": phase, "what_would_change_the_verdict": list(reasons), "alternatives": ranked[:MAX_ALTERNATIVES]}


def _markdown(data: dict, picked: str | None) -> str:
    md = [f"# Gate {data['phase']}: what you can do after a STOP", "",
          "A STOP is a recommendation, not the end. These are your options.", "",
          "## Checks that did not pass (meeting them would change the verdict)", ""]
    md += [f"- {r}" for r in data["what_would_change_the_verdict"]] or ["- (no reason recorded)"]
    md += ["", "## Other directions from the same evidence", ""]
    for i, a in enumerate(data["alternatives"], 1):
        why = "; ".join(str(x) for x in (a.get("reasons") or [])[:2])
        md.append(f"{i}. **{a['name']}** (score {a.get('score', '?')}). {why}")
    if not data["alternatives"]:
        md.append("No other idea was ranked in Phase 1. Describe a new direction in your brief and start again.")
    md += ["", f"Founder's choice: {picked or STOP_HERE}", ""]
    return "\n".join(md)


def _ask(ctx, phase: int, data: dict) -> str:
    names = [a["name"] for a in data["alternatives"]]
    listing = " ".join(f"{i}) {n}." for i, n in enumerate(names, 1))
    prompt = (f"The system recommends stopping at Gate {phase}. You do not have to end here. Other directions from the "
              f"same evidence: {listing} Pick one to start again from Phase 1, or choose '{STOP_HERE}'.")
    if getattr(ctx.founder, "mode", "") == "scripted":
        try:
            return str(ctx.founder.scripted.lookup(f"stop_alternative_{phase}")).strip()
        except KeyError:
            return STOP_HERE  # scripted demo files that do not mention it keep the old behavior
    return ctx.founder.ask(f"stop_alternative_{phase}", prompt, options=names + [STOP_HERE]).strip()


def offer(ctx, phase: int, reasons: list[str]) -> dict | None:
    """Write the alternatives file and let the founder pick one; returns the picked alternative or None."""
    data = build(ctx, phase, reasons)
    picked = None
    if data["alternatives"]:
        answer = _ask(ctx, phase, data)
        low = answer.lower()
        if low.isdigit() and 1 <= int(low) <= len(data["alternatives"]):
            picked = data["alternatives"][int(low) - 1]
        else:
            picked = next((a for a in data["alternatives"] if a["name"].lower() == low), None)
    ctx.store.put(f"phase{phase}_gate_alternatives", {**data, "founder_choice": picked["name"] if picked else STOP_HERE},
                  _markdown(data, picked["name"] if picked else None), agent="orchestrator")
    ctx.log.action("founder", f"stop_alternative_{phase}", approved_by="founder" if picked else None,
                   choice=picked["name"] if picked else STOP_HERE, options=[a["name"] for a in data["alternatives"]])
    return picked
