# OWNER: M4
"""MOCKED refunds.

Marks the order refunded and revokes delivery access; moves no money.
"""
from __future__ import annotations

import delivery

_REFUNDED_ORDERS: set[str] = set()


def reset_refund_store() -> None:
    """Helper for testing to reset state."""
    _REFUNDED_ORDERS.clear()


def process_refund(order_id: str) -> dict:
    """Marks the order refunded and revokes access via delivery.revoke()."""
    oid = str(order_id)
    _REFUNDED_ORDERS.add(oid)
    delivery.revoke(oid)
    return {
        "order_id": oid,
        "status": "refunded",
        "access_revoked": not delivery.has_access(oid),
        "mocked": True,
    }


def is_refunded(order_id: str) -> bool:
    """Check if an order has been refunded."""
    return str(order_id) in _REFUNDED_ORDERS
