# OWNER: M2
"""scripts/audit_outputs.py: passes a clean folder, fails each kind of violation."""
import json

from scripts import audit_outputs as audit
from tests.test_m2_helpers import ctx_for
import orchestrator


def write(d, name, text):
    (d / name).write_text(text, encoding="utf-8")


def good(d):
    write(d, "phase1_step5_market.json", json.dumps({"claims": [
        {"claim": "a", "source_url": "https://a.org", "quote": "q" * 25, "verified": True, "assumption": False},
        {"claim": "b", "source_url": "", "quote": "", "verified": False, "assumption": True}]}))
    write(d, "phase1_step5_market.md", "# Market\n\nWe cannot guarantee results. No countdown timers.\n")


def test_clean_folder_passes(tmp_path, capsys):
    good(tmp_path)
    assert audit.main([str(tmp_path)]) == 0
    assert "AUDIT PASS" in capsys.readouterr().out


def test_unsourced_claim_fails(tmp_path):
    good(tmp_path)
    write(tmp_path, "phase1_step5_demand_signals.json", json.dumps({"claims": [
        {"claim": "people pay", "source_url": "", "quote": "", "verified": None, "assumption": False}]}))
    write(tmp_path, "phase1_step5_demand_signals.md", "# d\n")
    probs = audit.audit(tmp_path)
    assert any("without a source URL" in m for m in probs["phase1_step5_demand_signals.json"])
    assert audit.main([str(tmp_path)]) == 1


def test_unverified_claim_not_labeled_fails():
    probs = audit.claim_problems({"claims": [{"claim": "x", "source_url": "https://a.org", "quote": "q",
                                              "verified": False, "assumption": False}]})
    assert probs and "unverified" in probs[0]


def test_finding_without_claim_fails():
    probs = audit.claim_problems({"findings": [{"text": "big market"}, {"text": "ok", "claim_ids": ["C1"]},
                                               {"text": "ASSUMPTION: maybe"}]})
    assert len(probs) == 1 and "findings[0]" in probs[0]


def test_banned_phrases_and_negation():
    assert audit.banned_hits("This is a great idea!")
    assert audit.banned_hits("Results are guaranteed.")
    assert audit.banned_hits("Rated 5-star by buyers")
    assert audit.banned_hits("Offer countdown: 2 hours")
    assert not audit.banned_hits("We cannot guarantee any income.")
    assert not audit.banned_hits("The page has no countdown and never says risk-free.")


def test_empty_file_and_mock_label(tmp_path):
    write(tmp_path, "phase1_step1_scope.json", json.dumps({"is_digital": True, "mocked": True}))
    write(tmp_path, "phase1_step1_scope.md", "# Scope\n")
    write(tmp_path, "phase1_step2_x.md", "")
    probs = audit.audit(tmp_path)
    assert any("MOCKED" in m for m in probs["phase1_step1_scope.json"])
    assert probs["phase1_step2_x.md"] == ["empty file"]


def test_sample_provenance_must_be_shown(tmp_path):
    write(tmp_path, "phase1_step6_interview_findings.json", json.dumps({"provenance": "SAMPLE", "findings": "f"}))
    write(tmp_path, "phase1_step6_interview_findings.md", "# Findings\n")
    assert any("SAMPLE" in m for m in audit.audit(tmp_path)["phase1_step6_interview_findings.json"])


def test_mock_phase1_run_passes_audit(tmp_path):
    ctx = ctx_for(tmp_path)
    orchestrator.run(ctx, through=1)
    problems = audit.audit(ctx.out_dir)
    assert not problems, problems
