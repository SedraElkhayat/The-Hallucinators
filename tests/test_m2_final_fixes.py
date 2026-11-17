"""Final-night fixes: founder sets the price when no source states one; critics stop over-flagging (no gate change)."""
from types import SimpleNamespace

from agents.critic_phase1 import quotes_absence_or_interview
from agents.critic_phase2 import CriticPhase2
from agents.pricing_analyst import PricingAnalyst


class _Log:
    def __init__(self):
        self.entries = []

    def action(self, agent, action, **kw):
        self.entries.append((action, kw))


def _pricing_ctx(answer):
    log = _Log()

    def provide(key, prompt):
        assert key == "founder_price"
        if isinstance(answer, Exception):
            raise answer
        return answer
    store = SimpleNamespace(has=lambda s: False, get=lambda s: {})
    return SimpleNamespace(brief="**Budget:** USD 100 total.", log=log, store=store,
                           founder=SimpleNamespace(provide=provide), mock=True), log


def _run_pricing(answer):
    ctx, log = _pricing_ctx(answer)
    agent = PricingAnalyst()
    agent.keep_verified_comparables = lambda c, claims: []
    data = agent.post_process(ctx, {"price_usd": None, "range": None, "comparable_claims": [], "is_assumption": True})
    return data, log


def test_founder_sets_the_price_when_no_source_states_one():
    data, log = _run_pricing("9")
    assert data["price_usd"] == 9 and data["price_source"] == "founder" and data["is_assumption"] is True
    assert data["price_label"].startswith("Set by the founder") and "ASSUMPTION" in data["price_label"]
    assert "note" not in data
    assert any(a == "founder_set_price" and kw.get("approved_by") == "founder" for a, kw in log.entries)


def test_no_usable_founder_price_stays_stubbed():
    for answer in ("I don't know", "100", RuntimeError("no scripted answer")):
        data, _ = _run_pricing(answer)
        assert data["price_usd"] is None and data["note"].startswith("STUBBED")


def test_phase1_critic_issue_about_missing_evidence_or_interviews_is_not_must_fix():
    absence = ("The report states 'there is insufficient evidence to confirm a demand for a bilingual template pack.' "
               "but does not cite any verified claims. This is a factual statement that lacks a verified source.")
    interview = ("The report mentions 'interviewees showed no commitment signals for paying for a template.' "
                 "but does not cite any verified claims.")
    market = ("The report mentions 'Competitors like Notion Freelance Templates offer free alternatives.' "
              "but does not cite any verified claims.")
    assert quotes_absence_or_interview(absence, has_interviews=False)
    assert quotes_absence_or_interview(interview, has_interviews=True)
    assert not quotes_absence_or_interview(interview, has_interviews=False)
    assert not quotes_absence_or_interview(market, has_interviews=True)  # a market claim still needs a source


def test_phase2_critic_risk_without_evidence_is_not_must_fix():
    store = SimpleNamespace(has=lambda s: False, get=lambda s: {})
    ctx = SimpleNamespace(store=store, extra={}, mock=False, brief="")
    data = {"verdict": "revise", "issues": [
        {"severity": "must_fix", "text": "The report includes a high-severity risk about unknown demand, but the "
                                         "claim is not supported by real evidence."},
        {"severity": "must_fix", "text": "The report says 45% of competitors charge USD 20 without a source."}]}
    out = CriticPhase2().post_process(ctx, data)
    risk, number = out["issues"]
    assert risk["severity"] == "should_fix" and "uncertainty" in risk["downgraded_by_code"]
    assert number["severity"] == "must_fix" and out["verdict"] == "revise"
