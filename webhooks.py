# OWNER: M4
"""MOCKED webhook handler with mock HMAC signature verification and idempotency store.

Dispatches payment.succeeded to delivery and refund.requested to refunds.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import delivery
import refunds


class WebhookHandler:
    def __init__(self, secret: str | None = None):
        self.secret = secret or os.getenv("MOCK_WEBHOOK_SECRET", "mock-secret")
        self.seen_idempotency_keys: set[str] = set()
        self.processed_events: list[dict] = []
        self.ignored_duplicates: int = 0

    def verify_signature(self, event: dict) -> bool:
        """Verify mock HMAC-SHA256 signature."""
        sig = event.get("signature")
        if not sig:
            return False
        oid = event.get("order_id", "")
        amount = event.get("amount_usd", "")
        key = event.get("idempotency_key", "")
        expected = hmac.new(
            self.secret.encode("utf-8"),
            f"{oid}:{amount}:{key}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig, expected)

    def handle(self, event: dict) -> dict:
        """Handle incoming webhook event idempotently."""
        if not self.verify_signature(event):
            return {"status": "rejected", "reason": "invalid_signature", "mocked": True}

        key = event.get("idempotency_key")
        if not key:
            return {"status": "rejected", "reason": "missing_idempotency_key", "mocked": True}

        if key in self.seen_idempotency_keys:
            self.ignored_duplicates += 1
            return {
                "status": "ignored",
                "reason": "duplicate_idempotency_key",
                "idempotency_key": key,
                "mocked": True,
            }

        self.seen_idempotency_keys.add(key)
        self.processed_events.append(event)
        etype = event.get("type")
        oid = event.get("order_id")

        if etype == "payment.succeeded":
            delivery_record = delivery.deliver(oid)
            return {
                "status": "processed",
                "action": "delivered",
                "delivery": delivery_record,
                "mocked": True,
            }
        elif etype == "refund.requested":
            refund_record = refunds.process_refund(oid)
            return {
                "status": "processed",
                "action": "refunded",
                "refund": refund_record,
                "mocked": True,
            }

        return {"status": "unhandled_event_type", "type": etype, "mocked": True}
