"""Bugs found while testing the web app and the stop flow by hand, one test per bug. Offline, no network.

1 skip ends the questions; 2 a bad "through" value is a 400; 3 each run has its own questions; 4 the gate override
understands what the founder types; 5 the "I don't know" hint only where it works; 6 no question that cannot be
honored; 7 "different options" never moves on silently; 8 typed directions are understood; 9 one word for the
checkpoint; 10 friendly choice buttons; 11 the alternatives file is honest about thin evidence and who chose.
"""
import json
import pathlib
import threading
import time

import pytest
from jinja2 import Environment, FileSystemLoader

import orchestrator
from core import alternatives
from tests.helpers import DEMO_INPUTS, make_ctx

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = Environment(loader=FileSystemLoader(str(ROOT / "templates")))


class SeqFounder:
    """A founder that answers from a list and remembers every prompt (web mode: answers are not scripted)."""
    mode = "web"

    def __init__(self, answers):
        self.answers, self.prompts, self.options = list(answers), [], []

    def ask(self, key, prompt, options=None):
        self.prompts.append(prompt)
        self.options.append(options)
        return self.answers.pop(0) if self.answers else "stop"


# ------------------------------------------------------------------ 1. skip ends the questions (M2)
def test_TC_BUG1_after_skip_the_option_suggester_asks_nothing(tmp_path):
    from agents import get_agent
    from tests.test_m2_agents import inputs, only
    from tests.test_m2_helpers import TransformLLM, ctx_for, run_until
    ctx = ctx_for(tmp_path, brief="Something.", founder_inputs=inputs(clarify_product_type="skip"))
    run_until(ctx, "clarifier")
    ctx.llm = TransformLLM(only("clarifier", {"stated": {}, "idea": None, "questions": []}))
    get_agent("clarifier").run(ctx)
    assert ctx.store.get("phase1_step2_clarification")["stopped_by_founder"] is True
    asked = []
    orig = ctx.founder.ask
    ctx.founder.ask = lambda k, p, options=None: (asked.append(k) or orig(k, p, options))
    get_agent("option_suggester").run(ctx)
    assert asked == []
    fields = ctx.store.get("phase1_step2_options")["fields"]
    assert all(v["status"] in ("answered", "unknown_confirmed") for v in fields.values())
    assert any(v["status"] == "unknown_confirmed" for v in fields.values())


# ------------------------------------------------------------------ 2 and 3. the web app (M1)
def test_TC_BUG2_a_non_numeric_phase_limit_is_a_400_not_a_crash():
    import app as appmod
    c = appmod.app.test_client()
    n = len(appmod.RUNS)
    assert c.post("/start", data={"brief": "SAMPLE brief", "through": "abc", "mock": "on"}).status_code == 400
    assert len(appmod.RUNS) == n                                  # and no run was started


def test_TC_BUG3_the_inbox_filters_by_run_and_nothing_else_changes():
    from core.founder import Inbox
    inbox = Inbox()
    a, b = inbox.open("input", "clarify_budget", "A?", run="run-a"), inbox.open("input", "clarify_budget", "B?", run="run-b")
    legacy = inbox.open("input", "x", "no run")
    assert [i["id"] for i in inbox.pending("run-a")] == [a["id"]]
    assert [i["id"] for i in inbox.pending("run-b")] == [b["id"]]
    assert len(inbox.pending()) == 3 and {i["id"] for i in inbox.all()} == {a["id"], b["id"], legacy["id"]}
    inbox.answer(a["id"], "100")
    assert inbox.pending("run-a") == [] and [i["answer"] for i in inbox.all("run-a")] == ["100"]


def test_TC_BUG3_a_founder_and_an_approval_tag_their_questions_with_the_run():
    from approval import Approvals
    from core.founder import FounderInput, Inbox
    inbox = Inbox()
    log = make_ctx(pathlib.Path(__import__("tempfile").mkdtemp())).log
    founder, approvals = FounderInput("web", log, inbox=inbox), Approvals("web", log, inbox=inbox)
    founder.run_id = approvals.run_id = "run-x"
    threads = [threading.Thread(target=founder.ask, args=("clarify_budget", "How much?"), daemon=True),
               threading.Thread(target=approvals.request, args=("gate", "Gate 1: go", "details", 1), daemon=True)]
    for t in threads:
        t.start()
    for _ in range(100):
        if len(inbox.pending("run-x")) == 2:
            break
        time.sleep(0.05)
    assert {i["kind"] for i in inbox.pending("run-x")} == {"input", "approval"}
    assert inbox.pending("another-run") == []
    for i in inbox.pending():
        inbox.answer(i["id"], "approve")
    for t in threads:
        t.join(timeout=5)


