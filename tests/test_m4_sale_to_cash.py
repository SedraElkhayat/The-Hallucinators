# OWNER: M4
"""Unit tests for mocked sale to cash subsystem.

Verifies:
1. Payment triggers delivery exactly once.
2. Duplicate payment event is ignored (idempotency).
3. Refund revokes access.
4. Reconciliation is balanced.
5. Tampered HMAC signature is rejected.
6. No network calls occur (socket disabled).
"""
from __future__ import annotations

import socket

import pytest

import delivery
import payments
import reconcile
import refunds
from webhooks import WebhookHandler


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Ensure no socket network calls can be made in sale-to-cash tests."""
    def block_socket(*args, **kwargs):
        raise RuntimeError("Network calls strictly forbidden in mocked sale-to-cash modules!")
    monkeypatch.setattr(socket, "socket", block_socket)
    delivery.reset_delivery_store()
    refunds.reset_refund_store()


def test_payment_triggers_delivery():
    handler = WebhookHandler()
    order = payments.create_mock_order("ord_test_01", 29.0)
    evt = payments.mock_payment_event(order, "payment.succeeded", "idemp_test_01")

    res = handler.handle(evt)
    assert res["status"] == "processed"
    assert res["action"] == "delivered"
    assert delivery.has_access("ord_test_01") is True


def test_duplicate_event_ignored():
    handler = WebhookHandler()
    order = payments.create_mock_order("ord_test_02", 49.0)
    evt1 = payments.mock_payment_event(order, "payment.succeeded", "idemp_test_02")
    evt2 = payments.mock_payment_event(order, "payment.succeeded", "idemp_test_02")

    # First event delivers
    res1 = handler.handle(evt1)
    assert res1["status"] == "processed"

    # Duplicate event with same idempotency key is ignored
    res2 = handler.handle(evt2)
    assert res2["status"] == "ignored"
    assert res2["reason"] == "duplicate_idempotency_key"
    assert handler.ignored_duplicates == 1


def test_refund_revokes_access():
    handler = WebhookHandler()
    order = payments.create_mock_order("ord_test_03", 29.0)

    # Deliver order first
    pay_evt = payments.mock_payment_event(order, "payment.succeeded", "idemp_test_03_pay")
    handler.handle(pay_evt)
    assert delivery.has_access("ord_test_03") is True

    # Process refund request
    ref_evt = payments.mock_payment_event(order, "refund.requested", "idemp_test_03_ref")
    res_ref = handler.handle(ref_evt)
    assert res_ref["status"] == "processed"
    assert res_ref["action"] == "refunded"

    # Access is revoked
    assert delivery.has_access("ord_test_03") is False


def test_tampered_signature_rejected():
    handler = WebhookHandler()
    order = payments.create_mock_order("ord_test_04", 29.0)
    evt = payments.mock_payment_event(order, "payment.succeeded", "idemp_test_04")

    # Tamper with signature
    evt["signature"] = "tampered_fake_signature"
    res = handler.handle(evt)

    assert res["status"] == "rejected"
    assert res["reason"] == "invalid_signature"
    assert delivery.has_access("ord_test_04") is False


def test_reconciliation_balanced():
    orders = [
        {"order_id": "ord_1", "amount_usd": 100.0},
        {"order_id": "ord_2", "amount_usd": 50.0},
    ]
    payments_total = 150.0
    refunds_total = 50.0
    fees_total = 4.95
    payout_total = 150.0 - 4.95 - 50.0  # 95.05

    rec = reconcile.reconcile(
        orders=orders,
        payments=payments_total,
        refunds=refunds_total,
        fees=fees_total,
        payouts=payout_total,
    )
    assert rec["balanced"] is True
    assert len(rec["mismatches"]) == 0


def test_reconciliation_unbalanced():
    rec = reconcile.reconcile(
        orders=100.0,
        payments=100.0,
        refunds=0.0,
        fees=3.20,
        payouts=50.0,  # Expected 96.80
    )
    assert rec["balanced"] is False
    assert len(rec["mismatches"]) > 0
