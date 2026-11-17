# OWNER: M4
"""MOCKED mock buyer and payment events.

No payment provider is ever called; no money moves; no payment SDK is imported.
All fee rates and events are explicitly simulated mock data.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid

MOCKED = True

# Mock fee constants documented as mock values
MOCK_FEE_RATE: float = 0.029   # 2.9% simulated processing fee
MOCK_FEE_FIXED: float = 0.30   # $0.30 simulated fixed transaction fee


def create_mock_order(order_id: str, amount_usd: float, product: str = "Digital Template Pack") -> dict:
    """Return a MOCKED order dictionary."""
    return {
        "order_id": str(order_id),
        "amount_usd": float(amount_usd),
        "product": str(product),
        "status": "created",
        "mocked": True,
    }


def compute_mock_signature(payload_str: str, secret: str | None = None) -> str:
    """Compute HMAC-SHA256 mock signature for webhook payload verification."""
    sec = secret or os.getenv("MOCK_WEBHOOK_SECRET", "mock-secret")
    return hmac.new(sec.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest()


def simulate_payment_events(order: dict) -> list[dict]:
    """Produce simulated payment events for an order, including one duplicate payment event to test idempotency."""
    oid = order["order_id"]
    amount = order["amount_usd"]
    shared_key = f"idemp_pay_{oid}"

    # First payment.succeeded event
    sig1 = compute_mock_signature(f"{oid}:{amount}:{shared_key}")
    event1 = {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "idempotency_key": shared_key,
        "type": "payment.succeeded",
        "order_id": oid,
        "amount_usd": amount,
        "signature": sig1,
        "mocked": True,
    }

    # Duplicate payment.succeeded event with identical idempotency key to test idempotency
    event1_dup = {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "idempotency_key": shared_key,
        "type": "payment.succeeded",
        "order_id": oid,
        "amount_usd": amount,
        "signature": sig1,
        "mocked": True,
    }

    # Refund requested event
    ref_key = f"idemp_ref_{oid}"
    sig2 = compute_mock_signature(f"{oid}:{amount}:{ref_key}")
    event2 = {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "idempotency_key": ref_key,
        "type": "refund.requested",
        "order_id": oid,
        "amount_usd": amount,
        "signature": sig2,
        "mocked": True,
    }

    return [event1, event1_dup, event2]


def mock_payment_event(order: dict, event_type: str, idempotency_key: str) -> dict:
    """Return a single MOCKED signed event."""
    oid = order.get("order_id", "order_mock")
    amount = float(order.get("amount_usd", order.get("amount", 29.0)))
    sig = compute_mock_signature(f"{oid}:{amount}:{idempotency_key}")
    return {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "idempotency_key": idempotency_key,
        "type": event_type,
        "order_id": oid,
        "amount_usd": amount,
        "signature": sig,
        "mocked": True,
    }
