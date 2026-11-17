# OWNER: M1
"""Turns a run's decision log into a conversation for the founder UI (presentation only).

Nothing here changes what the pipeline does: it reads the run's decision log, gate criteria and
artifacts, and describes them in plain language. Internal names stay in the audit trail page.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PHASES = {
    1: ("Discover", "I'll sharpen your idea, look for real evidence that people want it, and check the competition."),
    2: ("Validate", "Next I'll draft the business on one page and test demand against a target set before the test."),
    3: ("Build", "Now I'll build a first version of the website and test it."),
    4: ("Commercial setup", "Time to set a price and draft the policies. No payments are taken."),
    5: ("Launch", "I'll prepare the store page and launch posts as drafts, and run the mocked order flow."),
    6: ("Operate and learn", "Last, I'll draft support replies, compare results with the targets, and recommend what to do next."),
}

# agent -> (what it is doing, what it did)
AGENTS = {
    "scope_classifier": ("Checking the idea is a digital product we can work on", "Checked the product type"),
    "clarifier": ("Working out what I still need to know about your idea", "Asked about missing details"),
    "option_suggester": ("Suggesting options for the details you left open", "Suggested options for open details"),
    "idea_generator": ("Looking at the idea you chose", "Recorded your idea"),
    "idea_sharpener": ("Turning your brief into an idea card", "Wrote the idea card"),
    "opportunity_finder": ("Looking for alternative ideas in the same space", "Found alternative ideas"),
    "market_scout": ("Researching the market", "Researched the market"),
    "demand_analyst": ("Looking for signs people already pay for this", "Looked for demand signals"),
    "competitor_scanner": ("Scanning competitors and what they charge", "Scanned competitors"),
    "founder_fit": ("Comparing the idea with your skills and time", "Rated founder fit"),
    "mom_test_designer": ("Writing customer interview questions", "Wrote the interview script"),
    "feasibility_analyst": ("Estimating the effort to build it", "Estimated feasibility"),
    "interview_analyst": ("Reading your interview notes", "Analysed the interview notes"),
    "opportunity_scorer": ("Ranking your idea against the alternatives", "Ranked the options"),
    "skeptic": ("Arguing against the idea to find the risks", "Listed risks and kill criteria"),
    "discover_synthesizer": ("Writing the discovery report", "Wrote the discovery report"),
    "critic_phase1": ("Reviewing the report for unsupported claims", "Reviewed the discovery report"),
    "competitor_analyst": ("Analysing the competition in depth", "Analysed the competition"),
    "lean_canvas_drafter": ("Drafting the lean canvas", "Drafted the lean canvas"),
    "demand_test_designer": ("Designing the demand test", "Set the demand-test target"),
    "landing_page_builder": ("Building the test landing page", "Built the landing page draft"),
    "demand_results": ("Recording the demand-test results", "Recorded the demand results"),
    "assumption_auditor": ("Listing every assumption", "Listed the assumptions"),
    "risk_analyst": ("Looking for the biggest risks", "Listed the risks"),
    "scorecard_builder": ("Scoring the idea on six dimensions", "Built the scorecard"),
    "validation_synthesizer": ("Writing the validation report", "Wrote the validation report"),
    "critic_phase2": ("Reviewing the validation report", "Reviewed the validation report"),
    "spec_writer": ("Writing the product spec and its tests", "Wrote the spec"),
    "copywriter": ("Writing the website copy", "Wrote the website copy"),
    "builder": ("Building the website", "Built the website"),
    "user_docs_writer": ("Writing the user guide", "Wrote the user guide"),
    "qa_agent": ("Testing the website", "Tested the website"),
    "content_reviewer": ("Checking the website for anything dishonest", "Reviewed the content"),
    "pricing_analyst": ("Working out a price from comparable products", "Set the price"),
    "offer_packager": ("Packaging the offer", "Packaged the offer"),
    "policy_drafter": ("Drafting terms, privacy and refund policies", "Drafted the policies"),
    "compliance_reviewer_phase4": ("Reviewing the offer and policies", "Reviewed the offer and policies"),
    "channel_planner": ("Choosing launch channels", "Chose launch channels"),
    "store_page_builder": ("Building the store page", "Built the store page"),
    "launch_post_drafter": ("Drafting launch posts", "Drafted launch posts"),
    "compliance_reviewer_phase5": ("Reviewing the launch drafts", "Reviewed the launch drafts"),
    "sale_to_cash": ("Running the mocked order flow", "Ran the mocked order flow"),
    "support_drafter": ("Drafting support replies", "Drafted support replies"),
    "metrics_analyst": ("Comparing results with the targets", "Compared results with targets"),
    "persevere_pivot_memo": ("Writing the persevere-or-pivot memo", "Wrote the recommendation memo"),
}

APPROVAL_KINDS = {"landing_page": "the landing page draft", "store_page": "the store page",
                  "launch_post": "a launch post", "gate": "the gate verdict"}
OUTCOME_WORDS = {"go": "Go on", "repeat": "Repeat this phase", "pivot": "Pivot", "stop": "Stop"}
OP_WORDS = {">=": "at least", "<=": "at most", "==": "exactly", ">": "more than", "<": "less than"}
INTERNAL_AGENTS = {"gate", "orchestrator", "approval", "founder", "system:tool_broker"}


def doing(agent: str) -> str:
    return AGENTS.get(agent, (agent.replace("_", " ").capitalize(), ""))[0]


def done(agent: str) -> str:
    return AGENTS.get(agent, ("", agent.replace("_", " ").capitalize()))[1]


def brief_title(text: str) -> str:
    """A short title for a run: the starting idea if the brief names one, else its first real line."""
    m = re.search(r"\*\*Starting idea:\*\*\s*(.+)", text or "")
    line = m.group(1) if m else next((l for l in (text or "").splitlines()
                                      if l.strip() and not l.lstrip().startswith("#")), (text or "").strip())
    line = re.sub(r"[*_#`]", "", line).strip()
    return line if len(line) <= 90 else line[:87].rsplit(" ", 1)[0] + "…"


def humanize_key(key: str) -> str:
    key = re.sub(r"^(clarify|option)_", "", key)
    return key.replace("_", " ")


def _step_for(agent: str) -> str | None:
    try:
        from agents import get_agent
        return get_agent(agent).step
    except Exception:
        return None


def _short(data: dict) -> str:
    for k in ("summary", "value_proposition", "recommendation", "reasoning", "positioning", "hypothesis", "findings"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            v = re.sub(r"\s+", " ", v).strip()
            return v if len(v) < 220 else v[:217].rsplit(" ", 1)[0] + "…"
    return ""


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).removeprefix("www.") if m else url


def _criteria(out_dir: Path, phase: int) -> list[dict]:
    p = out_dir / f"phase{phase}_gate_criteria.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("checks", [])
    except Exception:
        return []


def _ruler(check: dict, metrics: dict) -> dict:
    """One pre-registered rule against its measured value, for the verdict ruler."""
    val = metrics.get(check.get("metric"))
    target = check.get("value")
    op = check.get("op")
    ok = None
    if isinstance(val, (int, float)) and isinstance(target, (int, float)):
        ok = {">=": val >= target, "<=": val <= target, "==": val == target,
              ">": val > target, "<": val < target}.get(op)
    span = max(abs(float(target or 0)) * 2, abs(float(val)) * 1.15 if isinstance(val, (int, float)) else 0, 1.0)
    pos = lambda x: max(0.0, min(100.0, float(x) / span * 100)) if isinstance(x, (int, float)) else None
    if isinstance(target, float) and target.is_integer():
        target = int(target)
    return {"name": check.get("metric", "").replace("_", " "), "op": OP_WORDS.get(op, op), "target": target, "value": val,
            "ok": ok, "on_fail": check.get("on_fail"), "target_pos": pos(target), "value_pos": pos(val)}


def build_feed(run: dict, answers: dict[str, str]) -> list[dict]:
    """Blocks for the conversation: user, phase, thinking, gate, note, site, finished."""
    ctx = run["ctx"]
    out_dir = Path(ctx.out_dir)
    rid = run["id"]
    blocks: list[dict] = [{"type": "user", "text": ctx.brief.strip()}]
    thinking: dict | None = None
    phase = 0
    site_index = None

    def close():
        nonlocal thinking
        if thinking and thinking["steps"]:
            blocks.append(thinking)
        thinking = None

    def think():
        nonlocal thinking
        if thinking is None:
            thinking = {"type": "thinking", "steps": [], "first": None, "last": None, "phase": phase}
        return thinking

    for e in ctx.log.entries():
        a, agent = e["action"], e["agent"]
        m = re.match(r"preregister_gate_(\d+)$", a)
        if m:
            close()
            phase = int(m.group(1))
            name, intro = PHASES.get(phase, (f"Phase {phase}", ""))
            rules = [_ruler(c, {}) for c in _criteria(out_dir, phase)]
            blocks.append({"type": "phase", "n": phase, "name": name, "intro": intro, "rules": rules})
            continue
        m = re.match(r"gate_(\d+)$", a)
        if m and agent == "gate":
            close()
            n = int(m.group(1))
            metrics = e.get("metrics") or {}
            blocks.append({"type": "gate", "n": n, "outcome": e.get("outcome", ""),
                           "word": OUTCOME_WORDS.get(e.get("outcome", ""), e.get("outcome", "")),
                           "reasons": [re.sub(r"^[\w_]+: ", "", r) for r in e.get("reasons", [])],
                           "rulers": [_ruler(c, metrics) for c in _criteria(out_dir, n)],
                           "link": f"/artifact/phase{n}_gate_decision?run={rid}", "decision": None})
            continue
        if a in ("approved:gate", "rejected:gate"):
            for b in reversed(blocks):
                if b["type"] == "gate":
                    b["decision"] = "accepted" if a.startswith("approved") else "rejected"
                    break
            continue
        m = re.match(r"gate_override_(\d+)$", a)
        if m and agent == "founder":
            close()
            blocks.append({"type": "note", "tone": "founder",
                           "text": f"You overrode Gate {m.group(1)}: the system said "
                                   f"“{OUTCOME_WORDS.get(e.get('system_outcome'), e.get('system_outcome'))}”, "
                                   f"you chose “{OUTCOME_WORDS.get(e.get('outcome'), e.get('outcome'))}”. This is logged."})
            continue
        m = re.match(r"(approved|rejected):(\w+)$", a)
        if m and agent == "founder":
            close()
            what = APPROVAL_KINDS.get(m.group(2), m.group(2).replace("_", " "))
            blocks.append({"type": "note", "tone": "founder",
                           "text": f"You {m.group(1)} {what}." + (" Nothing was published: you publish it yourself."
                                                                  if m.group(1) == "approved" else "")})
            continue
        if a.startswith("founder_input:"):
            close()
            key = a.split(":", 1)[1]
            val = answers.get(key)
            blocks.append({"type": "answer", "label": humanize_key(key), "text": val,
                           "scripted": e.get("provenance") == "SCRIPTED"})
            continue
        if a == "run_finished":
            close()
            blocks.append({"type": "finished", "outcome": e.get("outcome"), "phase": e.get("phase"),
                           "tokens": (e.get("tokens_in") or 0) + (e.get("tokens_out") or 0),
                           "cost": e.get("cost") or 0})
            continue
        if agent in INTERNAL_AGENTS:
            continue
        t = think()
        t["first"] = t["first"] or e["timestamp"]
        t["last"] = e["timestamp"]
        if a == "search":
            t["steps"].append({"kind": "search", "text": f"Searched for “{e.get('query', '')}”",
                               "detail": ", ".join(_host(u) for u in e.get("sources", [])[:3])})
        elif a == "fetch":
            src = (e.get("sources") or [""])[0]
            t["steps"].append({"kind": "read", "text": f"Read {_host(src)}", "url": src})
        elif a == "agent_error":
            t["steps"].append({"kind": "error", "text": f"{doing(agent)}: this step failed",
                               "detail": str(e.get("error", ""))[:200]})
        elif a == "claim_downgraded":
            t["steps"].append({"kind": "check", "text": "A claim could not be confirmed on its source, so it is marked as an assumption"})
        elif a in ("guardrail_block", "guardrail_drop"):
            t["steps"].append({"kind": "check", "text": "A safety check removed text that broke the rules",
                               "detail": ", ".join(e.get("reasons", []))})
        elif a.startswith("run_") or a in ("record_demand_results", "record_idea_choice", "run_acceptance_tests"):
            step = _step_for(agent)
            summary, link = "", None
            if step and (out_dir / f"{step}.json").exists():
                try:
                    summary = _short(json.loads((out_dir / f"{step}.json").read_text(encoding="utf-8")))
                except Exception:
                    summary = ""
                link = f"/artifact/{step}?run={rid}"
            t["steps"].append({"kind": "done", "text": done(agent), "summary": summary, "link": link,
                               "model": e.get("model")})
            if agent in ("builder", "store_page_builder"):
                site_index = True
        elif a == "store_site_written":
            site_index = True
    close()
    merged: list[dict] = []
    for b in blocks:
        if b["type"] == "answer" and merged and merged[-1]["type"] == "answers":
            merged[-1]["items"][b["label"]] = b
        elif b["type"] == "answer":
            merged.append({"type": "answers", "items": {b["label"]: b}})
        else:
            merged.append(b)
    blocks = merged
    if site_index:
        pos = next((i for i, b in enumerate(blocks) if b["type"] == "gate" and b["n"] >= 3), len(blocks))
        blocks.insert(pos, {"type": "site"})
    for b in blocks:
        if b["type"] == "thinking":
            b["label"] = _thinking_label(b)
    return blocks


def _thinking_label(b: dict) -> str:
    from datetime import datetime
    n = sum(1 for s in b["steps"] if s["kind"] == "done")
    searches = sum(1 for s in b["steps"] if s["kind"] == "search")
    errors = sum(1 for s in b["steps"] if s["kind"] == "error")
    try:
        f = lambda t: datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
        secs = int((f(b["last"]) - f(b["first"])).total_seconds())
    except Exception:
        secs = 0
    took = f"{secs // 60} min" if secs >= 60 else (f"{secs} s" if secs else "")
    if n == 1 and not searches and not errors:
        first = next(s["text"] for s in b["steps"] if s["kind"] == "done")
        return f"{first} ({took})" if took else first
    parts = [f"Worked through {n} step{'s' if n != 1 else ''}"]
    if searches:
        parts.append(f"{searches} web search{'es' if searches != 1 else ''}")
    if errors:
        parts.append(f"{errors} failed")
    label = ", ".join(parts)
    return f"{label} ({took})" if took else label


def current_activity(run: dict) -> str | None:
    """What the system is doing right now, for the 'thinking' indicator."""
    if run["status"] != "running":
        return None
    entries = run["ctx"].log.entries()
    phase, seen = None, set()
    for e in entries:
        m = re.match(r"preregister_gate_(\d+)$", e["action"])
        if m:
            phase, seen = int(m.group(1)), set()
        elif e["agent"] not in INTERNAL_AGENTS and (e["action"].startswith("run_") or e["action"] == "agent_error"
                                                    or e["action"].startswith("record_")):
            seen.add(e["agent"])
    if phase is None:
        return "Reading your brief"
    try:
        from phases import load_phase
        for stage in load_phase(phase).STAGES:
            for agent in stage:
                if agent not in seen:
                    return doing(agent)
    except Exception:
        pass
    return f"Checking the evidence against the Phase {phase} rules"
