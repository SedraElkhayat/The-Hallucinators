# OWNER: M1
"""Founder UI with Flask's test client. A mocked run must wait for the founder at every gate."""
import time

import pytest

import app as app_mod
from core.founder import INBOX


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(app_mod, "COMMITTED_OUT", tmp_path / "outputs")
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


def _drain(client, rid, decision="approve", timeout=20):
    """Answer every inbox item until the run ends. Returns the number of approvals given."""
    answered, end = 0, time.time() + timeout
    while time.time() < end:
        run = app_mod.RUNS[rid]
        for it in INBOX.pending():
            client.post(f"/approvals/{it['id']}", data={"decision": decision})
            answered += 1
        if run["status"] != "running":
            return answered
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_index_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Start a run" in r.data and b"MOCKED" in r.data
    h = client.get("/health").get_json()
    assert h["status"] == "ok" and "model" in h


def test_start_requires_brief(client):
    assert client.post("/start", data={}).status_code == 400


def test_mock_run_waits_for_founder_then_finishes(client):
    r = client.post("/start", data={"preset": "brief_strong.md", "mock": "on", "through": "2"})
    assert r.status_code == 302
    rid = r.headers["Location"].rsplit("/", 1)[-1]
    # answer the founder's Phase 1 questions; the run then blocks on the Gate 1 approval
    for _ in range(400):
        pending = INBOX.pending()
        if any(it["kind"] == "approval" for it in pending):
            break
        for it in pending:
            client.post(f"/approvals/{it['id']}", data={"answer": "unknown"})
        time.sleep(0.05)
    assert app_mod.RUNS[rid]["status"] == "running"
    page = client.get("/approvals")
    assert b"Approval needed" in page.data and b"Approve" in page.data
    _drain(client, rid)
    assert app_mod.RUNS[rid]["status"] == "finished"
    run_page = client.get(f"/run/{rid}")
    assert b"MOCKED run" in run_page.data and b"phase1_gate_decision" in run_page.data
    art = client.get(f"/artifact/phase1_gate_decision?run={rid}")
    assert art.status_code == 200 and b"Gate 1 decision" in art.data
    log = app_mod.RUNS[rid]["ctx"].log.entries()
    assert sum(1 for e in log if e["action"] == "approved:gate" and e["approved_by"] == "founder") == 2


def test_rejected_gate_asks_founder_and_stops(client):
    rid = client.post("/start", data={"preset": "brief_weak.md", "mock": "on", "through": "3"}) \
        .headers["Location"].rsplit("/", 1)[-1]
    end = time.time() + 20
    while app_mod.RUNS[rid]["status"] == "running" and time.time() < end:
        for it in INBOX.pending():
            value = "reject" if it["kind"] == "approval" else "stop"
            client.post(f"/approvals/{it['id']}", data={"decision": value})
        time.sleep(0.05)
    res = app_mod.RUNS[rid]["result"]
    assert res["outcome"] == "stop" and res["phase"] == 1


def test_artifact_rejects_bad_names_and_unknown_runs(client):
    assert client.get("/artifact/..%2Fsecrets").status_code in (400, 404)
    assert client.get("/artifact/phase1_step1_scope?run=nope").status_code == 404
    assert client.get("/run/nope").status_code == 404


def test_markdown_renderer_escapes_html():
    out = str(app_mod.render_md("# Title\n<script>x</script>\n- **bold** item\n```\n<b>code</b>\n```"))
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<h2>Title</h2>" in out and "<b>bold</b>" in out and "&lt;b&gt;code" in out
