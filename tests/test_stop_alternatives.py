"""After a STOP the founder gets other directions, not a dead end (demo feedback). Offline, no network."""
from core import alternatives
from tests.helpers import make_ctx

SCORES = {"chosen": "Idea A", "top_scored": "Idea A", "switch_suggested": False, "ranked": [
    {"name": "Idea A", "score": 7.0, "reasons": ["need: x"], "is_founder_idea": True},
    {"name": "Idea B", "score": 6.0, "reasons": ["need: y", "fit: z"]},
    {"name": "Idea C", "score": 5.0, "reasons": ["need: w"]}]}


class _Founder:
    mode = "web"

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask(self, key, prompt, options=None):
        self.asked.append((key, prompt, options))
        return self.answer


def _ctx(tmp_path, answer):
    ctx = make_ctx(tmp_path)
    ctx.store.put("phase1_step7_opportunity_scores", SCORES, "# scores", agent="test")
    ctx.founder = _Founder(answer)
    return ctx


def test_TC_UX_stop_shows_the_other_ranked_ideas_and_what_would_change_the_verdict(tmp_path):
    ctx = _ctx(tmp_path, alternatives.STOP_HERE)
    assert alternatives.offer(ctx, 1, ["0 verified claims"]) is None
    d = ctx.store.get("phase1_gate_alternatives")
    assert [a["name"] for a in d["alternatives"]] == ["Idea B", "Idea C"]      # never the idea that just stopped
    assert d["what_would_change_the_verdict"] == ["0 verified claims"] and d["founder_choice"] == "stop here"
    key, prompt, options = ctx.founder.asked[0]
    assert key == "stop_alternative_1" and options == ["Idea B", "Idea C", "stop here"] and "Idea B" in prompt


def test_TC_UX_founder_can_pick_by_name_or_number_and_the_choice_is_logged(tmp_path):
    for answer in ("Idea C", "2"):
        ctx = _ctx(tmp_path / answer, answer)
        assert alternatives.offer(ctx, 2, [])["name"] == "Idea C"
        assert any(e["action"] == "stop_alternative_2" and e["approved_by"] == "founder" for e in ctx.log.entries())


def test_TC_UX_without_ranked_alternatives_nobody_is_asked_and_the_file_says_so(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.founder = _Founder("1")
    assert alternatives.offer(ctx, 1, ["why"]) is None and ctx.founder.asked == []
    assert "No other idea was ranked" in (ctx.out_dir / "phase1_gate_alternatives.md").read_text(encoding="utf-8")


def test_TC_UX_scripted_runs_without_the_key_keep_stopping(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.store.put("phase1_step7_opportunity_scores", SCORES, "# scores", agent="test")
    assert alternatives.offer(ctx, 1, []) is None           # demo inputs have no stop_alternative_1 key


def test_TC_UX_an_unknown_answer_is_treated_as_stop(tmp_path):
    assert alternatives.offer(_ctx(tmp_path, "something else"), 1, []) is None


def test_TC_UX_picking_an_alternative_restarts_from_phase_1_once_with_the_direction_in_the_brief(tmp_path):
    import json
    import pathlib
    import orchestrator
    root = pathlib.Path(__file__).resolve().parent.parent / "demo"
    inputs = json.loads((root / "founder_inputs_weak.json").read_text(encoding="utf-8"))
    inputs["approvals"] = {"default": "approve"}
    inputs["stop_alternative_2"] = "1"
    inputs["stop_alternative_1"] = "1"
    brief = (root / "brief_weak.md").read_text(encoding="utf-8")
    ctx = make_ctx(tmp_path, brief=brief, founder_inputs=inputs)
    res = orchestrator.run(ctx, through=2)
    restarts = [e for e in ctx.log.entries() if e["action"] == "restart_with_alternative"]
    assert len(restarts) == 1                                   # one restart at most
    assert "Direction chosen by the founder" in ctx.brief
    assert [p for p, _, _ in res["history"]].count(1) >= 2       # Phase 1 ran again
    assert res["outcome"] == "stop"                              # and a second STOP ends the run
