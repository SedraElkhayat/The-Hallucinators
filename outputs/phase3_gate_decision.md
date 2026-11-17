# Gate 3 decision: **GO**

System recommendation: GO: move on to the next phase.
The founder approves or overrides this recommendation; an override is logged.

Attempt: 0 (max repeats 1)
Criteria hash (sha256, pre-registered before the phase ran): `5e47067a81b1d4df04d7d6d597eb94e7216d29125e7cc77c2ccb9c19280c4801`

## Checks

| Check | Metric | Rule | Value | Result | On fail |
|---|---|---|---|---|---|
| `acceptance_pass_ratio` | `acceptance_pass_ratio` | >= 0.8 | 1 | PASS | repeat |
| `no_honesty_must_fix` | `honesty_must_fix` | == 0 | 0 | PASS | repeat |
| `site_checks` | `site_checks_passed` | == 1 | 1 | PASS | repeat |
| `nothing_deployed` | `deployed` | == 0 | 0 | PASS | stop |

## Reasons

- all pre-registered checks passed

## What would change this verdict

- A failed check in a later run, or new evidence that triggers a kill criterion.

## Metrics (computed in code from the artifacts)

```json
{
  "acceptance_pass_ratio": 1.0,
  "site_checks_passed": 1,
  "honesty_must_fix": 0,
  "deployed": 0
}
```
