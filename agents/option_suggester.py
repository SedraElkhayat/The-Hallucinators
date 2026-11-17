"""option_suggester (founder kind): for every field the founder left unknown, suggest 2 to 3 options and let
the founder approve one. Nothing is assumed silently: only founder-approved options become values.

Founder key ``option_<field>``. The answer can be an option's text, its number (1, 2, 3), "approve" (= the
first option, as shown first), "none of these" (stays unknown), or the founder's own value.
Afterwards the scope classification is run again with the updated fields (same prompt as scope_classifier)
and ``phase1_step1_scope`` is overwritten; if the product is not clearly digital the phase halts.
"""
import json

from agents.base import Agent
from agents.m2_common import (CLARIFICATION, OPTIONS, SCOPE, ask_model, banner, blocked, clip, get_artifact,
                              is_mocked, is_unknown, redact_input)

NONE = "none of these"
APPROVE_WORDS = {"approve", "approved", "yes", "ok", "okay", "y", "نعم", "موافق"}


def resolve(answer: str, options: list[str]) -> tuple[str, str]:
    """Return (status, value)."""
    a = (answer or "").strip()
    low = a.lower()
    if not a or low in (NONE, "reject", "rejected", "no", "none") or is_unknown(a):
        return "unknown_confirmed", "unknown"
    if low.isdigit() and 1 <= int(low) <= len(options):
        return "suggested_approved", options[int(low) - 1]
    for o in options:
        if low == o.lower():
            return "suggested_approved", o
    if low in APPROVE_WORDS and options:
        return "suggested_approved", options[0]
    return "answered", a


class OptionSuggester(Agent):
    name = "option_suggester"
    phase = 1
    step = OPTIONS
    inputs = [CLARIFICATION]
    tools: list = []
    required_keys = ["fields", "decisions"]
    kind = "founder"

    def run(self, ctx):
        """For each field the founder left unknown, suggest up to three options (labeled as suggestions, not
        facts); only an option the founder approves becomes the value. Then re-run the scope check."""
        self.check_inputs(ctx)
        clar = get_artifact(ctx, CLARIFICATION) or {}
        fields = {f: dict(v) for f, v in (clar.get("fields") or {}).items() if isinstance(v, dict)}
        decisions, model, cost = [], None, 0.0
        tokens = {"tokens_in": 0, "tokens_out": 0}
        known = {f: v.get("value") for f, v in fields.items() if v.get("status") == "answered"}
        for f, v in fields.items():
            if v.get("status") == "answered":
                continue
            options = []
            try:
                user = "<data>\n" + json.dumps({"brief": clip(ctx.brief or "", 2500), "field": f,
                                                "known_answers": known}, ensure_ascii=False, indent=1) + \
                       "\n</data>\nAnswer with the JSON object described in your instructions."
                data, model, c, t = ask_model(self, ctx, user, ["options"])
                cost += c
                tokens = {k: tokens[k] + t[k] for k in tokens}
                options = [str(o).strip() for o in (data.get("options") or [])
                           if isinstance(o, str) and o.strip() and not blocked(o)][:3]
            except Exception as e:  # noqa: BLE001
                ctx.log.action(self.name, "options_model_failed", field=f, error=str(e)[:200])
            if not options:
                decisions.append({"field": f, "options": [], "status": "unknown_confirmed", "value": "unknown",
                                  "note": "no options could be suggested"})
                fields[f] = {"value": "unknown", "status": "unknown_confirmed", "source": None}
                continue
            listing = "; ".join(f"{i}) {o}" for i, o in enumerate(options, 1))
            raw = ctx.founder.ask(f"option_{f}",
                                  f"You did not know '{f}'. SUGGESTIONS (not facts): {listing}. "
                                  f"Approve one, or answer '{NONE}'.", options=options + [NONE])
            answer, _ = redact_input(raw)
            status, value = resolve(answer, options)
            fields[f] = {"value": value, "status": status,
                         "source": "founder_approved_suggestion" if status == "suggested_approved"
                         else "founder" if status == "answered" else None}
            decisions.append({"field": f, "options": options, "status": status, "value": value})
            ctx.log.action(self.name, f"option_decision:{f}", status=status,
                           approved_by="founder" if status == "suggested_approved" else None)
            if status == "answered":
                known[f] = value
            elif status == "suggested_approved":
                known[f] = value
        scope = self.rerun_scope(ctx, fields)
        data = {"fields": fields, "decisions": decisions, "scope_after_options": scope}
        mocked = is_mocked(ctx, model)
        md = ["# Options for unknown fields", "",
              "Suggestions are not facts. Only founder-approved options became values.", "",
              "| Field | Options suggested | Founder decision | Value |", "|---|---|---|---|"]
        md += [f"| {d['field']} | {' / '.join(d['options']) or '-'} | {d['status']} | {d['value']} |"
               for d in decisions] or ["| none | all fields were answered | - | - |"]
        md += ["", f"Scope after clarification: is_digital = {scope.get('is_digital')}"]
        return self.save(ctx, data, markdown=banner(mocked) + "\n".join(md) + "\n", sources=[], model=model,
                         cost=cost, mocked=mocked, **tokens)

    def rerun_scope(self, ctx, fields: dict) -> dict:
        from agents.scope_classifier import ScopeClassifier, normalize_scope
        sc = ScopeClassifier()
        values = {f: v.get("value") for f, v in fields.items()}
        user = "<data>\n" + json.dumps({"brief": clip(ctx.brief or "", 3000), "clarified_fields": values},
                                       ensure_ascii=False, indent=1) + \
               "\n</data>\nAnswer with the JSON object described in your instructions."
        try:
            data, model, c, t = ask_model(sc, ctx, user, sc.required_keys)
            data = normalize_scope(data)
        except Exception as e:  # noqa: BLE001 - no classification means not clearly digital
            data, model, c, t = ({"is_digital": "undetermined", "product_type": "unknown", "excluded_reason": None,
                                  "reasoning": f"scope could not be re-checked: {str(e)[:120]}"}, None, 0.0, {})
        data["rechecked_after"] = "clarification and options"
        sc.save(ctx, data, model=model, cost=c, mocked=is_mocked(ctx, model),
                action="rerun_scope_after_clarification", **t)
        if data["is_digital"] is not True:
            ctx.extra["halt_phase"] = (f"product is not clearly digital and in scope after clarification "
                                       f"(is_digital={data['is_digital']}, reason={data.get('excluded_reason')})")
        return {"is_digital": data["is_digital"], "excluded_reason": data.get("excluded_reason")}
