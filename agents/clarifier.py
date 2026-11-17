"""clarifier (founder kind): find the brief's missing facts and ask the founder, highest decision impact first.

Gap score of a field = weight x missing. Up to 2 rounds, at most 4 questions per round. Each round makes one
model call that says which fields the brief already states and drafts specific questions. The first
question of round 1 is always "what is being sold, and is it digital?" when product_type is missing.
Every field is asked once. A blank or "I don't know" answer stays ``unknown`` and is never asked again: the
option_suggester that follows proposes options for it. The founder can type ``skip`` to stop. Founder keys: ``clarify_<field>``.
"""
from agents.base import Agent
from agents.m2_common import CLARIFICATION, ask_model, banner, blocked, clip, is_mocked, is_unknown, redact_input

FIELDS = {"target_customer": 5, "problem": 5, "product_type": 5, "budget": 4, "time_per_week": 4,
          "founder_skills": 4, "monetization_idea": 3, "distribution_channel": 3, "differentiation": 3,
          "values_and_limits": 2}
DEFAULT_QUESTIONS = {
    "target_customer": "Who exactly is the customer? Describe one specific person who has this problem.",
    "problem": "What problem does that customer have today, and what happens when it is not solved?",
    "product_type": "What exactly is being sold, and is it digital (a template, course, tool, guide, software)?",
    "budget": "How much money (in USD) can you spend on this in total?",
    "time_per_week": "How many hours per week can you work on this?",
    "founder_skills": "Which of your skills and experience are relevant to building and selling this?",
    "monetization_idea": "How do you expect to charge for it (one-time price, subscription, other)?",
    "distribution_channel": "Where do your customers already spend time, online or offline, where you could reach them?",
    "differentiation": "Why would a customer choose yours over what they use today?",
    "values_and_limits": "Is there anything you will not do (for example data you will not collect)?",
}
FIELD_LABELS = {
    "target_customer": "who your customer is", "problem": "the problem you solve", "product_type": "what you sell",
    "budget": "your budget", "time_per_week": "your weekly time", "founder_skills": "your skills",
    "monetization_idea": "how you will charge", "distribution_channel": "where you will reach customers",
    "differentiation": "what makes yours different", "values_and_limits": "what you will not do",
}
NOT_SURE = " Not sure? Type “I don't know” and I will suggest some options for you to choose from."
FIRST_QUESTION = DEFAULT_QUESTIONS["product_type"]
MAX_ROUNDS, MAX_PER_ROUND, MIN_GAP = 2, 4, 5


def gap_score(fields: dict) -> int:
    return sum(w for f, w in FIELDS.items() if fields[f]["status"] != "answered")


class Clarifier(Agent):
    name = "clarifier"
    phase = 1
    step = CLARIFICATION
    inputs: list = []
    tools: list = []
    required_keys = ["fields", "questions_asked", "rounds"]
    kind = "founder"

    def _user(self, ctx, fields: dict, rnd: int) -> str:
        import json
        known = {f: v["value"] for f, v in fields.items() if v["status"] == "answered"}
        payload = {"brief": clip(ctx.brief or "", 3000), "round": rnd, "known_answers": known,
                   "fields": list(FIELDS)}
        return "<data>\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n</data>\n" \
               "Answer with the JSON object described in your instructions."

    def run(self, ctx):
        """Ask the founder about missing brief fields, in rounds, until the weighted gap score is small enough.

        Each round the model marks the fields the brief already states and drafts questions; the founder answers
        through ``ctx.founder.ask`` (a field is asked once, "skip" ends the clarification). Answers pass
        the input guardrail before they become field values."""
        fields = {f: {"value": "unknown", "status": "unknown", "source": None} for f in FIELDS}
        asked_count = {f: 0 for f in FIELDS}
        log, idea, model, cost, tokens = [], None, None, 0.0, {"tokens_in": 0, "tokens_out": 0}
        stopped, rounds = False, 0
        for rnd in range(1, MAX_ROUNDS + 1):
            unasked = [f for f in FIELDS if fields[f]["status"] != "answered" and asked_count[f] < 1]
            if stopped or gap_score(fields) < MIN_GAP or not unasked:
                break
            rounds = rnd
            drafted = {}
            try:
                data, model, c, t = ask_model(self, ctx, self._user(ctx, fields, rnd), ["stated", "questions"])
                cost += c
                tokens = {k: tokens[k] + t[k] for k in tokens}
                for f, v in (data.get("stated") or {}).items():
                    if f in FIELDS and fields[f]["status"] != "answered" and isinstance(v, str) \
                            and not is_unknown(v) and not blocked(v):
                        fields[f] = {"value": v.strip(), "status": "answered", "source": "brief"}
                if rnd == 1 and isinstance(data.get("idea"), str) and not is_unknown(data["idea"]) \
                        and not blocked(data["idea"]):
                    idea = data["idea"].strip()
                for q in data.get("questions") or []:
                    if isinstance(q, dict) and q.get("field") in FIELDS and isinstance(q.get("question"), str) \
                            and q["question"].strip() and not blocked(q["question"]):
                        drafted.setdefault(q["field"], q["question"].strip())
            except Exception as e:  # noqa: BLE001 - without the model, ask the default questions
                ctx.log.action(self.name, "clarifier_model_failed", error=str(e)[:200])
            missing = [f for f in FIELDS if fields[f]["status"] != "answered" and asked_count[f] < 1]
            missing.sort(key=lambda f: -FIELDS[f])  # stable: weight order, then field order
            if rnd == 1 and "product_type" in missing:
                missing.remove("product_type")
                missing.insert(0, "product_type")
            for f in missing[:MAX_PER_ROUND]:
                question = FIRST_QUESTION if (f == "product_type" and rnd == 1) else drafted.get(f, DEFAULT_QUESTIONS[f])
                question = question + NOT_SURE
                raw = ctx.founder.ask(f"clarify_{f}", question)
                asked_count[f] += 1
                if (raw or "").strip().lower() == "skip":
                    stopped = True
                    log.append({"round": rnd, "field": f, "question": question, "answer_status": "skipped"})
                    break
                answer, flags = redact_input(raw)
                status = "unknown" if is_unknown(answer) else "answered"
                if status == "answered":
                    fields[f] = {"value": answer.strip(), "status": "answered", "source": "founder"}
                    if flags:
                        fields[f]["input_flags"] = flags
                log.append({"round": rnd, "field": f, "question": question, "answer_status": status})
                ctx.log.action(self.name, "clarify_question", field=f, round=rnd, question=question,
                               answer=answer[:300], answer_status=status, input_flags=flags)
        data = {"fields": fields, "questions_asked": log, "rounds": rounds, "idea": idea,
                "gap_score_remaining": gap_score(fields), "stopped_by_founder": stopped}
        md = ["# Clarification", "", f"Rounds: {rounds}. Remaining gap score: {data['gap_score_remaining']}.",
              f"Founder's starting idea: {idea or 'none stated'}", "",
              "| Field | Value | Status | Source |", "|---|---|---|---|"]
        md += [f"| {f} | {str(v['value']).replace('|', '/')} | {v['status']} | {v['source'] or '-'} |"
               for f, v in fields.items()]
        md += ["", "## Questions asked", ""] + [f"- Round {q['round']} `{q['field']}`: {q['question']} "
                                                 f"({q['answer_status']})" for q in log]
        mocked = is_mocked(ctx, model)
        return self.save(ctx, data, markdown=banner(mocked) + "\n".join(md) + "\n", sources=[], model=model, cost=cost,
                         mocked=mocked, **tokens)