def test_TC_BUG3_a_run_page_lists_only_its_own_questions_and_the_inbox_page_names_the_run():
    import app as appmod
    from core.founder import INBOX
    appmod.RUNS["run-a"] = {"id": "run-a", "brief": "Idea A", "result": None, "status": "running", "mock": True}
    appmod.RUNS["run-b"] = {"id": "run-b", "brief": "Idea B", "result": None, "status": "running", "mock": True}
    a = INBOX.open("input", "clarify_budget", "Question of A?", run="run-a")
    b = INBOX.open("input", "clarify_budget", "Question of B?", run="run-b")
    try:
        assert [i["id"] for i in appmod._pending_items("run-a")] == [a["id"]]
        assert [i["id"] for i in appmod._pending_items("run-b")] == [b["id"]]
        page = appmod.app.test_client().get("/approvals").get_data(as_text=True)
        assert "Question of A?" in page and "Question of B?" in page
        assert "From the run" in page and "Idea A" in page and "Idea B" in page
    finally:
        INBOX.answer(a["id"], "x")
        INBOX.answer(b["id"], "x")
        appmod.RUNS.pop("run-a", None)
        appmod.RUNS.pop("run-b", None)


# ------------------------------------------------------------------ 4. the gate override understands the founder (M1)
@pytest.mark.parametrize("text,expected", [
    ("go", "go"), ("Go on", "go"), ("  CONTINUE! ", "go"), ("repeat", "repeat"), ("run again", "repeat"),
    ("rethink", "pivot"), ("pivot", "pivot"), ("stop", "stop"), ("Stop here.", "stop"),
    ("I don't know", None), ("yes", None), ("", None), ("go go go", None)])
def test_TC_BUG4_override_words_are_understood(text, expected):
    assert orchestrator.parse_override(text) == expected


def test_TC_BUG4_an_unclear_answer_is_asked_again_and_the_second_answer_counts():
    ctx = make_ctx(pathlib.Path(__import__("tempfile").mkdtemp()))
    ctx.founder = SeqFounder(["I don't know", "pivot"])
    assert orchestrator.ask_override(ctx, 2, "stop") == ("pivot", "pivot")
    assert len(ctx.founder.prompts) == 2 and ctx.founder.prompts[1].startswith("I did not understand")


