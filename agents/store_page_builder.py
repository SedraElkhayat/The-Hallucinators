# OWNER: M4
"""store_page_builder agent for Phase 5 Launch.

Renders clean static HTML store page without scripts, timers, counters, or testimonials.
Buy button is labeled 'MOCKED checkout: no real payment'.
Calls ctx.approvals.request and marks released only if approved.
"""
from __future__ import annotations

import html

from agents.m4_store_site import SITE_DIR, build_store_site, render_store_site, site_checks, write_site
from agents.m4_common import M4Agent, launch_copy_violations, price_from_pricing, to_float
from core.contracts import Context


class StorePageBuilder(M4Agent):
    name = "store_page_builder"
    phase = 5
    step = "phase5_step2_store_page"
    inputs = ["phase4_step1_pricing", "phase4_step2_offer", "phase4_step3_policies", "phase3_step3_build"]
    tools = []
    required_keys = ["title", "description", "price_usd", "bullets"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def render_html(self, data: dict) -> str:
        title = html.escape(str(data.get("title", "Digital Product Store")))
        description = html.escape(str(data.get("description", "")))
        price = data.get("price_usd")
        price_html = f"${float(price):.2f} USD" if price is not None else "Price: to be set by the founder"
        bullets = data.get("bullets", [])
        bullet_items = "\n".join(f"      <li>{html.escape(str(b))}</li>" for b in bullets)

        # Static clean HTML: no script, no timer, no counter, no fake review
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 650px; margin: 40px auto; padding: 0 20px; color: #222; }}
    .badge {{ display: inline-block; background: #eef2ff; color: #4338ca; padding: 4px 8px; border-radius: 4px; font-size: 13px; font-weight: 600; margin-bottom: 12px; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    .desc {{ font-size: 16px; color: #555; margin-bottom: 24px; }}
    .price {{ font-size: 24px; font-weight: 700; margin-bottom: 20px; }}
    ul {{ margin-bottom: 30px; padding-left: 20px; }}
    li {{ margin-bottom: 8px; }}
    .btn {{ display: inline-block; background: #111827; color: #fff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px; border: none; cursor: default; }}
    .disclaimer {{ margin-top: 30px; font-size: 12px; color: #777; border-top: 1px solid #eee; padding-top: 15px; }}
  </style>
</head>
<body>
  <div class="badge">DRAFT: prepared for founder review</div>
  <h1>{title}</h1>
  <p class="desc">{description}</p>
  <div class="price">{price_html}</div>
  <ul>
{bullet_items}
  </ul>
  <div>
    <button class="btn" type="button">MOCKED checkout: no real payment</button>
  </div>
  <div class="disclaimer">
    <p>Notice: All payments and product fulfillments are MOCKED simulations. No real money or payment details are collected.</p>
  </div>
</body>
</html>
"""

    def post_process(self, ctx: Context, data: dict) -> dict:
        pricing_price = price_from_pricing(ctx)
        data["price_usd"] = to_float(data.get("price_usd"), pricing_price)
        if pricing_price is not None and data["price_usd"] != pricing_price:
            # The page shows the price chosen in Phase 4, not a new one.
            data["price_usd"] = pricing_price

        bullets = data.get("bullets")
        if not isinstance(bullets, list) or not bullets:
            data["bullets"] = [
                "STUBBED: the model returned no feature bullets; the founder fills these in.",
            ]

        # Code rules: no user/sales counts, testimonials, income or time-saved numbers, no founder signature.
        removed = []
        for key in ("title", "description"):
            v = launch_copy_violations(str(data.get(key, "")))
            if v:
                removed.append({"field": key, "reasons": v})
                data[key] = f"STUBBED: {key} removed by a code check ({', '.join(v)}); the founder writes it."
        kept = []
        for b in data.get("bullets") or []:
            v = launch_copy_violations(str(b))
            if v:
                removed.append({"field": "bullet", "reasons": v})
            else:
                kept.append(str(b))
        data["bullets"] = kept or ["STUBBED: no feature bullets passed the checks; the founder fills these in."]
        if removed:
            data["removed_by_checks"] = removed

        # Render static HTML
        html_content = self.render_html(data)
        ctx.store.put_file(self.step, "html", html_content, self.name)

        # Store website (CONTEXT.md 4b.7): index.html + policy pages, checked before approval.
        pricing = ctx.store.get("phase4_step1_pricing") if ctx.store.has("phase4_step1_pricing") else {}
        documents = ctx.store.get("phase4_step3_policies").get("documents", []) if ctx.store.has("phase4_step3_policies") else []
        phase3 = ctx.store.get("phase3_step3_build") if ctx.store.has("phase3_step3_build") else {}
        is_assumption = bool(pricing.get("is_assumption", True))
        try:
            files = build_store_site(data, documents, is_assumption, phase3)
            template = "site_template/index.html (M3)"
        except FileNotFoundError:
            files = render_store_site(data, documents, is_assumption)
            template = "FALLBACK: plain page (site_template/index.html missing)"
        root = write_site(ctx.out_dir, files)
        checks = site_checks(root)
        data["site"] = {"folder": SITE_DIR, "template": template, "files": sorted(files), "site_checks": checks}
        ctx.log.action(self.name, "store_site_written", outcome="passed" if checks["passed"] else "failed")

        # Request founder approval
        title = f"Store Page: {data.get('title')}"
        approved = ctx.approvals.request("store_page", title, html_content, self.phase)
        if approved:
            # approval.release() records the release; it refuses anything the founder did not approve.
            ctx.approvals.release("store_page", title, html_content, self.phase)
        data["released"] = bool(approved)
        data["checkout"] = "MOCKED: no real payment"
        data.pop("mocked", None)
        return data
