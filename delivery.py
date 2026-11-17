# OWNER: M4
# STUB: replace the contents, keep the public names
"""MOCKED delivery: a payment.succeeded event grants an access token; a refund revokes it."""
MOCKED = True


def deliver(order_id: str) -> dict:
    """Grant access for a paid order. Returns {"order_id", "token", "delivered_at"}."""
    raise NotImplementedError


def revoke(order_id: str) -> bool:
    """Invalidate the access token of an order."""
    raise NotImplementedError
