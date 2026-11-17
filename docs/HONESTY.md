# How the outputs stay honest

This page explains how the system keeps its outputs honest, and where to check each rule. Every rule below is enforced in
**code**, not by a prompt, and every rule has a test. Prompts ask the model to be careful; code decides what is shown.

## What the labels mean

| Label | Meaning |
|---|---|
| `MOCKED` | Produced by a mock component or a mock model, or an input we made up for the demo (for example the demand-test result). Never presented as real. |
| `SAMPLE` | A demo input that stands for real data (interview notes, support questions, Phase 6 results). |
| `SCRIPTED` | A founder answer or approval that comes from the demo inputs file, not from a person. Always logged as such. |
| `ASSUMPTION` | A statement nobody has checked against a source. Shown with this label; never as a fact. |
| `SIMULATED, not real users` | Only for simulated people or numbers. The website never shows sign-up, waitlist or user numbers at all, even labeled. |
| `STUBBED` | Not built on purpose (real publishing: the founder publishes). Payments of any kind are not included at all. |

## Rule, where code enforces it, where it is tested

| Rule | Enforced in | Tested in |
|---|---|---|
| Gate criteria are fixed (and hashed) before a phase runs; the system can recommend STOP | `gates.py` (`preregister`, `evaluate`) | `tests/test_m2_gates.py`, `tests/test_e2e_mock.py` |
| Nothing outward-facing happens without the founder's approval | `approval.py`, `orchestrator.py` (`founder_gate`) | `tests/test_core_approval.py`, `tests/test_core_orchestrator.py` |
| Every agent action is logged with timestamp, agent, action, sources, model, cost and `approved_by` | `core/decision_log.py` | `tests/test_core_decision_log.py`, `tests/test_e2e_mock.py` |
| A founder override of a gate keeps the system's own verdict next to it (`system_outcome`) and says who answered (`provenance`: SCRIPTED, CLI or WEB) | `orchestrator.py` | `tests/test_core_orchestrator.py` |
| A market claim carries a source URL and an exact quote that code re-checks on the fetched page; otherwise it is `ASSUMPTION` | `core/claims.py` | `tests/test_m2_claims.py` |
| The website shows a claim as a sourced fact only if its quote also supports the claim (key-word overlap); otherwise it is shown as `ASSUMPTION` | `agents/m3_common.py` (`claim_supported_by_quote`), `agents/m3_site.py` (`sanitize_content`) | `tests/test_m3_real_run_fixes.py` |
| Outputs fail an audit if a claim has no source and no `ASSUMPTION` label, or if a mocked artifact is not labeled | `scripts/audit_outputs.py` | `tests/test_m2_audit.py` |
| A demand result that is not `REAL` can never make demand evidence "strong" (capped at "adequate") | `agents/scorecard_builder.py` | `tests/test_m3_phase2.py` |
| A kill criterion counts only with named evidence; "no evidence of X" is "unknown", never a reason to stop; the demand rule is decided in code | `agents/risk_analyst.py` | `tests/test_m3_risks.py`, `tests/test_m3_real_run_fixes.py` |
| The founder's website has no script, no network call, no payment code, no sign-up, waitlist or user number, and exactly one inert, labeled demo form | `agents/m3_site.py` (`check_site`), `agents/m3_common.py` | `tests/test_m3_site.py`, `tests/test_m3_honesty.py` |
| Fake reviews, income promises, impersonation, card numbers and credentials are refused or redacted (English and Arabic) | `core/guardrails.py` | `tests/test_m4_redteam.py`, `python evals/run_redteam.py` (83 cases) |
| Sale to cash is mocked: a payment event triggers delivery once (idempotency), a refund revokes access, reconciliation matches orders, payments, fees and payouts | `payments.py`, `webhooks.py`, `delivery.py`, `refunds.py`, `reconcile.py` | `tests/test_m4_sale_to_cash.py` |

## Model reviewers cannot block on rules that code already applies

The small local model that reviews the reports (`critic_phase2`, `content_reviewer`) sometimes raises a "must fix" about a
rule that code has already checked, for example "this claim has no source" when the page shows the source link, or "demand
data is mocked" when the report says so. For those cases only, code downgrades the issue to "should fix" and records the
reason in the artifact (`downgraded_by_code`). Real problems (fake testimonials, invented prices, income promises, claims
without a label) stay "must fix". The downgrade rules and their negative tests are in `agents/m3_common.py`
(`downgrade_must_fix`), `agents/critic_phase2.py`, `agents/content_reviewer.py`, `tests/test_m3_review_guards.py` and
`tests/test_m3_real_run_fixes.py`.

## Known limits (stated, not hidden)

- **Search coverage.** Free public search returns limited evidence. Expect few verified claims. A claim whose quote does not
  support it is shown as `ASSUMPTION`, so the websites show more assumptions than facts.
- **Demo inputs.** The demand-test result is `MOCKED`; interview notes and Phase 6 inputs are `SAMPLE`. The reports say so.
- **Founder overrides in the demo.** The strong demo brief is run with a scripted founder who overrides the system's STOP at
  Gates 1 and 2 (the evidence is thin and the small model's reviewer is noisy). The system's own verdict stays in the
  decision file and the log (`system_outcome`, `provenance: SCRIPTED`). The weak demo brief ends in a STOP at Gate 1 without
  any override. The strong demo's final memo also recommends STOP, because its demand and sales inputs are `MOCKED`.
- **Acceptance tests of the website are structural** (the page exists, every section exists, the demo label is shown). The
  content is checked by the website checks and the reviewer, not by those tests.
- **A small local model.** `qwen3:8b` is used on purpose (it runs for free). Its reviewers are inconsistent, which is why
  code guards exist.

## Check it yourself

```bash
python -m pytest -q                          # all tests, offline
python scripts/verify_submission.py          # the submission checklist
python scripts/audit_outputs.py outputs      # claims sourced or labeled, mocks labeled
python evals/run_redteam.py                  # trick prompts against the guardrails
```
