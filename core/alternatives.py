"""What happens after a STOP: the founder sees other directions instead of a dead end.

The alternatives are not invented here. They are the next-best ideas the Phase 1 scorer already ranked from the
evidence, so every option has its scores and reasons. The founder may pick one (the run restarts from Phase 1 with
that direction added to the brief, at most once) or stop. Nothing is chosen for the founder, and the choice is logged
with who made it: WEB, CLI, SCRIPTED, or SCRIPTED_DEFAULT when a demo file has no answer and the run simply stops.
"""
from __future__ import annotations

import re

STOP_HERE = "stop here"
MAX_ALTERNATIVES = 3
MAX_RESTARTS = 1
STOP_WORDS = {"stop", "stop here", "end", "end here", "no", "none", "no thanks", "none of these", "i don't know",
              "i dont know", "unknown"}
FILLER = {"a", "an", "the", "for", "and", "of", "to", "in", "on", "with", "try", "pick", "choose", "take", "go",
          "please", "i", "want", "one", "that", "this", "it", "my"}


def build(ctx, phase: int, reasons: list[str]) -> dict:
    """Ranked alternatives (not the idea that just stopped) plus the checks that did not pass."""
    ranked = []
    if ctx.store.has("phase1_step7_opportunity_scores"):
        scores = ctx.store.get("phase1_step7_opportunity_scores")
        chosen = scores.get("chosen")
        ranked = [r for r in scores.get("ranked", []) if isinstance(r, dict) and r.get("name") and r.get("name") != chosen]
    return {"phase": phase, "what_would_change_the_verdict": list(reasons), "alternatives": ranked[:MAX_ALTERNATIVES]}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in FILLER}


def match_alternative(answer: str, names: list[str]) -> int | None:
    """Index of the direction the founder meant: its number, its exact name, a unique part of its name, or the one
    sharing the most words (at least two) with what was typed, or the only one containing all of them. None when nothing clearly matches."""
    low = (answer or "").strip().lower()
    if not low:
        return None
    if low.isdigit():
        return int(low) - 1 if 1 <= int(low) <= len(names) else None
    lowered = [n.lower() for n in names]
    if low in lowered:
        return lowered.index(low)
    if len(low) >= 4:
        hits = [i for i, n in enumerate(lowered) if low in n or n in low]
        if len(hits) == 1:
            return hits[0]
    typed = _tokens(low)
    holders = [i for i, n in enumerate(names) if typed and typed <= _tokens(n)]
    if len(holders) == 1:
        return holders[0]
    scores = [len(typed & _tokens(n)) for n in names]
    best = max(scores, default=0)
    if best >= 2 and scores.count(best) == 1:
        return scores.index(best)
    return None


def _markdown(data: dict, choice: str) -> str:
    md = [f"# Gate {data['phase']}: what you can do after a STOP", "",
          "A STOP is a recommendation, not the end. These are your options.", "",
          "## Checks that did not pass (meeting them would change the verdict)", ""]
    md += [f"- {r}" for r in data["what_would_change_the_verdict"]] or ["- (no reason recorded)"]
    md += ["", "## Other directions from the same evidence", ""]
    for i, a in enumerate(data["alternatives"], 1):
        why = "; ".join(str(x) for x in (a.get("reasons") or [])[:2])
        md.append(f"{i}. **{a['name']}** (score {a.get('score', '?')}). {why}")
    if data["alternatives"]:
        md += ["", "These scores come from the same Phase 1 evidence. Where need or market says unknown, no evidence "
                   "was found for that idea either, so treat them as starting points to research, not as better "
                   "bets. Some may be the same idea in different words."]
    else:
        md.append("No other idea was ranked in Phase 1. Describe a new direction in your brief and start again.")
    md += ["", f"Founder's choice: {choice}", ""]
    return "\n".join(md)


def _provenance(ctx) -> str:
    return {"web": "WEB", "cli": "CLI", "scripted": "SCRIPTED"}.get(getattr(ctx.founder, "mode", ""), "")


def _ask(ctx, phase: int, data: dict, retry: str | None = None) -> tuple[str, str]:
    """Ask which direction to try. Returns (answer, who answered)."""
    key, names = f"stop_alternative_{phase}", [a["name"] for a in data["alternatives"]]
    if getattr(ctx.founder, "mode", "") == "scripted":
        try:
            return str(ctx.founder.scripted.lookup(key)).strip(), "SCRIPTED"
        except KeyError:
            return STOP_HERE, "SCRIPTED_DEFAULT"  # the demo file has no answer for this question: the run keeps stopping
    listing = " ".join(f"{i}) {n}." for i, n in enumerate(names, 1))
    sorry = f"I did not understand “{retry.strip()[:40]}”. " if retry else ""
    prompt = (f"{sorry}The system recommends stopping at checkpoint {phase}. You do not have to end here. Other "
              f"directions from the same evidence: {listing} Pick one to start again from Phase 1, or choose "
              f"'{STOP_HERE}'.")
    return str(ctx.founder.ask(key, prompt, options=names + [STOP_HERE])).strip(), _provenance(ctx)


def offer(ctx, phase: int, reasons: list[str], can_restart: bool = True) -> dict | None:
    """Write the alternatives file and, when a restart is still allowed, let the founder pick one.

    Returns the picked alternative or None. An answer that is neither a direction nor a way of saying stop is asked
    again once; the question is never asked when the restart has already been used (the pick could not be honored).
    """
    data = build(ctx, phase, reasons)
    names = [a["name"] for a in data["alternatives"]]
    picked, provenance, asked = None, "", False
    if names and can_restart:
        answer, provenance = _ask(ctx, phase, data)
        asked = provenance != "SCRIPTED_DEFAULT"  # a demo file with no answer means nobody was asked
        idx = match_alternative(answer, names)
        if idx is None and answer.strip().lower() not in STOP_WORDS and not provenance.startswith("SCRIPTED"):
            answer, provenance = _ask(ctx, phase, data, retry=answer)
            idx = match_alternative(answer, names)
        picked = data["alternatives"][idx] if idx is not None else None
    if picked:
        choice = picked["name"]
    elif not names:
        choice = "none (no other idea was ranked, so nobody was asked)"
    elif not can_restart:
        choice = "none (one other direction was already tried in this run, so nobody was asked and the run ends here)"
    elif provenance == "SCRIPTED_DEFAULT":
        choice = f"{STOP_HERE} (the scripted demo file has no answer for this question, so the run stops)"
    else:
        choice = STOP_HERE
    ctx.store.put(f"phase{phase}_gate_alternatives",
                  {**data, "founder_choice": picked["name"] if picked else STOP_HERE, "founder_choice_note": choice},
                  _markdown(data, choice), agent="orchestrator")
    ctx.log.action("founder", f"stop_alternative_{phase}", approved_by="founder" if picked else None,
                   choice=picked["name"] if picked else STOP_HERE, options=names, asked=asked,
                   **({"provenance": provenance} if provenance else {}))
    return picked
