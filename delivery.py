# OWNER: M4
"""MOCKED delivery and access token tracking.

Double deliveries are impossible. No real external delivery or network call occurs.
"""
from __future__ import annotations

import uuid

_DELIVERIES: dict[str, dict] = {}
_ACCESS_TOKENS: dict[str, str] = {}


def reset_delivery_store() -> None:
    """Helper for testing to reset state."""
    _DELIVERIES.clear()
    _ACCESS_TOKENS.clear()


def deliver(order_id: str) -> dict:
    """Creates a mock access token and delivery record.

    If the order has already been delivered, returns the existing record without creating a duplicate delivery.
    """
    oid = str(order_id)
    if oid in _DELIVERIES:
        return _DELIVERIES[oid]

    token = f"tok_mock_{uuid.uuid4().hex[:12]}"
    record = {
        "order_id": oid,
        "token": token,
        "status": "delivered",
        "mocked": True,
    }
    _DELIVERIES[oid] = record
    _ACCESS_TOKENS[oid] = token
    return record


def revoke(order_id: str) -> bool:
    """Revokes access for an order (e.g. following a refund)."""
    oid = str(order_id)
    if oid in _ACCESS_TOKENS:
        del _ACCESS_TOKENS[oid]
    if oid in _DELIVERIES:
        _DELIVERIES[oid]["status"] = "revoked"
        return True
    return False


def has_access(order_id: str) -> bool:
    """Check if the order currently holds valid access."""
    return str(order_id) in _ACCESS_TOKENS


def get_delivery_record(order_id: str) -> dict | None:
    """Retrieve delivery record for an order."""
    return _DELIVERIES.get(str(order_id))


def all_deliveries() -> dict[str, dict]:
    """Return a copy of all delivery records."""
    return dict(_DELIVERIES)