def test_TC_BUG4_after_three_unclear_answers_the_run_stops_and_the_log_says_why(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.founder = SeqFounder(["???", "hmm", "no idea"])
    ctx.approvals.request = lambda *a, **k: False             # the founder rejects the verdict
    res = type("R", (), {"outcome": "go", "reasons": [], "metrics": {}})()
    assert orchestrator.founder_gate(ctx, 1, res) == "stop" and len(ctx.founder.prompts) == 3
    entry = [e for e in ctx.log.entries() if e["action"] == "gate_override_1"][0]
    assert entry["outcome"] == "stop" and entry["unrecognized_answer"] == "no idea"


def test_TC_BUG4_a_scripted_override_is_never_asked_twice_and_a_clear_word_works(tmp_path):
    inputs = json.loads(DEMO_INPUTS.read_text(encoding="utf-8"))
    inputs["approvals"] = {"default": "reject"}
    inputs["gate_override_1"] = "go on"
    ctx = make_ctx(tmp_path / "a", founder_inputs=inputs)
    res = type("R", (), {"outcome": "stop", "reasons": ["why"], "metrics": {}})()
    assert orchestrator.founder_gate(ctx, 1, res) == "go"
    inputs["gate_override_1"] = "I don't know"
    ctx2 = make_ctx(tmp_path / "b", founder_inputs=inputs)
    assert orchestrator.founder_gate(ctx2, 1, res) == "stop"
    assert [e["action"] for e in ctx2.log.entries()].count("founder_input:gate_override_1") == 1


# ------------------------------------------------------------------ 5 and 10. hints and buttons (M3)
def _render(items):
    return ENV.get_template("_pending.html").render(items=items)


def _q(key, options=()):
    return {"id": 1, "kind": "input", "key": key, "label": key, "prompt": "Q?", "options": list(options), "phase": 1}


def test_TC_BUG5_the_i_dont_know_hint_appears_only_on_clarifying_questions():
    assert "Not sure? Type" in _render([_q("clarify_budget")])
    for key, opts in (("gate_override_1", ["go", "stop"]), ("stop_alternative_2", ["A", "stop here"]),
                      ("option_budget", ["x", "none of these"])):
        html = _render([_q(key, opts)])
        assert "Not sure?" not in html and "Or type your own answer here" in html
    other = _render([_q("interview_notes")])
    assert "Not sure?" not in other and "Label made-up data as SAMPLE or MOCKED" in other


def test_TC_BUG10_override_buttons_have_friendly_labels_but_keep_their_values():
    html = _render([_q("gate_override_1", ["go", "repeat", "pivot", "stop"])])
    for value, label in (("go", "Go on to the next phase"), ("repeat", "Run this phase again"),
                         ("pivot", "Step back and rethink"), ("stop", "Stop here")):
        assert f'value="{value}">{label}</button>' in html
    plain = _render([_q("option_budget", ["Sell on Gumroad"])])
    assert 'value="Sell on Gumroad">Sell on Gumroad</button>' in plain


# ------------------------------------------------------------------ 6, 8, 11. other directions after a STOP (M3)
SCORES = {"chosen": "Idea A", "ranked": [
    {"name": "Idea A", "score": 7.0, "reasons": ["need: x"]},
    {"name": "A client onboarding kit for designers", "score": 6.0, "reasons": ["need: y", "market: unknown"]},
    {"name": "A portfolio case-study template", "score": 5.0, "reasons": ["need: w"]}]}


def _alt_ctx(tmp_path, answers):
    ctx = make_ctx(tmp_path)
    ctx.store.put("phase1_step7_opportunity_scores", SCORES, "# scores", agent="test")
    ctx.founder = SeqFounder(answers)
    return ctx


def test_TC_BUG6_after_the_restart_is_used_nobody_is_asked_and_the_file_says_why(tmp_path):
    ctx = _alt_ctx(tmp_path, ["1"])
    assert alternatives.offer(ctx, 2, ["why"], can_restart=False) is None
    assert ctx.founder.prompts == []
    md = (ctx.out_dir / "phase2_gate_alternatives.md").read_text(encoding="utf-8")
    assert "already tried" in md
    entry = [e for e in ctx.log.entries() if e["action"] == "stop_alternative_2"][0]
    assert entry["asked"] is False and entry["approved_by"] is None


@pytest.mark.parametrize("answer,expected", [
    ("1", 0), ("2", 1), ("3", None), ("0", None), ("a client onboarding kit for designers", 0),
    ("onboarding", 0), ("the portfolio one", 1), ("case-study template please", 1),
    ("kit for the onboarding of clients", 0), ("template", 1), ("designers", 0), ("", None), ("hmm", None)])
def test_TC_BUG8_typed_directions_are_matched_by_number_name_or_words(answer, expected):
    names = ["A client onboarding kit for designers", "A portfolio case-study template"]
    assert alternatives.match_alternative(answer, names) == expected


def test_TC_BUG8_a_word_that_fits_two_directions_matches_neither():
    names = ["A Notion template pack", "A Sheets template pack", "A brand kit"]
    for typed in ("template", "template pack", "pack"):
        assert alternatives.match_alternative(typed, names) is None
    assert alternatives.match_alternative("the notion one", names) == 0


def test_TC_BUG8_something_unclear_is_asked_once_more_and_stop_words_are_not(tmp_path):
    ctx = _alt_ctx(tmp_path, ["hmm, not sure what to pick", "the portfolio one"])
    assert alternatives.offer(ctx, 1, [])["name"] == "A portfolio case-study template"
    assert len(ctx.founder.prompts) == 2 and ctx.founder.prompts[1].startswith("I did not understand")
    for word in ("stop here", "stop", "I don't know", "none of these"):
        c = _alt_ctx(tmp_path / word.replace(" ", "_").replace("'", ""), [word])
        assert alternatives.offer(c, 1, []) is None and len(c.founder.prompts) == 1


def test_TC_BUG8_two_unclear_answers_in_a_row_mean_stop_and_are_logged(tmp_path):
    ctx = _alt_ctx(tmp_path, ["blah", "still blah"])
    assert alternatives.offer(ctx, 1, []) is None and len(ctx.founder.prompts) == 2
    entry = [e for e in ctx.log.entries() if e["action"] == "stop_alternative_1"][0]
    assert entry["choice"] == "stop here" and entry["provenance"] == "WEB"


def test_TC_BUG11_the_file_warns_that_the_scores_rest_on_thin_evidence(tmp_path):
    ctx = _alt_ctx(tmp_path, ["stop here"])
    alternatives.offer(ctx, 1, ["why"])
    md = (ctx.out_dir / "phase1_gate_alternatives.md").read_text(encoding="utf-8")
    assert "starting points to research, not as better bets" in md and "same idea in different words" in md


def test_TC_BUG11_a_scripted_default_is_logged_as_a_default_not_as_a_founder_choice(tmp_path):
    ctx = make_ctx(tmp_path)                                   # scripted founder without a stop_alternative key
    ctx.store.put("phase1_step7_opportunity_scores", SCORES, "# scores", agent="test")
    assert alternatives.offer(ctx, 1, ["why"]) is None
    entry = [e for e in ctx.log.entries() if e["action"] == "stop_alternative_1"][0]
    assert entry["provenance"] == "SCRIPTED_DEFAULT" and entry["approved_by"] is None
    md = (ctx.out_dir / "phase1_gate_alternatives.md").read_text(encoding="utf-8")
    assert "the scripted demo file has no answer for this question" in md


def test_TC_BUG11_a_scripted_answer_keeps_its_label(tmp_path):
    inputs = json.loads(DEMO_INPUTS.read_text(encoding="utf-8"))
    inputs["stop_alternative_1"] = "2"
    ctx = make_ctx(tmp_path, founder_inputs=inputs)
    ctx.store.put("phase1_step7_opportunity_scores", SCORES, "# scores", agent="test")
    assert alternatives.offer(ctx, 1, [])["name"] == "A portfolio case-study template"
    entry = [e for e in ctx.log.entries() if e["action"] == "stop_alternative_1"][0]
    assert entry["provenance"] == "SCRIPTED" and entry["approved_by"] == "founder"


# ------------------------------------------------------------------ 7. "different options" never moves on silently (M3)
def test_TC_BUG7_when_there_are_no_new_options_the_same_ones_are_shown_again_with_a_note(tmp_path):
    from agents.option_suggester import MORE, OptionSuggester
    from tests.test_m2_helpers import ctx_for, run_until
    ctx = ctx_for(tmp_path)
    run_until(ctx, "option_suggester")
    agent = OptionSuggester()
    calls = []

    def suggest(c, field, known, avoid):
        if field != "distribution_channel":
            return ["only option"], None, 0.0, {}
        calls.append(list(avoid))
        return (["Sell on Gumroad", "Post in Facebook groups"] if len(calls) == 1 else []), None, 0.0, {}
    agent._suggest = suggest
    ctx.founder = SeqFounder([MORE, "2"] + ["approve"] * 20)
    agent.run(ctx)
    prompts = [p for p in ctx.founder.prompts if "where you will reach customers" in p]
    assert len(prompts) == 2 and prompts[1].startswith("I could not think of different ideas")
    assert "(new ideas)" not in prompts[1]                      # they are the same ideas, so do not call them new
    first_options = [o for o in ctx.founder.options if o and "Sell on Gumroad" in o][0]
    second_options = [o for o in ctx.founder.options if o and "Sell on Gumroad" in o][1]
    assert MORE in first_options and MORE not in second_options
    assert ctx.store.get("phase1_step2_options")["fields"]["distribution_channel"]["value"] == "Post in Facebook groups"


# ------------------------------------------------------------------ 9. one word for the checkpoint (M3)
def test_TC_BUG9_the_screens_say_checkpoint_not_gate():
    for name in ("_feed.html", "base.html", "_pending.html", "run.html", "approvals.html"):
        text = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "at gate" not in text and "Gate {{" not in text, name
    ui = (ROOT / "ui_feed.py").read_text(encoding="utf-8")
    assert "You overrode Gate" not in ui and "At checkpoint" in ui


def test_TC_BUG9_the_other_directions_question_says_checkpoint(tmp_path):
    ctx = _alt_ctx(tmp_path, ["stop here"])
    alternatives.offer(ctx, 1, [])
    assert "checkpoint 1" in ctx.founder.prompts[0] and "Gate" not in ctx.founder.prompts[0]


def test_TC_BUG9_an_override_that_equals_the_advice_is_not_called_a_disagreement(tmp_path):
    import ui_feed
    notes = {}
    for chosen in ("go", "pivot"):
        inputs = json.loads(DEMO_INPUTS.read_text(encoding="utf-8"))
        inputs["approvals"] = {"default": "reject"}
        inputs["gate_override_1"] = chosen
        ctx = make_ctx(tmp_path / chosen, brief="SAMPLE brief: a Notion template pack.", founder_inputs=inputs)
        res = orchestrator.run(ctx, through=1)
        run = {"id": "r", "ctx": ctx, "status": "finished", "mock": True, "result": res, "through": 1,
               "brief": "t", "error": None}
        notes[chosen] = [b["text"] for b in ui_feed.build_feed(run, {}) if b["type"] == "note"
                         and "checkpoint" in b["text"]]
    assert any("the same as the system's advice" in t for t in notes["go"])
    assert any("you disagreed" in t for t in notes["pivot"]) and not any("Gate" in t for t in notes["pivot"])


# ------------------------------------------------------------------ Docker and README (M1/M2)
def test_TC_HARDEN_the_founder_page_is_published_on_this_machine_only():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8000:8000"' in compose and '- "8000:8000"' not in compose


def test_TC_HARDEN_the_docker_build_leaves_local_files_out():
    lines = {l.strip() for l in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    assert {".git", ".env", "runs", "CONTEXT.md", "PROGRESS_*.md"} <= lines and "!.env.example" in lines
    assert "outputs" not in lines and "demo" not in lines        # the image still needs the committed demo run


def test_TC_HARDEN_the_readme_tells_a_reader_without_a_gpu_what_to_do():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Without an NVIDIA GPU" in readme and "Offline demo" in readme
