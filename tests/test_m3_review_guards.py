"""Reviewer guards (M1's targeted qwen3:8b check, Tuesday 14:54).

The two inputs in tests/fixtures/m3_real/ are the critic and content-review answers that qwen3:8b gave in that run.
- critic_phase2 raised must_fix issues disputing two rules that code enforces by design.
- content_reviewer asked six times for the "SIMULATED, not real users" label on MOCKED claims.
Code downgrades exactly those disputes to should_fix, records why, and keeps every real must_fix.
"""
import json

import pytest

from tests.test_m3_helpers import ROOT, ScriptedLLM, fixture, get_agent, make_ctx, put

REAL = ROOT / "tests" / "fixtures" / "m3_real"


def _real(name):
    data = json.loads((REAL / name).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def _critic(tmp_path, resp, provenance="MOCKED", demand_rating="adequate"):
    agent = get_agent("critic_phase2")
    ctx = make_ctx(tmp_path, llm=ScriptedLLM({"critic_phase2": resp}),
                   seed=agent.inputs + ["phase2_step7_risks", "phase2_step8_scorecard"])
    put(ctx, "phase2_step5_demand_results", {"signups": 140, "days": 14, "provenance": provenance, "ratio": 1.4,
                                             "target": 100, "window_days": 14})
    card = fixture("scorecard_builder")
    card["dimensions"]["demand_evidence"]["rating"] = demand_rating
    put(ctx, "phase2_step8_scorecard", card)
    return agent.run(ctx).data


def test_TC_M3_review_critic_disputes_of_code_rules_are_downgraded(tmp_path):
    data = _critic(tmp_path, _real("qwen3_critique.json"))
    must = [i for i in data["issues"] if i["severity"] == "must_fix"]
    assert must == [] and data["verdict"] == "ok"
    downgraded = [i for i in data["issues"] if i.get("downgraded_by_code")]
    assert len(downgraded) == 2
    assert any("caps demand_evidence at adequate" in i["downgraded_by_code"] for i in downgraded)
    assert any("named evidence" in i["downgraded_by_code"] for i in downgraded)
    assert len(data["issues"]) == len(_real("qwen3_critique.json")["issues"])  # nothing is deleted


def test_TC_M3_review_critic_keeps_real_must_fix(tmp_path):
    resp = {"issues": [{"severity": "must_fix", "text": "The summary calls demand proven although it is MOCKED"},
                       {"severity": "must_fix", "text": "Flattery: the report calls the idea brilliant"},
                       {"severity": "must_fix", "text": "Demand evidence rated strong on MOCKED results"},
                       {"severity": "must_fix", "text": "A triggered kill criterion is missing from the findings"}],
            "verdict": "revise"}
    data = _critic(tmp_path, resp)
    assert [i["severity"] for i in data["issues"]] == ["must_fix"] * 4 and data["verdict"] == "revise"


def test_TC_M3_review_critic_guard_needs_the_rule_to_have_applied(tmp_path):
    # With a REAL demand result the cap and the MOCKED kill point do not apply: the must_fix issues stay.
    data = _critic(tmp_path, _real("qwen3_critique.json"), provenance="REAL", demand_rating="strong")
    assert sum(i["severity"] == "must_fix" for i in data["issues"]) == 2 and data["verdict"] == "revise"
    # A MOCKED result but a scorecard that says strong (the cap did not apply): the adequate dispute is not downgraded.
    data = _critic(tmp_path / "b", {"issues": [{"severity": "must_fix",
                                                "text": "Demand evidence rated 'adequate' based on MOCKED results"}],
                                    "verdict": "revise"}, demand_rating="strong")
    assert data["issues"][0]["severity"] == "must_fix"


def _reviewer(tmp_path, resp, site_extra=None):
    builder = get_agent("builder")
    ctx = make_ctx(tmp_path, seed=builder.inputs)
    builder.run(ctx)
    if site_extra:
        page = ctx.out_dir / "phase3_step3_site" / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace("</main>", site_extra + "</main>"), encoding="utf-8")
    agent = get_agent("content_reviewer")
    for step in agent.inputs:
        if not ctx.store.has(step):
            from tests.test_m3_helpers import seed_data
            put(ctx, step, seed_data(step))
    ctx.llm = ScriptedLLM({"content_reviewer": resp})
    return agent.run(ctx).data


