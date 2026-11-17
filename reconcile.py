# OWNER: M4
# STUB: replace the contents, keep the public names
"""MOCKED reconciliation of orders, payments, fees (documented mock rate) and payouts."""
MOCKED = True


def reconcile(orders: list, payments: list, fee_rate: float) -> dict:
    """Return {"balanced": bool, "discrepancies": [str], "totals": {...}}."""
    raise NotImplementedError
