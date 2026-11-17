# OWNER: M4
# STUB: replace the contents, keep the public names
"""MOCKED refunds: marks the order refunded and revokes access. Moves no money."""
MOCKED = True


def process_refund(order_id: str, reason: str) -> dict:
    """Return {"order_id", "status": "refunded", "access_revoked": bool}."""
    raise NotImplementedError
