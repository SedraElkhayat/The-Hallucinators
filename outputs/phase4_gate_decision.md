# Gate 4 decision: **GO**

System recommendation: GO: move on to the next phase.
The founder approves or overrides this recommendation; an override is logged.

Attempt: 0 (max repeats 1)
Criteria hash (sha256, pre-registered before the phase ran): `1fc3e4f1eda189e319e7d186dbe58e3c5f4c7a35ebc951860d79523edc5b2507`

## Checks

| Check | Metric | Rule | Value | Result | On fail |
|---|---|---|---|---|---|
| `chk_p4_price` | `price_sourced_or_labeled` | >= 1 | 1 | PASS | repeat |
| `chk_p4_policies` | `policies_labeled` | >= 1 | 1 | PASS | repeat |
| `chk_p4_claims` | `banned_claims` | <= 0 | 0 | PASS | repeat |
| `chk_p4_no_payment_sdk` | `payment_code_present` | <= 0 | 0 | PASS | stop |
| `chk_p4_compliance` | `compliance_must_fix` | <= 0 | 0 | PASS | repeat |

## Reasons

- all pre-registered checks passed

## What would change this verdict

- A failed check in a later run, or new evidence that triggers a kill criterion.

## Metrics (computed in code from the artifacts)

```json
{
  "compliance_must_fix": 0,
  "price_sourced_or_labeled": 1,
  "policies_labeled": 1,
  "banned_claims": 0,
  "payment_code_present": 0
}
```
