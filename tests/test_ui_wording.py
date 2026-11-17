"""Plain wording in the web UI (demo feedback): no jargon in buttons, advice explained, terms defined."""
import pathlib

from jinja2 import Environment, FileSystemLoader

ENV = Environment(loader=FileSystemLoader(str(pathlib.Path(__file__).resolve().parent.parent / "templates")))


def _render(items):
    return ENV.get_template("_pending.html").render(items=items)


def _gate(outcome):
    return {"id": 1, "kind": "approval", "key": "gate", "phase": 2, "prompt": f"Gate 2: {outcome}",
            "content": "details here", "options": [], "is_html": False}


def test_TC_UX_gate_question_explains_the_advice_in_plain_words():
    html = _render([_gate("stop")])
    assert "stop here, because the evidence is too weak so far" in html
    assert "It is only advice: you decide" in html
    assert "Even after a stop you can try a different direction" in html
    assert "Agree with the system" in html and "I disagree, let me decide" in html
    assert "raw gate summary" not in html and "Reject and choose myself" not in html


def test_TC_UX_other_outcomes_are_explained_and_only_stop_mentions_a_new_direction():
    assert "repeat this phase to fill the gaps" in _render([_gate("repeat")])
    html = _render([_gate("go")])
    assert "go on to the next phase" in html and "different direction" not in html


def test_TC_UX_a_question_tells_the_user_what_to_type_when_unsure():
    q = {"id": 2, "kind": "input", "key": "clarify_budget", "label": "budget", "prompt": "How much?", "options": []}
    assert "I don't know" in _render([q]) and "I will suggest options" in _render([q])


def test_TC_UX_the_glossary_defines_the_terms_a_new_user_will_not_know():
    html = ENV.get_template("_glossary.html").render()
    for term in ("Checkpoint (gate)", "Kill criterion", "Verified claim", "ASSUMPTION", "ratio", "MOCKED, SAMPLE, SCRIPTED",
                 "Override", "Rethink (pivot)"):
        assert term in html
