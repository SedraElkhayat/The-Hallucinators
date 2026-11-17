# The Hallucinators: open-source agentic venture builder

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product across six phases (Discover, Validate, Build, Commercial setup, Launch, Operate and learn). Every phase ends with a gate whose criteria are fixed in code before the phase runs, and the system can recommend **STOP**. The founder approves every outward-facing step; payments are **MOCKED**.

**Committed demo run** (`outputs/`, `decision_log.json`; real `qwen3:8b` on Ollama, live web search through SearXNG):
- Strong brief (`demo/brief_strong.md`): all six phases ran. The system's own verdict was **STOP** at Gates 1 and 2; the founder overrode both (scripted demo inputs, labeled `SCRIPTED` and logged with `approved_by: founder` and `system_outcome: stop`), and Gates 3 to 6 were **GO**. The Phase 6 memo still recommends stopping because the demand and sales numbers are `MOCKED`. Summary: `outputs/phase6_gate_final_report.md`.
- Weak brief (`demo/brief_weak.md`): **STOP** at Gate 1 with no override (0 verified claims, 2 kill criteria triggered). See `outputs/phase1_gate_weak_decision.md`.

## Quickstart

```bash
docker compose up
```

Then open http://localhost:8000, pick a demo brief (or paste your own), and press **Start run**. The first start downloads the open-weight model (`qwen3:8b`, about 5 GB). Answer questions and approve or reject items in the founder inbox. When Phase 3 has built the founder's website, the run page shows **Preview website** and **Download site folder**; the system never publishes it.

Offline, without Docker or a model: `pip install -r requirements.txt && make demo-mock` (writes to `runs/demo_mock`, every output labeled `MOCKED`). Without `make` (for example on Windows): `python orchestrator.py --brief demo/brief_strong.md --through 6 --mock-llm --out runs/demo_mock/outputs --founder-inputs demo/founder_inputs.json`. Tests: `python -m pip install -r requirements.txt` once, then `python -m pytest -q` (same as `make test`).

## What works and what is mocked

