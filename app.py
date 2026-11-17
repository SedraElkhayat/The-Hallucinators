# OWNER: M1
"""Founder UI (Flask, server-rendered, no JavaScript).

Pages: /  (brief form, runs)   /run/<id>  (live progress)   /approvals  (founder inbox)
       /artifact/<step>?run=<id>  (rendered artifact)   /health
       /site/<id>/  (local preview of the founder's website)   /download/site/<id>  (zip of its folder)
       <id> "outputs" means the committed demo run in outputs/.
The pipeline runs in a background thread with founder mode "web": every question and approval waits
in the inbox until the founder answers. Nothing is published, sent, spent or signed by the system.
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_file, send_from_directory, url_for
from markupsafe import Markup

import orchestrator
from core.founder import INBOX

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
COMMITTED_OUT = ROOT / "outputs"
STEP_RX = re.compile(r"^[A-Za-z0-9_\-]+$")
app = Flask(__name__, template_folder=str(ROOT / "templates"))
RUNS: dict[str, dict] = {}
_lock = threading.Lock()

# The founder's website: built in Phase 3, re-filled with price and policies in Phase 5 (newest first).
SITE_DIRS = (("phase5_step2_store_site", "Phase 5 store version"), ("phase3_step3_site", "Phase 3 build version"))
# Preview is local only and inert: no scripts, no network, and forms cannot submit anywhere.
SITE_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'self'")


# ---------------------------------------------------------------- runs
def start_run(brief: str, mock: bool, through: int = 6) -> str:
    rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    out_dir = RUNS_DIR / rid / "outputs"
    ctx = orchestrator.build_context(brief, out_dir, out_dir.parent / "decision_log.json", mock=mock,
                                     founder_mode="web", founder_inputs=None)
    run = {"id": rid, "status": "running", "mock": mock, "result": None, "ctx": ctx, "through": through,
           "brief": brief.strip().splitlines()[0][:120] if brief.strip() else "", "error": None}
    with _lock:
        RUNS[rid] = run

    def work():
        try:
            run["result"] = orchestrator.run(ctx, through=through)
            run["status"] = "finished"
        except Exception as e:  # shown on the run page; the decision log keeps the trail
            run["status"], run["error"] = "error", f"{type(e).__name__}: {e}"

    threading.Thread(target=work, daemon=True, name=f"run-{rid}").start()
    return rid


def progress(run: dict) -> dict:
    """Current phase and agent, derived from the run's decision log (the event stream)."""
    entries = run["ctx"].log.entries()
    phase, agent = None, None
    for e in entries:
        m = re.match(r"preregister_gate_(\d+)", e["action"])
        if m:
            phase = int(m.group(1))
        if e["agent"] not in ("gate", "orchestrator", "approval", "founder"):
            agent = e["agent"]
    return {"phase": phase, "agent": agent, "events": entries[-40:][::-1], "count": len(entries)}


def artifact_dir(rid: str | None) -> Path:
    if not rid:
        return COMMITTED_OUT
    run = RUNS.get(rid)
    if run:
        return run["ctx"].out_dir
    d = RUNS_DIR / rid / "outputs"
    if STEP_RX.match(rid) and d.is_dir():
        return d
    abort(404)


def site_dir(rid: str) -> tuple[Path, str] | None:
    """The newest website folder of a run (or of the committed outputs/ when rid == "outputs")."""
    base = COMMITTED_OUT if rid == "outputs" else artifact_dir(rid)
    for name, label in SITE_DIRS:
        if (base / name / "index.html").is_file():
            return base / name, label
    return None


