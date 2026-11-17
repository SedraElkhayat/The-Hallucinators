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

Offline, without Docker or a model: `pip install -r requirements.txt && make demo-mock` (writes to `runs/demo_mock`, every output labeled `MOCKED`). Tests: `python -m pip install -r requirements.txt` once, then `python -m pytest -q` (same as `make test`).

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
| Sale to cash: payments, webhooks, delivery, refunds, reconciliation | MOCKED (runs in code: no money moves, no payment provider is called) |
| Demand-test results and interview notes in the demo run | MOCKED / SAMPLE inputs (labeled) |
| Publishing pages, sending posts or emails | Not implemented by design (the founder does it) |
| Real payment provider | STUBBED (roadmap) |

## Architecture

Control is plain code: `orchestrator.py` runs each phase's stages, `gates.py` evaluates criteria registered before the phase, and `approval.py` is the only door to anything outward-facing. AI agents (`agents/<role>.py`, prompts in `prompts/<role>.md`) only produce typed artifacts in `outputs/`, and every action is appended to `decision_log.json`. Market claims carry a source URL and an exact quote that code re-checks (quote on the page, about this idea, and stating the claim), or are labeled `ASSUMPTION`. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- Default model: `qwen3:8b` (open weights) served locally by Ollama, pulled and started by `docker compose up`.
- Optional: any free OpenAI-compatible endpoint via `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in `.env` (for example GPT-OSS on a free tier). The key stays in the untracked `.env`.
- Web evidence comes from free public search and pages, cached on disk.
- No paid API, key or account is needed.

## Cost per run

About $0.00 per run (local `qwen3:8b`, no paid API). The committed strong-brief run used 92 model calls and about 256k tokens (222k in, 33k out) and took about 5.5 minutes on one RTX 5080 GPU; the weak-brief run stopped at Gate 1 after 24 calls and about 53k tokens. Figures from `outputs/phase6_gate_final_report.md` and `outputs/phase1_gate_weak_final_report.md`; per-call tokens are in `decision_log.json`.

## Demo video

[Demo video, 1 min 29 s (Google Drive)](https://drive.google.com/file/d/1ZRJ6DPlPK0YaDh7kkNTIuMUyTnZc_Eiu/view?usp=sharing): a weak idea run live on `qwen3:8b` that ends in **STOP** at Gate 1, then the committed demo run's store website, sourced and `ASSUMPTION` claims, the founder's logged gate override, the `MOCKED` sale to cash, and the red-team results. Founder answers in the live run are `SCRIPTED` demo inputs.

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
