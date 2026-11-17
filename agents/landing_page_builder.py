"""landing_page_builder: waitlist page copy from the model, static HTML rendered by code.

The page is a draft. The founder approves or rejects it via ctx.approvals (enforced in code);
a rejection halts Phase 2 through ctx.extra["halt_phase"].
"""
import html
import re

from agents.base import Agent
from agents.m3_common import (M3InputsMixin, P1_IDEA_CARD, P2_CANVAS, P2_LANDING, P2_PLAN,
                              content_violations, get_artifact, guardrail_findings)

DRAFT_LINE = "Draft for the founder to review. Waitlist sign-up only; no purchase."
_PRICE = re.compile(r"(?:[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:usd|egp|eur|gbp|dollars?|pounds?)\b|\bfree\b trial)", re.I)


def _clean(text, allow_price: bool) -> str:
    """Return the text if it passes the honesty checks, else an empty string."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    if not allow_price and _PRICE.search(text):
        return ""
    if content_violations(text) or guardrail_findings(text):
        return ""
    return text


def render_landing_html(copy: dict, plan: dict) -> tuple[str, list[str]]:
    """Static page: no script, no external resources, no counters, timers or testimonials."""
    allow_price = bool(plan.get("price") or plan.get("show_price"))
    removed = []
    headline = _clean(copy.get("headline"), allow_price)
    if not headline:
        removed.append("headline")
        headline = "Product draft"
    sub = _clean(copy.get("subheadline"), allow_price)
    if not sub and copy.get("subheadline"):
        removed.append("subheadline")
    bullets = []
    raw_bullets = copy.get("bullets") or []
    if isinstance(raw_bullets, str):
        raw_bullets = [raw_bullets]
    for b in raw_bullets[:5]:
        c = _clean(b, allow_price)
        (bullets.append(c) if c else removed.append(f"bullet: {str(b)[:60]}"))
    cta = _clean(copy.get("call_to_action"), allow_price) or "Join the waitlist"
    price_line = ""
    if allow_price and plan.get("price"):
        price_line = f'<p class="price">Planned price: {html.escape(str(plan.get("price")))}</p>'

    e = html.escape
    items = "\n".join(f"      <li>{e(b)}</li>" for b in bullets)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(headline)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #222; }}
    .draft {{ background: #fff4d6; border: 1px solid #e0c060; padding: .5rem .75rem; }}
    .cta {{ display: inline-block; padding: .6rem 1rem; background: #1f4e79; color: #fff; text-decoration: none; border-radius: 4px; }}
  </style>
</head>
<body>
  <p class="draft">{e(DRAFT_LINE)}</p>
  <h1>{e(headline)}</h1>
  <p>{e(sub)}</p>
  <ul>
{items}
  </ul>
  {price_line}
  <p><a class="cta" href="#waitlist">{e(cta)}</a></p>
  <section id="waitlist">
    <h2>Waitlist</h2>
    <p>The founder adds the sign-up link here before publishing. Joining the waitlist is free and is not a purchase.</p>
  </section>
</body>
</html>
"""
    return page, removed


class LandingPageBuilder(M3InputsMixin, Agent):
    name = "landing_page_builder"
    phase = 2
    step = P2_LANDING
    inputs = [P2_PLAN, P2_CANVAS, P1_IDEA_CARD]
    tools = []
    required_keys = ["headline", "subheadline", "bullets", "call_to_action"]
    kind = "llm"

    def run(self, ctx):
        result = super().run(ctx)  # model call, required keys, guardrails, artifact, log entry
        copy = dict(result.data or {})
        plan = get_artifact(ctx, P2_PLAN) or {}
        page, removed = render_landing_html(copy, plan)
        ctx.store.put_file(self.step, "html", page, self.name)

        title = f"Landing page draft: {copy.get('headline') or 'waitlist page'}"
        approved = bool(ctx.approvals.request("landing_page", title, page, phase=2))
        if not approved:
            ctx.extra["halt_phase"] = "landing page rejected by the founder"

        copy.update({
            "html_file": f"{self.step}.html",
            "founder_approved": approved,
            "status": "approved draft (the founder publishes it)" if approved else "rejected by the founder",
            "removed_by_code": removed,
        })
        md = (result.markdown or "") + (
            f"\n\n---\nHTML draft: `{self.step}.html`. {DRAFT_LINE}\n\n"
            f"Founder decision: {'approved' if approved else 'rejected'}.\n")
        if removed:
            md += "Removed by code checks: " + "; ".join(removed) + "\n"
        ctx.store.put(self.step, copy, md, self.name, list(result.sources or []))
        result.data, result.markdown = copy, md
        return result