# ---------------------------------------------------------------- tiny markdown renderer
def render_md(text: str) -> Markup:
    out, in_code, in_list = [], False, False
    for line in text.splitlines():
        if line.startswith("```"):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        s = html.escape(line)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        m = re.match(r"^(#{1,4}) (.*)$", s)
        if re.match(r"^\s*[-*] ", s):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*[-*] ", "", s)
            out.append(f"<li>{item}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m:
            n = len(m.group(1)) + 1
            out.append(f"<h{n}>{m.group(2)}</h{n}>")
        elif s.startswith("&gt; "):
            out.append(f"<blockquote>{s[5:]}</blockquote>")
        elif s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            out.append("<div class='row'>" + "".join(f"<span>{c}</span>" for c in cells) + "</div>")
        elif s.strip():
            out.append(f"<p>{s}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return Markup("\n".join(out))


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    briefs = {p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "demo").glob("brief_*.md"))}
    with _lock:
        runs = sorted(RUNS.values(), key=lambda r: r["id"], reverse=True)
    return render_template("index.html", briefs=briefs, runs=runs, pending=len(INBOX.pending()),
                           model=os.getenv("LLM_MODEL", "qwen3:8b"), demo_site=site_dir("outputs"))


@app.post("/start")
def start():
    brief = request.form.get("brief", "").strip()
    preset = request.form.get("preset", "")
    if not brief and preset:
        p = ROOT / "demo" / preset
        if p.parent == ROOT / "demo" and p.is_file():
            brief = p.read_text(encoding="utf-8")
    if not brief:
        abort(400, "A brief is required.")
    through = max(1, min(6, int(request.form.get("through", 6) or 6)))
    rid = start_run(brief, mock=request.form.get("mock") == "on", through=through)
    return redirect(url_for("run_page", rid=rid))


@app.get("/run/<rid>")
def run_page(rid):
    run = RUNS.get(rid)
    if not run:
        abort(404)
    out = run["ctx"].out_dir
    files = sorted(p.name for p in out.glob("*") if p.is_file()) if out.is_dir() else []
    steps = sorted({Path(f).stem for f in files if f.endswith((".md", ".json", ".html"))})
    return render_template("run.html", run=run, prog=progress(run), steps=steps, site=site_dir(rid),
                           pending=len(INBOX.pending()))


@app.get("/approvals")
def approvals():
    return render_template("approvals.html", items=INBOX.pending(), pending=len(INBOX.pending()))


@app.post("/approvals/<int:item_id>")
def answer(item_id):
    if item_id not in INBOX.items:
        abort(404)
    value = request.form.get("decision") or request.form.get("answer", "")
    INBOX.answer(item_id, value.strip())
    return redirect(url_for("approvals"))


@app.get("/artifact/<step>")
def artifact(step):
    if not STEP_RX.match(step):
        abort(400)
    rid = request.args.get("run")
    d = artifact_dir(rid)
    md, js, ht = d / f"{step}.md", d / f"{step}.json", d / f"{step}.html"
    if not (md.exists() or js.exists() or ht.exists()):
        abort(404)
    data = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {}
    mocked = bool(data.get("mocked")) or (RUNS.get(rid, {}).get("mock", False))
    return render_template("artifact.html", step=step, rid=rid, mocked=mocked,
                           body=render_md(md.read_text(encoding="utf-8")) if md.exists() else None,
                           html_src=ht.read_text(encoding="utf-8") if ht.exists() else None,
                           raw=json.dumps(data, indent=2, ensure_ascii=False) if data else None,
                           pending=len(INBOX.pending()))


@app.get("/site/<rid>/")
@app.get("/site/<rid>/<path:name>")
def site_preview(rid, name="index.html"):
    """Serve the founder's website locally for preview. The system never publishes or deploys it."""
    found = site_dir(rid)
    if not found:
        abort(404)
    resp = send_from_directory(found[0], name)  # rejects paths outside the folder
    resp.headers["Content-Security-Policy"] = SITE_CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Robots-Tag"] = "noindex"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/download/site/<rid>")
def site_download(rid):
    """Zip the website folder in memory so the founder can publish it themselves. Nothing is written to outputs/."""
    found = site_dir(rid)
    if not found:
        abort(404)
    folder = found[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f"{folder.name}/{f.relative_to(folder).as_posix()}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{folder.name}.zip")


@app.get("/health")
def health():
    return {"status": "ok", "model": os.getenv("LLM_MODEL", "qwen3:8b"),
            "llm_base_url": os.getenv("LLM_BASE_URL", "http://ollama:11434/v1"),
            "runs": len(RUNS), "pending_founder_items": len(INBOX.pending())}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("APP_PORT", "8000")), threaded=True)
