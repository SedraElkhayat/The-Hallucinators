# Scripted founder inputs

`--founder-inputs <file>` runs the pipeline without a person at the keyboard. Every answer taken from the file is logged with `provenance: "SCRIPTED"` in `decision_log.json`. Interview notes, demand results, support questions and phase 6 results in these files are **SAMPLE / MOCKED inputs**, never real data.

| File | Use |
|---|---|
| `founder_inputs.json` | Strong brief (`brief_strong.md`). Demand results 140 sign-ups in 14 days (MOCKED). |
| `founder_inputs_weak.json` | Weak brief (`brief_weak.md`). Demand results 12 sign-ups in 14 days (MOCKED), so Gate 2 stops. |

## Keys (fixed, CONTEXT section 4a item 5)

| Key | Asked by | Value |
|---|---|---|
| `clarify_<field>` for `target_customer`, `problem`, `product_type`, `budget`, `time_per_week`, `founder_skills`, `monetization_idea`, `distribution_channel`, `differentiation`, `values_and_limits` | clarifier | text, or `unknown` |
| `option_<field>` | option_suggester | `approve` or `reject` |
| `idea_choice` | idea_generator / clarifier | text |
| `interview_notes` | interview_analyst | text, labeled SAMPLE |
| `demand_results` | demand_results | JSON text `{"signups": int, "days": int, "provenance": "REAL" or "MOCKED"}` |
| `support_questions` | support_drafter | text, labeled SAMPLE |
| `phase6_results` | metrics_analyst | CSV text |
| `gate_override_<N>` | orchestrator, only when a gate verdict is rejected | `go`, `repeat`, `pivot` or `stop` |

`prefix_defaults` answers any missing key by its longest matching prefix (for example `clarify_`). A key with no answer and no matching prefix stops the run with a clear error. `approvals.default` (and optionally `approvals.<kind>`) is `approve` or `reject` for every approval request. `approvals.<kind>_<N>` (for example `gate_1`) answers only the request of that kind in phase N and wins over `approvals.<kind>`.

`founder_inputs.json` rejects only the Gate 1 verdict (`approvals.gate_1: reject`) and overrides it with `gate_override_1: go`: a founder decision, not a gate rule change. The system's Gate 1 verdict stays in `phase1_gate_decision.md`; the override is in `phase1_gate_founder_override.md` and in `decision_log.json` (`gate_override_1`, `approved_by: founder`). Later gates are approved as recommended.
