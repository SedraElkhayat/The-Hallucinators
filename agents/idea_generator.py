"""idea_generator (llm + founder): only when the brief has no idea. Proposes 3 to 5 candidate ideas from the
founder's skills, time, budget and values, each with sourced claims, and asks the founder to pick one.

Always writes ``phase1_step3_idea_choice`` as well. If the founder already gave an idea, it is recorded as the
choice and no model call is made. Founder key: ``idea_choice`` (a candidate name or number, or the founder's
own idea in words).
"""
import json

from agents.base import Agent
from agents.m2_common import (CLARIFICATION, IDEA_CANDIDATES, IDEA_CHOICE, MAX_PAGE_CHARS, OPTIONS, ask_model,
                              banner, blocked, clip, get_artifact, is_mocked, is_unknown, norm_claims,
                              redact_input, short, untrusted)

OWN = "my own idea"


class IdeaGenerator(Agent):
    name = "idea_generator"
    phase = 1
    step = IDEA_CANDIDATES
    inputs = [CLARIFICATION]
    tools = ["search"]
    required_keys = ["candidates", "chosen", "skipped"]
    kind = "founder"

    def _choice(self, ctx, chosen, source: str, mocked: bool):
        data = {"chosen": chosen, "source": source}
        md = f"{banner(mocked)}# Idea choice\n\nChosen idea: {chosen or 'unknown'}\n\nSource: {source}\n"
        ctx.store.put(IDEA_CHOICE, dict(data, **({"mocked": True} if mocked else {})), md, agent=self.name)
        ctx.log.action(self.name, "record_idea_choice", source=source,
                       approved_by="founder" if source.startswith("founder") else None)

    def run(self, ctx):
        self.check_inputs(ctx)
        clar = get_artifact(ctx, CLARIFICATION) or {}
        idea = clar.get("idea")
        if isinstance(idea, str) and idea.strip() and not is_unknown(idea):
            self._choice(ctx, idea.strip(), "founder_brief", bool(ctx.mock))
            data = {"skipped": True, "candidates": [], "chosen": None,
                    "reason": "The founder's brief already contains an idea."}
            return self.save(ctx, data, markdown=f"{banner(bool(ctx.mock))}# Idea candidates\n\nSkipped: the "
                             f"founder's brief already contains an idea.\n", sources=[], model=None,
                             mocked=bool(ctx.mock), action="skip_idea_generation")
        fields = {f: v.get("value") for f, v in (clar.get("fields") or {}).items() if isinstance(v, dict)}
        opts = get_artifact(ctx, OPTIONS)
        if opts:
            fields.update({f: v.get("value") for f, v in (opts.get("fields") or {}).items() if isinstance(v, dict)})
        results = []
        for q in (f"{short(fields.get('founder_skills'))} digital product ideas",
                  f"{short(fields.get('target_customer'))} problems"):
            try:
                results += ctx.tools.search(self.name, q)
            except Exception as e:  # noqa: BLE001
                ctx.log.action(self.name, "search_failed", query=q, error=str(e)[:200])
        evidence = [{"title": r.get("title"), "url": r.get("url"),
                     "snippet": untrusted(str(r.get("snippet", ""))[:MAX_PAGE_CHARS // 5])} for r in results[:8]]
        user = "<data>\n" + json.dumps({"brief": clip(ctx.brief or "", 2500), "founder": fields,
                                        "search_results": evidence}, ensure_ascii=False, indent=1) + \
               "\n</data>\nAnswer with the JSON object described in your instructions."
        data, model, cost, tokens = ask_model(self, ctx, user, ["candidates"])
        mocked = is_mocked(ctx, model)
        from core.claims import verify_claims
        cands = []
        for c in (data.get("candidates") or [])[:5]:
            if not isinstance(c, dict) or not isinstance(c.get("name"), str) or blocked(c["name"]):
                continue
            c["claims"] = norm_claims(c.get("claims"))
            verify_claims(ctx, c)
            cands.append(c)
        names = [c["name"] for c in cands]
        raw = ctx.founder.ask("idea_choice", "Pick one idea (name or number), or describe your own idea.",
                              options=names + [OWN])
        answer, _ = redact_input(raw)
        low = answer.strip().lower()
        if low.isdigit() and 1 <= int(low) <= len(names):
            chosen, source = names[int(low) - 1], "founder_pick"
        elif any(low == n.lower() for n in names):
            chosen, source = next(n for n in names if n.lower() == low), "founder_pick"
        elif is_unknown(answer) or low in (OWN, "keep my starting idea"):
            chosen, source = None, "founder_gave_no_idea"
        else:
            chosen, source = answer.strip(), "founder_own_idea"
        self._choice(ctx, chosen, source, mocked)
        out = {"skipped": False, "candidates": cands, "chosen": chosen, "choice_source": source}
        srcs = [c2["source_url"] for c in cands for c2 in c["claims"] if c2.get("verified") is True]
        return self.save(ctx, out, sources=srcs, model=model, cost=cost, mocked=mocked, **tokens)
