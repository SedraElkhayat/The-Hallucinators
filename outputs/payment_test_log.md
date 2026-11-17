# Payment and Delivery Test Log (MOCKED)

> **MOCKED: no real or sandbox payment was made.**
> All orders, webhook events, access tokens, and ledger entries are simulated offline.

## Scenario Steps

1. Created 3 mock orders at MOCKED test amounts (no Phase 4 price is set; these are not prices): `mock_ord_001` ($29.00), `mock_ord_002` ($49.00), `mock_ord_003` ($29.00).
2. Order 1 payment event received: status=processed, action=delivered, token=tok_mock_9f1cfe4681a9
3. Duplicate Order 1 payment event received: status=ignored, reason=duplicate_idempotency_key
4. Order 2 payment event received: status=processed, action=delivered, token=tok_mock_72cc791b7225
5. Order 3 payment event received: status=processed, action=delivered, token=tok_mock_95d1849c1171
6. Order 3 refund requested: status=processed, access_revoked=True
7. Delivery validation: total deliveries created=3, ignored duplicate events=1, double deliveries=0

## Reconciliation Summary
- Balanced: **True**
- Total Orders: $107.00
- Total Payments: $107.00
- Total Simulated Fees: $4.00
- Total Refunds: $29.00
- Net Payout: $74.00
