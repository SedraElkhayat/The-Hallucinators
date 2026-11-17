# Pitch: an honest, open venture builder

## The problem

A first-time founder with a small budget and a few hours a week has to decide whether an idea is worth building before
spending that time and money. The hard part is not producing a business plan; it is getting an honest answer: is there
evidence that people want this, can this founder build it, and should they stop? A tool that always says "go", writes
glowing copy and invents numbers makes that decision worse, not better.

## The user

A solo founder of a small **digital** product (templates, guides, small courses, newsletters), for example the demo
founder: a freelance graphic designer in Egypt with USD 100, 8 hours a week and no coding skills
(`demo/brief_strong.md`). They bring a short brief: a starting idea plus their skills, budget, time, target market and
values. They stay in charge of every decision that matters.

## What the system does

Six phases, each with agents that do one job and a gate whose criteria are fixed in code before the phase runs:

| Phase | Agents produce | Gate checks (examples) |
|---|---|---|
| 1 Discover | sharpened idea card, sourced market and competitor claims, founder fit, Mom Test interview script and findings, opportunity scores, skeptic's kill criteria | at least 3 verified claims, at least 2 competitors, no triggered kill criterion |
| 2 Validate | Lean Canvas, demand test plan with a target fixed in advance, landing page, scorecard | sign-ups divided by target (below 0.2 means stop), no weak dimension |
| 3 Build | spec with acceptance tests, the product website, user docs, QA report | acceptance tests pass, website checks pass, nothing deployed |
| 4 Commercial setup | price only when a verified source supports it, draft policies marked for legal review | no banned claims, prices sourced or labeled `ASSUMPTION` |
| 5 Launch | store page, launch posts held for approval, mocked sale to cash | nothing released without approval, no double delivery, reconciliation balanced |
| 6 Operate and learn | support replies, metrics, persevere-or-pivot memo | inputs labeled, memo backed by metrics |

## How it decides on evidence

- **Claims are checked by code, three times.** A market claim counts only if its exact quote is on the fetched page,
  the quote is about this idea, and the model confirms the quote states the claim. Everything else is labeled
  `ASSUMPTION`, and every downgrade is logged.
- **Criteria are fixed before the evidence arrives.** Each gate's criteria are written and hashed before its phase
  runs (`phase<N>_gate_criteria.json`), so a weak result cannot be argued away afterwards.
- **It says stop.** In the committed run the weak brief stops at Gate 1 (0 verified claims, 2 kill criteria), and the
  system then lists other directions from the same evidence (in the web app the founder can pick one and start again;
  the scripted demo simply stops). Even the strong brief, GO at Gate 1 with 7 verified claims,
  gets a STOP recommendation at Gate 2 because the demand evidence is thin, and the final memo recommends stopping because the
  demand and sales inputs are `MOCKED`.

## How the founder stays in control

- **Nothing outward-facing without approval.** `approval.py` is the only door to publishing, sending or releasing; a
  rejected item is never released, and every approval is logged with `approved_by: founder`.
- **The founder can disagree with a gate,** and the override is logged next to the system's own verdict
  (`phase<N>_gate_founder_override.md`); the verdict file itself is never edited.
- **Rules the founder cannot switch off:** no income promises, no fake reviews, sign-ups or urgency, no impersonation,
  no money movement, no stored credentials. Guardrails check inputs and outputs in code; 83 trick prompts and 3 live
  trick briefs test them (`evals/`).

## Why open beats closed

- **The founder can check every step.** Every agent action is in `decision_log.json` with its sources, model and
  cost; every prompt is a readable file in `prompts/`; every gate rule is code in `gates.py` and `phases/`.
- **No lock-in and no running cost.** It runs on a free open-weight model (`qwen3:8b`) and free self-hosted search
  (SearXNG) with one command (`docker compose up`); a run costs $0.00. The founder's data stays on their machine.
- **Rules are inspectable and testable.** Anyone can read the guardrails, run the red-team evals and the smoke tests,
  and propose a change (`CONTRIBUTING.md`). A closed tool asks the founder to trust it; this one shows its work.

## What it will not do

Promise income or success; write fake reviews, testimonials, sign-ups, counters or countdowns; pose as the founder, a
customer or another brand; publish, send, spend or sign without the founder's approval; hold, move or refund money;
store passwords or card numbers; hide core features behind a paywall; work on physical goods, financial, investment
or crypto products, or health or legal advice.

## Roadmap and how it stays alive

See the README section "How the project stays alive after the hackathon" and the roadmap in
[ARCHITECTURE.md](../ARCHITECTURE.md#roadmap): Arabic-first prompts and evaluations, more free evidence sources, and
founder-run demand tests that replace today's `MOCKED` demand input. Payments stay out of scope.