def test_TC_M3_review_simulated_label_on_mocked_claims_is_not_a_must_fix(tmp_path):
    data = _reviewer(tmp_path, _real("qwen3_content_review.json"))
    assert data["verdict"] == "ok"
    assert len(data["issues"]) == 1  # six identical issues count once
    assert data["issues"][0]["severity"] == "should_fix" and "only for simulated people" in data["issues"][0]["downgraded_by_code"]


def test_TC_M3_review_simulated_request_stays_must_fix_when_the_site_shows_counts(tmp_path):
    data = _reviewer(tmp_path, _real("qwen3_content_review.json"), site_extra="<p>Join 40 designers</p>")
    assert data["issues"][0]["severity"] == "must_fix" and data["verdict"] == "revise"


def test_TC_M3_review_reviewer_keeps_other_must_fix(tmp_path):
    resp = {"issues": [{"severity": "must_fix", "text": "The FAQ promises 5 hours saved a week", "file": "faq"},
                       {"severity": "must_fix", "text": "Fake testimonial in features", "file": "index.html"}],
            "verdict": "ok"}
    data = _reviewer(tmp_path, resp)
    assert [i["severity"] for i in data["issues"]] == ["must_fix", "must_fix"] and data["verdict"] == "revise"


def test_TC_M3_review_prompts_state_the_code_rules_and_labels():
    read = lambda n: (ROOT / "prompts" / f"{n}.md").read_text(encoding="utf-8")
    critic = read("critic_phase2")
    assert "caps `demand_evidence` at `adequate`" in critic and "a MOCKED result alone triggers none" in critic
    reviewer = read("content_reviewer")
    assert "Never ask for the SIMULATED label on a claim or on MOCKED text" in reviewer
    assert "Any sign-up, waitlist or user number on the page is `must_fix`" in reviewer
    for name in ("builder", "copywriter", "landing_page_builder", "spec_writer"):
        assert "No sign-up, waitlist or user numbers anywhere" in read(name), name


# ---------------------------------------------------------------- the SIMULATED downgrade is narrow (15:13 review)

def test_TC_M3_review_fake_testimonial_issue_mentioning_simulated_stays_must_fix(tmp_path):
    resp = {"issues": [{"severity": "must_fix", "file": "index.html",
                        "text": "The page shows simulated testimonials from fake customers as real praise"}],
            "verdict": "revise"}
    data = _reviewer(tmp_path, resp)
    assert data["issues"][0]["severity"] == "must_fix" and "downgraded_by_code" not in data["issues"][0]
    assert data["verdict"] == "revise" and "verdict_changed_by_code" not in data


def test_TC_M3_review_label_request_is_still_downgraded_next_to_a_real_must_fix(tmp_path):
    resp = {"issues": [{"severity": "must_fix", "text": "Claim labeled MOCKED but not labeled SIMULATED, not real users"},
                       {"severity": "must_fix", "text": "Simulated ratings are shown as real reviews"}],
            "verdict": "revise"}
    data = _reviewer(tmp_path, resp)
    assert [i["severity"] for i in data["issues"]] == ["should_fix", "must_fix"]
    assert data["verdict"] == "revise"  # a real must_fix remains, so the verdict is not changed


@pytest.mark.parametrize("text,downgraded", [
    ("Claim labeled MOCKED but not labeled SIMULATED, not real users", True),
    ("Add the SIMULATED label to the example numbers", True),
    ("Example timeline needs the simulated label", True),
    ("The page shows simulated testimonials from fake customers as real praise", False),
    ("Simulated reviews shown as real; add a label", False),
    ("Add SIMULATED label: invented customer quote", False),
    ("Fabricated numbers, add simulated label", False),
    ("Simulated rating needs a label", False),
    ("Customer says the kit is great; add simulated label", False),
    ("Mentions simulated data", False),  # does not ask for the label
])
def test_TC_M3_review_downgrade_rule_boundaries(text, downgraded):
    from agents.content_reviewer import asks_for_simulated_label
    assert asks_for_simulated_label(text) is downgraded
