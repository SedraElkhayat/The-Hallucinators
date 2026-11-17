# OWNER: M4
# STUB: replace the contents, keep the public names
"""MOCKED mock buyer and payment events. No payment provider is ever called; no money moves."""
MOCKED = True


def create_mock_order(product_id: str, price_usd: float) -> dict:
    """Return a MOCKED order {"order_id", "product_id", "amount", "status"}."""
    raise NotImplementedError


def mock_payment_event(order: dict, event_type: str, idempotency_key: str) -> dict:
    """Return a MOCKED signed event (order.created, payment.succeeded, refund.requested)."""
    raise NotImplementedError
