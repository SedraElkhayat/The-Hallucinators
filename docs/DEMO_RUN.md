# The committed demo run

`outputs/` and `decision_log.json` are the result of running the real pipeline on two demo briefs. Nothing in them was written
by hand. Model: `qwen3:8b` through Ollama (reasoning effort off, 8192-token context); web evidence: a local SearXNG container.
Cost: $0.00. This page says what was run, what happened at each gate, what is mocked, and where to look.

## What was run

| Run | Brief | Phases | Result |
|---|---|---|---|
| strong | `demo/brief_strong.md` (bilingual Notion and Google Sheets template pack for freelance designers in Egypt and the MENA region) | 1 to 6 | all six phases; 198 log entries; about 5 minutes; 71 model calls; 181,236 input and 26,620 output tokens; 20 founder approvals; 69 distinct source URLs |
| weak | `demo/brief_weak.md` (paid newsletter) | 1 | **the system recommends STOP at Gate 1** and the run ends; 86 log entries; about 1.2 minutes; 23 model calls; 52,602 input and 6,844 output tokens; no override; after the STOP the system lists three other directions from the same evidence and the founder chooses to stop (`outputs/phase1_gate_weak_alternatives.md`) |

Both runs have 0 agent errors. In `decision_log.json` every entry has `run` set to `strong` or `weak`.

## The gates in the strong run

| Gate | System's own verdict | What happened | Where to read it |
|---|---|---|---|
| 1 Discover | **STOP** (a triggered kill criterion; 3 open must-fix issues; 4 verified claims, 4 competitors) | the scripted founder rejected the STOP and chose GO (`SCRIPTED`) | `outputs/phase1_gate_decision.md`, `outputs/phase1_gate_founder_override.md` |
| 2 Validate | repeat, then **STOP** (3 open must-fix issues after the repeat) | the scripted founder overrode it to GO (`SCRIPTED`) | `outputs/phase2_gate_decision.md`, `outputs/phase2_gate_founder_override.md` |
| 3 Build | GO (acceptance 1.0, website checks pass, no honesty must-fix, nothing deployed) | none needed | `outputs/phase3_gate_decision.md`, `outputs/phase3_step5_qa_report.md` |
| 4 Commercial setup | repeat, then GO (no compliance must-fix after the repeat; price not set, labeled `ASSUMPTION`; policies marked for legal review) | none needed | `outputs/phase4_gate_decision.md` |
| 5 Launch | GO (no double delivery, refund revokes access, reconciliation balanced) | none needed | `outputs/phase5_gate_decision.md` |
| 6 Operate | GO | none needed | `outputs/phase6_gate_decision.md` |

Every gate file keeps the system's verdict, each check with its result, and the evidence that would change the verdict. A
founder override never edits the decision file; it is written to its own file and to the log (`gate_override_<N>` with
`system_outcome` and `provenance`).

## What is mocked or sample in the run (all labeled)

| Item | Label |
|---|---|
| Demand-test result (140 sign-ups against a target of 100) | `MOCKED` |
| Interview notes, support questions, Phase 6 results | `SAMPLE` |
| Founder answers and approvals | `SCRIPTED` (logged as such) |
| Sale to cash (orders, payment events, refund, reconciliation) | `MOCKED`; sample amounts, not the Phase 4 price |
| Real or sandbox payments | not included (the rules exclude payments of any kind) |
| Real publishing | `STUBBED`: the system drafts, the founder publishes |

Consequences visible in the outputs: the scorecard caps demand evidence at `adequate` because the demand result is `MOCKED`;
Phase 4 found no verified price comparable, so it proposes no price (an `ASSUMPTION`) and the store page says purchasing opens
when the founder is ready to sell; the Phase 6 memo recommends STOP because its demand and sales inputs are `MOCKED`.

## Where to look, by topic

| Topic | File |
|---|---|
| Sourced claims (URL and exact quote) and `ASSUMPTION` labels | `outputs/phase1_step5_market.json`, `outputs/phase1_step5_competitors.json`, `outputs/phase2_step1_competitor_analysis.json` |
| The founder's website and its store version | `outputs/phase3_step3_site/index.html`, `outputs/phase5_step2_store_site/index.html` |
| How the founder would publish it (the system never does) | `outputs/phase3_step7_publish_guide.md` |
| Policy drafts, each marked "needs legal review" | `outputs/phase4_step3_policies.json`, `outputs/phase5_step2_store_site/policies/` |
| Launch posts held for the founder's approval | `outputs/phase5_step3_launch_posts.json` |
| Mocked payments and delivery | `outputs/payment_test_log.md`, `outputs/phase5_step5_sale_to_cash.json` |
| What the system recommends at the end, and why | `outputs/phase6_step3_persevere_pivot_memo.md` |
| The weak brief's STOP | `outputs/phase1_gate_weak_decision.md`, `outputs/phase1_gate_weak_final_report.md` |

## Reproduce

```bash
python -m pytest -q                          # offline tests
python scripts/verify_submission.py          # submission checklist
python scripts/audit_outputs.py outputs      # claims sourced or labeled, mocks labeled
python orchestrator.py --brief demo/brief_strong.md --through 6 --mock-llm --out runs/demo_mock/outputs --founder-inputs demo/founder_inputs.json
```

A real run needs a model: `docker compose up` starts Ollama and pulls `qwen3:8b`. The committed run was made with
`python orchestrator.py --brief demo/brief_strong.md --through 6 --out runs/final/outputs --founder-inputs demo/founder_inputs.json`
and `scripts/finalize_outputs.py`.
