# Gate 5 decision: **GO**

System recommendation: GO: move on to the next phase.
The founder approves or overrides this recommendation; an override is logged.

Attempt: 0 (max repeats 1)
Criteria hash (sha256, pre-registered before the phase ran): `6ce24bfcf5b8fed227fa4136935662384523aa7a2849722330152c21c15df59c`

## Checks

| Check | Metric | Rule | Value | Result | On fail |
|---|---|---|---|---|---|
| `chk_p5_unapproved` | `unapproved_released` | <= 0 | 0 | PASS | stop |
| `chk_p5_s2c_passed` | `sale_to_cash_passed` | >= 1 | 1 | PASS | repeat |
| `chk_p5_double_deliv` | `double_deliveries` | <= 0 | 0 | PASS | stop |
| `chk_p5_reconcile` | `reconcile_balanced` | >= 1 | 1 | PASS | repeat |
| `chk_p5_compliance` | `compliance_must_fix` | <= 0 | 0 | PASS | repeat |

## Reasons

- all pre-registered checks passed

## What would change this verdict

- A failed check in a later run, or new evidence that triggers a kill criterion.

## Metrics (computed in code from the artifacts)

```json
{
  "compliance_must_fix": 0,
  "unapproved_released": 0,
  "sale_to_cash_passed": 1,
  "double_deliveries": 0,
  "reconcile_balanced": 1
}
```
