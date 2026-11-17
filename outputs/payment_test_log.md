# Payment and Delivery Test Log (MOCKED)

> **MOCKED: no real or sandbox payment was made.**
> All orders, webhook events, access tokens, and ledger entries are simulated offline.

## Scenario Steps

1. Created 3 mock orders at the Phase 4 price (9.00 USD): `mock_ord_001` ($9.00), `mock_ord_002` ($9.00), `mock_ord_003` ($9.00).
2. Order 1 payment event received: status=processed, action=delivered, token=tok_mock_f283e8ad8cd0
3. Duplicate Order 1 payment event received: status=ignored, reason=duplicate_idempotency_key
4. Order 2 payment event received: status=processed, action=delivered, token=tok_mock_79d93306601c
5. Order 3 payment event received: status=processed, action=delivered, token=tok_mock_faaab709e1d6
6. Order 3 refund requested: status=processed, access_revoked=True
7. Delivery validation: total deliveries created=3, ignored duplicate events=1, double deliveries=0

## Reconciliation Summary
- Balanced: **True**
- Total Orders: $27.00
- Total Payments: $27.00
- Total Simulated Fees: $1.68
- Total Refunds: $9.00
- Net Payout: $16.32