| Step | Status |
|---|---|
| Orchestrator, gates (criteria pre-registered for all six phases), founder approval, decision log | Working |
| Founder UI (web) and CLI | Working |
| Phase 1 to 6 agents (one file and one prompt each) | Working: the committed demo run in `outputs/` ran all six phases with the real local model (`qwen3:8b`), 0 agent errors. Offline tests use MockLLM (outputs labeled MOCKED) |
| Pricing (Phase 4) | Working, but the demo run set no price: no verified source stated a comparable price, so `price_usd` is empty and labeled STUBBED until the founder sets it |
| Search and fetch (free public sources, cached) and claim re-checking | Working (code): local SearXNG container, then Hacker News API and DuckDuckGo as fallbacks (Bing optional, off by default); a blocked search is an error, never a silent 0 results. Live check: `python -m scripts.check_search` |
| Guardrails and red-team evals (`python evals/run_redteam.py`) | Working |
| Founder website (Phase 3 build from a template, Phase 5 store version with price and policies, website checks in Gates 3 and 5) | Working (never published by the system; the founder publishes it) |
| Preview website and Download site folder buttons (local only; the system never publishes) | Working |
| Demo founder: in the strong demo run the system recommends STOP at Gates 1 and 2 (thin evidence) and the scripted founder overrides both; the weak demo brief stops at Gate 1 with no override | Working (labeled SCRIPTED; the system's own verdict stays in the decision log) |
| Sale to cash: payments, webhooks, delivery, refunds, reconciliation | MOCKED (runs in code: no money moves, no payment provider is called) |
| Demand-test results and interview notes in the demo run | MOCKED / SAMPLE inputs (labeled) |
| Publishing pages, sending posts or emails | Not implemented by design (the founder does it) |
| Real payment provider | STUBBED (roadmap) |

### Known limits

- Free public search returns limited evidence. A claim whose quote does not support it is never shown as a fact, so the websites show many labeled `ASSUMPTION`s. Phase 4 found no verified price comparable, so it proposes no price (an `ASSUMPTION`) and the store page says purchasing opens when the founder is ready to sell.
- The small local model reviews its own phase reports inconsistently; code guards stop it from blocking on rules that code already checked (recorded as `downgraded_by_code`). A founder can always override a gate; the override is logged next to the system's verdict.
- The demand-test result is a `MOCKED` input and the interview notes are `SAMPLE`; the demo's final memo recommends STOP because of that. The sale-to-cash test uses sample amounts, not the Phase 4 price.

### Reading the demo run

| Where | What it shows |
|---|---|
| `outputs/phase1_gate_weak_decision.md` | The weak brief: the system recommends STOP (0 verified claims, 2 kill criteria) and says what would change that |
| `outputs/phase1_gate_decision.md`, `outputs/phase1_gate_founder_override.md` | The strong brief: the system's own STOP at Gate 1 and the logged founder override (same for Gate 2) |
| `outputs/phase3_step3_site/index.html`, `outputs/phase5_step2_store_site/index.html` | The founder's website (Phase 3) and its store version (Phase 5); open them in a browser |
| `outputs/payment_test_log.md` | The mocked sale to cash: duplicate event ignored, refund revokes access, reconciliation balanced |
| `decision_log.json` | One entry per agent action for both runs (`run`: strong or weak), with model, sources, cost and `approved_by` |

More detail: [docs/DEMO_RUN.md](docs/DEMO_RUN.md). The rule behind each guarantee, with the file and the test: [docs/HONESTY.md](docs/HONESTY.md).

## Architecture

Control is plain code: `orchestrator.py` runs each phase's stages, `gates.py` evaluates criteria registered before the phase, and `approval.py` is the only door to anything outward-facing. AI agents (`agents/<role>.py`, prompts in `prompts/<role>.md`) only produce typed artifacts in `outputs/`, and every action is appended to `decision_log.json`. Market claims carry a source URL and an exact quote that code re-checks (quote on the page, about this idea, and stating the claim), or are labeled `ASSUMPTION`. See [ARCHITECTURE.md](ARCHITECTURE.md).

### How outputs stay honest

- **Fixed before the evidence:** gate criteria are written and hashed before a phase runs; the system can recommend STOP.
- **Checked by code, not by prompt:** claims are re-checked against the source page, the website is checked by code (no scripts, no network calls, no sign-up numbers, one inert demo form), and an audit script fails the build if a claim has no source and no `ASSUMPTION` label.
- **Mocks are labeled:** `MOCKED`, `SAMPLE`, `SCRIPTED`, `STUBBED` appear in the artifacts and the log.
- **Tested:** `python -m pytest -q`, `python scripts/verify_submission.py`, `python scripts/audit_outputs.py outputs` and `python evals/run_redteam.py` (83 trick prompts).

## Models and free resources

- Default model: `qwen3:8b` (open weights) served locally by Ollama, pulled and started by `docker compose up`.
- The committed demo run in `outputs/` was made with `qwen3:8b` through Ollama; the model is recorded in every entry of `decision_log.json`. Recommended settings for qwen3 on Ollama (the defaults in `docker-compose.yml`): reasoning effort off (`LLM_REASONING_EFFORT=none`) and an 8192-token context.
- Optional: any free OpenAI-compatible endpoint via `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in `.env` (for example GPT-OSS on a free tier). The key stays in the untracked `.env`.
- Web evidence comes from free public search and pages, cached on disk.
- No paid API, key or account is needed.

## Cost per run

About $0.00 per run (local `qwen3:8b`, no paid API). The committed strong-brief run used 92 model calls and about 270k tokens (233k in, 37k out, the totals logged at the end of the run in `decision_log.json`) and took about 5.5 minutes on one RTX 5080 GPU; the weak-brief run stopped at Gate 1 after 24 calls and about 53k tokens. Figures from `outputs/phase6_gate_final_report.md` and `outputs/phase1_gate_weak_final_report.md`; per-call tokens are in `decision_log.json`.

## Demo video

Link added after recording.

## What our system will NOT do

- Promise income or success.
- Write fake reviews, testimonials, sign-ups, counters or countdown timers.
- Pose as the founder, a customer or another brand.
- Publish, send, spend or sign anything without the founder's explicit approval.
- Hold, move or refund money, create accounts, or store passwords or card numbers. Payments are MOCKED only.
- Hide core features behind a paywall.
- Work on physical goods, financial, investment or crypto products, or health or legal advice products.

## How the project stays alive after the hackathon

- **Maintainers:** the four team members, one per area, matching the code ownership used during the hackathon: platform and integration (orchestrator, UI, Docker); discovery and evidence quality (Phase 1, gates, claim checking); validation and build (Phases 2-3, founder website); commerce and safety (Phases 4-6, payments, guardrails). MIT licence.
- **Roadmap (next three releases):** (1) a payment-provider adapter in test mode behind the existing webhook, idempotency and refund interface, used only with the founder's own keys and approval; (2) Arabic-first prompts and evaluation sets, since our first users are freelancers in Egypt and the MENA region; (3) more free evidence sources behind the same claim checks. Full list: [ARCHITECTURE.md](ARCHITECTURE.md#roadmap).
- **Community:** issues and pull requests welcome. A new agent is one file (`agents/<role>.py`) plus one prompt (`prompts/<role>.md`) and a mock fixture, so contributions stay small and reviewable; every change must keep `python -m pytest -q` and `python scripts/verify_submission.py` green.
- **Funding:** none needed to run it: open-weight local model, free self-hosted search (SearXNG), no paid API. Costs stay at $0 per run; any future hosted service would be optional and free for founders to self-host.
