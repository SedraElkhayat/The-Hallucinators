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


# ---------------------------------------------------------------- founder website preview / download
import io
import zipfile


def _fake_run_with_site(tmp_path, rid="20260101T000000_site01", phase5=False):
    out = tmp_path / "runs" / rid / "outputs"
    site = out / "phase3_step3_site"
    (site / "policies").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>Build version</title><a href='policies/terms.html'>Terms</a>")
    (site / "policies" / "terms.html").write_text("<p>Draft terms, needs legal review</p>")
    (out / "secret_note.md").write_text("not part of the site")
    if phase5:
        (out / "phase5_step2_store_site").mkdir()
        (out / "phase5_step2_store_site" / "index.html").write_text("<!doctype html><title>Store version</title>")
    return rid


def test_preview_serves_site_with_inert_csp(client, tmp_path):
    rid = _fake_run_with_site(tmp_path)
    r = client.get(f"/site/{rid}/")
    assert r.status_code == 200 and b"Build version" in r.data
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "form-action 'none'" in csp
    assert client.get(f"/site/{rid}/policies/terms.html").status_code == 200


def test_preview_prefers_phase5_store_version(client, tmp_path):
    rid = _fake_run_with_site(tmp_path, phase5=True)
    assert b"Store version" in client.get(f"/site/{rid}/").data


def test_preview_cannot_leave_the_site_folder(client, tmp_path):
    rid = _fake_run_with_site(tmp_path)
    for bad in ["../secret_note.md", "..%2Fsecret_note.md", "policies/../../secret_note.md", "/etc/passwd"]:
        assert client.get(f"/site/{rid}/{bad}", follow_redirects=True).status_code in (400, 404), bad
    assert client.get("/site/nope/").status_code == 404
    assert client.get("/site/..%2F..%2F/").status_code == 404


def test_download_zips_only_the_site_folder(client, tmp_path):
    rid = _fake_run_with_site(tmp_path)
    r = client.get(f"/download/site/{rid}")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert sorted(names) == ["phase3_step3_site/index.html", "phase3_step3_site/policies/terms.html"]
    assert not (tmp_path / "runs" / rid / "outputs" / "phase3_step3_site.zip").exists()


def test_no_site_means_404_and_committed_outputs_preview(client, tmp_path):
    out = tmp_path / "runs" / "20260101T000000_nosite" / "outputs"
    out.mkdir(parents=True)
    assert client.get("/site/20260101T000000_nosite/").status_code == 404
    assert client.get("/download/site/outputs").status_code == 404
    (tmp_path / "outputs" / "phase3_step3_site").mkdir(parents=True)
    (tmp_path / "outputs" / "phase3_step3_site" / "index.html").write_text("<title>Demo run site</title>")
    assert b"Demo run site" in client.get("/site/outputs/").data
    assert b"Preview website" in client.get("/").data
