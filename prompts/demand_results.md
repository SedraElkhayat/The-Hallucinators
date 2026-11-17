# demand_results

## Role
Founder-input step (no model call): records the demand-test result the founder supplies and labels where it came from.

## Task
The code asks the founder for key `demand_results` and expects JSON text `{"signups": int, "days": int, "provenance": "REAL" | "MOCKED"}`. It checks the values and asks once more if they are invalid. If the second answer is also invalid, it records no result: it sets `ctx.extra["halt_phase"]` with the reason, so the phase stops early and Gate 2 cannot pass. It computes `ratio = signups / target` using the target from `phase2_step3_demand_test_plan`, which was fixed before the result existed.

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

Example (placeholders in angle brackets; replace them, never copy them):
```json
{"signups": "<whole number from the founder>", "days": "<whole number>", "provenance": "<REAL|MOCKED>", "ratio": "<signups / target>", "target": "<from the plan>", "window_days": "<from the plan>"}
```
The markdown always starts with the line `PROVENANCE: MOCKED` or `PROVENANCE: REAL`.

## Rules
- Never invent or adjust sign-up numbers. Only the founder's input is recorded.
- Invalid input after one retry is never replaced by a made-up number; the phase halts with the reason.
