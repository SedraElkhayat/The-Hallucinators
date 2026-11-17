# OWNER: M1
"""Founder UI: start a run, answer questions, approve or reject every gated item. Nothing goes out without it."""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

import orchestrator
from core.founder import INBOX

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
app = Flask(__name__, template_folder=str(ROOT / "templates"))
STATE: dict[str, dict] = {}


def _start(brief: str, mock: bool, through: int) -> str:
    rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    out_dir, log_path = RUNS / rid / "outputs", RUNS / rid / "decision_log.json"
    ctx = orchestrator.build_context(brief, out_dir, log_path, mock=mock, founder_mode="web", founder_inputs=None)
    STATE[rid] = {"status": "running", "mock": mock, "result": None, "out_dir": out_dir}

    def work():
        try:
            STATE[rid]["result"] = orchestrator.run(ctx, through=through)
            STATE[rid]["status"] = "finished"
        except Exception as e:
            STATE[rid]["status"] = f"error: {type(e).__name__}: {e}"

    threading.Thread(target=work, daemon=True).start()
    return rid


@app.get("/")
def index():
    briefs = {p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "demo").glob("brief_*.md"))}
    return render_template("index.html", briefs=briefs, model=os.getenv("LLM_MODEL", "qwen3:8b"))


@app.post("/api/runs")
def start_run():
    body = request.get_json(force=True)
    brief = (body.get("brief") or "").strip()
    if not brief:
        abort(400, "brief is required")
    rid = _start(brief, bool(body.get("mock")), int(body.get("through", 6)))
    return jsonify({"run_id": rid})


@app.get("/api/runs/<rid>")
def run_status(rid):
    st = STATE.get(rid)
    if not st:
        abort(404)
    files = sorted(p.name for p in st["out_dir"].glob("*") if p.is_file())
    return jsonify({"status": st["status"], "mock": st["mock"], "result": st["result"], "files": files})


@app.get("/runs/<rid>/<path:name>")
def run_file(rid, name):
    st = STATE.get(rid)
    if not st:
        abort(404)
    return send_from_directory(st["out_dir"], name)


@app.get("/api/inbox")
def inbox():
    return jsonify(INBOX.pending())


@app.post("/api/inbox/<int:item_id>")
def answer(item_id):
    body = request.get_json(force=True)
    INBOX.answer(item_id, str(body.get("answer", "")))
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("APP_PORT", "8000")), threaded=True)
