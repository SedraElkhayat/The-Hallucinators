# OWNER: M4
"""store_page_builder agent for Phase 5 Launch.

Renders clean static HTML store page without scripts, timers, counters, or testimonials.
Buy button is labeled 'MOCKED checkout: no real payment'.
Calls ctx.approvals.request and marks released only if approved.
"""
from __future__ import annotations

import html

from agents.m4_common import M4Agent
from core.contracts import Context


class StorePageBuilder(M4Agent):
    name = "store_page_builder"
    phase = 5
    step = "phase5_step2_store_page"
    inputs = ["phase4_step1_pricing", "phase4_step2_offer", "phase4_step3_policies"]
    tools = []
    required_keys = ["title", "description", "price_usd", "bullets"]
    kind = "llm"

    def check_inputs(self, ctx: Context) -> None:
        pass

    def render_html(self, data: dict) -> str:
        title = html.escape(str(data.get("title", "Digital Product Store")))
        description = html.escape(str(data.get("description", "")))
        price = float(data.get("price_usd", 29.0))
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
  <div class="price">${price:.2f} USD</div>
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
        try:
            data["price_usd"] = float(data.get("price_usd", 29.0))
        except (ValueError, TypeError):
            data["price_usd"] = 29.0

        bullets = data.get("bullets")
        if not isinstance(bullets, list) or not bullets:
            data["bullets"] = [
                "Bilingual Notion & Google Sheets dashboard",
                "Client revision and invoice tracking",
                "MOCKED checkout: no real payment",
            ]

        # Render static HTML
        html_content = self.render_html(data)
        ctx.store.put_file(self.step, "html", html_content, self.name)

        # Request founder approval
        approved = ctx.approvals.request("store_page", f"Store Page: {data.get('title')}", html_content, self.phase)
        data["released"] = bool(approved)
        data["mocked"] = True
        return data
