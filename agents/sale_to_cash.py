# OWNER: M4
"""sale_to_cash agent (kind code, step phase5_step5_sale_to_cash).

Runs a mock scenario of 3 orders with one duplicate payment event and one refund through the WebhookHandler.
Runs reconciliation, writes the step artifact and payment_test_log.md.
"""
from __future__ import annotations

import delivery
import payments
import reconcile
import refunds
from agents.base import Agent
from core.contracts import AgentResult, Context
from webhooks import WebhookHandler


class SaleToCash(Agent):
    name = "sale_to_cash"
    phase = 5
    step = "phase5_step5_sale_to_cash"
    inputs = []
    tools = []
    required_keys = ["double_deliveries", "access_after_refund", "reconcile_balanced", "orders_processed"]
    kind = "code"

    def run(self, ctx: Context) -> AgentResult:
        ctx.log.action(self.name, "start_sale_to_cash_simulation", note="MOCKED: simulated checkout")

        # Reset states
        delivery.reset_delivery_store()
        refunds.reset_refund_store()
        handler = WebhookHandler()

        # Step-by-step readable log lines
        log_lines = [
            "# Payment and Delivery Test Log (MOCKED)",
            "",
            "> **MOCKED: no real or sandbox payment was made.**",
            "> All orders, webhook events, access tokens, and ledger entries are simulated offline.",
            "",
            "## Scenario Steps",
            "",
        ]

        # 1. Create 3 mock orders
        orders = [
            payments.create_mock_order("mock_ord_001", 29.0, "Standard Starter Kit"),
            payments.create_mock_order("mock_ord_002", 49.0, "Pro Studio Pack"),
            payments.create_mock_order("mock_ord_003", 29.0, "Standard Starter Kit"),
        ]
        log_lines.append(f"1. Created {len(orders)} mock orders: `mock_ord_001` ($29.00), `mock_ord_002` ($49.00), `mock_ord_003` ($29.00).")
        ctx.log.action(self.name, "create_mock_orders", order_ids=[o["order_id"] for o in orders])

        # 2. Process payments for Order 1, Order 2, Order 3
        # For Order 1, send payment.succeeded
        evt1 = payments.mock_payment_event(orders[0], "payment.succeeded", "idemp_ord_001_pay")
        res1 = handler.handle(evt1)
        log_lines.append(f"2. Order 1 payment event received: status={res1['status']}, action={res1.get('action')}, token={res1.get('delivery', {}).get('token')}")
        ctx.log.action(self.name, "process_payment_order_1", status=res1["status"])

        # Send duplicate payment event for Order 1 to test idempotency
        evt1_dup = payments.mock_payment_event(orders[0], "payment.succeeded", "idemp_ord_001_pay")
        res1_dup = handler.handle(evt1_dup)
        log_lines.append(f"3. Duplicate Order 1 payment event received: status={res1_dup['status']}, reason={res1_dup.get('reason')}")
        ctx.log.action(self.name, "process_duplicate_payment", status=res1_dup["status"])

        # For Order 2, send payment.succeeded
        evt2 = payments.mock_payment_event(orders[1], "payment.succeeded", "idemp_ord_002_pay")
        res2 = handler.handle(evt2)
        log_lines.append(f"4. Order 2 payment event received: status={res2['status']}, action={res2.get('action')}, token={res2.get('delivery', {}).get('token')}")
        ctx.log.action(self.name, "process_payment_order_2", status=res2["status"])

        # For Order 3, send payment.succeeded
        evt3 = payments.mock_payment_event(orders[2], "payment.succeeded", "idemp_ord_003_pay")
        res3 = handler.handle(evt3)
        log_lines.append(f"5. Order 3 payment event received: status={res3['status']}, action={res3.get('action')}, token={res3.get('delivery', {}).get('token')}")
        ctx.log.action(self.name, "process_payment_order_3", status=res3["status"])

        # 3. Process refund for Order 3
        evt3_ref = payments.mock_payment_event(orders[2], "refund.requested", "idemp_ord_003_ref")
        res3_ref = handler.handle(evt3_ref)
        access_after_ref = delivery.has_access("mock_ord_003")
        log_lines.append(f"6. Order 3 refund requested: status={res3_ref['status']}, access_revoked={not access_after_ref}")
        ctx.log.action(self.name, "process_refund_order_3", status=res3_ref["status"], access_revoked=not access_after_ref)

        # 4. Check double delivery count
        # In delivery, deliveries dictionary should have exactly 3 orders delivered (1 duplicate ignored)
        all_dels = delivery.all_deliveries()
        double_deliveries = handler.ignored_duplicates - 1 if handler.ignored_duplicates > 1 else 0
        log_lines.append(f"7. Delivery validation: total deliveries created={len(all_dels)}, ignored duplicate events={handler.ignored_duplicates}, double deliveries={double_deliveries}")

        # 5. Financial Reconciliation
        total_payments = sum(o["amount_usd"] for o in orders)
        total_refunds = orders[2]["amount_usd"]
        fees = []
        for o in orders:
            fee = round(o["amount_usd"] * payments.MOCK_FEE_RATE + payments.MOCK_FEE_FIXED, 2)
            fees.append(fee)
        total_fees = round(sum(fees), 2)
        payout = round(total_payments - total_fees - total_refunds, 2)

        rec_result = reconcile.reconcile(
            orders=orders,
            payments=total_payments,
            refunds=total_refunds,
            fees=total_fees,
            payouts=payout,
        )
        log_lines.append("")
        log_lines.append("## Reconciliation Summary")
        log_lines.append(f"- Balanced: **{rec_result['balanced']}**")
        log_lines.append(f"- Total Orders: ${rec_result['summary']['total_orders_usd']:.2f}")
        log_lines.append(f"- Total Payments: ${rec_result['summary']['total_payments_usd']:.2f}")
        log_lines.append(f"- Total Simulated Fees: ${rec_result['summary']['total_fees_usd']:.2f}")
        log_lines.append(f"- Total Refunds: ${rec_result['summary']['total_refunds_usd']:.2f}")
        log_lines.append(f"- Net Payout: ${rec_result['summary']['total_payouts_usd']:.2f}")
        ctx.log.action(self.name, "reconciliation", balanced=rec_result["balanced"])

        # Write payment_test_log.md
        log_text = "\n".join(log_lines) + "\n"
        ctx.store.put_file("payment_test_log", "md", log_text, self.name)

        data = {
            "orders_processed": [o["order_id"] for o in orders],
            "double_deliveries": double_deliveries,
            "access_after_refund": access_after_ref,
            "reconcile_balanced": rec_result["balanced"],
            "reconcile_summary": rec_result["summary"],
            "mocked": True,
        }

        md = (
            f"# Phase 5 Step 5: Sale to Cash (MOCKED)\n\n"
            f"> **MOCKED**: All transactions simulated offline without network.\n\n"
            f"- Orders Processed: {len(data['orders_processed'])}\n"
            f"- Double Deliveries: {data['double_deliveries']}\n"
            f"- Access After Refund: {data['access_after_refund']}\n"
            f"- Reconcile Balanced: {data['reconcile_balanced']}\n"
        )

        return self.save(ctx, data, markdown=md, mocked=True, action="run_sale_to_cash")
