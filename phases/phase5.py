# OWNER: M4
"""Phase 5: Launch (channel plan, store page, launch posts, compliance review, sale to cash).

Founder keys used in this phase:
- "store_page" (approval request for static store page HTML)
- "launch_post" (approval request for each channel launch post draft)
"""
from __future__ import annotations

from core.contracts import Context
from gates import Check

PHASE = 5
STAGES: list[list[str]] = [
    ["channel_planner"],
    ["store_page_builder"],
    ["launch_post_drafter"],
    ["compliance_reviewer_phase5"],
    ["sale_to_cash"],
]
REVISE = None
PIVOT_TO = 4


def gate_checks(ctx: Context) -> list[Check]:
    return [
        Check("chk_p5_unapproved", "unapproved_released", "<=", 0.0, "stop"),
        Check("chk_p5_s2c_passed", "sale_to_cash_passed", ">=", 1.0, "repeat"),
        Check("chk_p5_double_deliv", "double_deliveries", "<=", 0.0, "stop"),
        Check("chk_p5_reconcile", "reconcile_balanced", ">=", 1.0, "stop"),
    ]


def measure(ctx: Context) -> dict:
    unapproved_released = 0

    # Verify store page approval
    if ctx.store.has("phase5_step2_store_page"):
        sp_data = ctx.store.get("phase5_step2_store_page")
        # If it was marked released, ensure it was properly approved by founder
        if sp_data.get("released"):
            # check decision log for founder approval of store_page
            approvals = [e for e in ctx.log.entries()
                         if e.get("agent") == "founder" and "store_page" in str(e.get("action"))]
            if not approvals:
                unapproved_released += 1

    # Verify launch posts
    if ctx.store.has("phase5_step3_launch_posts"):
        lp_data = ctx.store.get("phase5_step3_launch_posts")
        posts = lp_data.get("posts", [])
        for p in posts:
            if p.get("posted"):
                # System must never post anything automatically
                unapproved_released += 1

    # Check sale-to-cash metrics
    sale_to_cash_passed = 0
    double_deliveries = 0
    reconcile_balanced = 0

    if ctx.store.has("phase5_step5_sale_to_cash"):
        s2c_data = ctx.store.get("phase5_step5_sale_to_cash")
        sale_to_cash_passed = 1
        double_deliveries = int(s2c_data.get("double_deliveries", 0))
        reconcile_balanced = 1 if s2c_data.get("reconcile_balanced") else 0

    return {
        "unapproved_released": unapproved_released,
        "sale_to_cash_passed": sale_to_cash_passed,
        "double_deliveries": double_deliveries,
        "reconcile_balanced": reconcile_balanced,
    }
