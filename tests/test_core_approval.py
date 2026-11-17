# OWNER: M1
import pytest

from approval import NotApproved
from tests.helpers import make_ctx


def _ctx(tmp_path, approvals):
    return make_ctx(tmp_path, founder_inputs={"idea_choice": "A", "prefix_defaults": {"clarify_": "unknown"},
                                              "approvals": approvals})


def test_approve_logs_founder(tmp_path):
    ctx = _ctx(tmp_path, {"default": "approve"})
    assert ctx.approvals.request("page", "Landing page", "<html>", 2) is True
    e = [e for e in ctx.log.entries() if e["action"] == "approved:page"][0]
    assert e["approved_by"] == "founder" and e["provenance"] == "SCRIPTED"


def test_reject_never_logs_founder_approval(tmp_path):
    ctx = _ctx(tmp_path, {"default": "reject"})
    assert ctx.approvals.request("post", "Launch post", "text", 5) is False
    assert all(e["approved_by"] is None for e in ctx.log.entries())


def test_release_requires_approval(tmp_path):
    ctx = _ctx(tmp_path, {"default": "approve", "post": "reject"})
    assert ctx.approvals.release("page", "Store page", "<html>", 5) is True
    with pytest.raises(NotApproved):
        ctx.approvals.release("post", "Launch post", "text", 5)
    released = [e for e in ctx.log.entries() if e["action"].startswith("released:")]
    assert [e["action"] for e in released] == ["released:page"]
    assert all(e["approved_by"] == "founder" for e in released)


def test_scripted_founder_keys_and_prefix_defaults(tmp_path):
    ctx = make_ctx(tmp_path, founder_inputs={"idea_choice": "A",
                                             "prefix_defaults": {"clarify_": "unknown", "clarify_budget": "100"}})
    assert ctx.founder.ask("idea_choice", "?") == "A"
    assert ctx.founder.provide("clarify_budget", "?") == "100"
    assert ctx.founder.provide("clarify_problem", "?") == "unknown"
    with pytest.raises(KeyError, match="interview_notes"):
        ctx.founder.ask("interview_notes", "?")
    assert all(e["provenance"] == "SCRIPTED" for e in ctx.log.entries() if e["agent"] == "founder")


def test_demo_inputs_cover_fixed_keys(tmp_path):
    ctx = make_ctx(tmp_path)  # demo/founder_inputs.json
    for key in ["clarify_problem", "option_budget", "idea_choice", "interview_notes", "demand_results",
                "support_questions", "phase6_results"]:
        assert ctx.founder.provide(key, "?")
