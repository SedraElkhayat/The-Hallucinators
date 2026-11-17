# OWNER: M4
"""MOCKED reconciliation module.

Matches orders, payments, refunds, fees and payouts.
Payout = payments minus fees minus refunds.
"""
from __future__ import annotations

from typing import Any, Iterable


def _to_sum(val: Any) -> float:
    """Helper to sum numbers from a float, int, or list of dicts/numbers."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple, set)):
        total = 0.0
        for item in val:
            if isinstance(item, (int, float)):
                total += float(item)
            elif isinstance(item, dict):
                total += float(item.get("amount_usd", item.get("amount", 0.0)))
        return round(total, 4)
    return 0.0


def reconcile(orders: Any, payments: Any, refunds: Any, fees: Any, payouts: Any) -> dict:
    """Reconcile transactions and verify payout ledger balance.

    Formula: payout = payments - fees - refunds
    """
    total_orders = _to_sum(orders)
    total_payments = _to_sum(payments)
    total_refunds = _to_sum(refunds)
    total_fees = _to_sum(fees)
    total_payouts = _to_sum(payouts)

    mismatches = []

    # Check 1: Payments should match ordered amounts for completed orders
    if total_orders > 0 and abs(total_payments - total_orders) > 0.01:
        mismatches.append(
            f"Payments total (${total_payments:.2f}) does not match orders total (${total_orders:.2f})"
        )

    # Check 2: Payout = payments - fees - refunds
    expected_payout = round(total_payments - total_fees - total_refunds, 4)
    if abs(total_payouts - expected_payout) > 0.01:
        mismatches.append(
            f"Payout (${total_payouts:.2f}) does not match expected (${expected_payout:.2f} = "
            f"payments ${total_payments:.2f} - fees ${total_fees:.2f} - refunds ${total_refunds:.2f})"
        )

    balanced = len(mismatches) == 0

    return {
        "balanced": balanced,
        "mismatches": mismatches,
        "summary": {
            "total_orders_usd": round(total_orders, 2),
            "total_payments_usd": round(total_payments, 2),
            "total_refunds_usd": round(total_refunds, 2),
            "total_fees_usd": round(total_fees, 2),
            "total_payouts_usd": round(total_payouts, 2),
            "expected_payout_usd": round(expected_payout, 2),
        },
        "mocked": True,
    }
