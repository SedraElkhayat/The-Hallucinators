# demand_results

## Role
Founder-input step (no model call): records the demand-test result the founder supplies and labels where it came from.

## Task
The code asks the founder for key `demand_results` and expects JSON text `{"signups": int, "days": int, "provenance": "REAL" | "MOCKED"}`. It checks the values, asks once more if they are invalid, and otherwise records `signups` 0 with provenance `MOCKED` and says so. It computes `ratio = signups / target` using the target from `phase2_step3_demand_test_plan`, which was fixed before the result existed.

## Inputs
- Founder input `demand_results`.
- `phase2_step3_demand_test_plan`: `target`, `window_days`.

## Output
Artifact `phase2_step5_demand_results`:
- `signups`: integer, at least 0.
- `days`: integer, at least 0.
- `provenance`: `"REAL"` or `"MOCKED"`.
- `ratio`: number, signups divided by target.
- `target`, `window_days`: copied from the plan.
- `note`: string explaining any problem with the input.

Example:
```json
{"signups": 140, "days": 14, "provenance": "MOCKED", "ratio": 1.4, "target": 100, "window_days": 14, "note": ""}
```
The markdown always starts with the line `PROVENANCE: MOCKED` or `PROVENANCE: REAL`.

## Rules
- Never invent or adjust sign-up numbers. Only the founder's input is recorded.
- Invalid input after one retry becomes 0 sign-ups labeled `MOCKED`, and the note says why.
