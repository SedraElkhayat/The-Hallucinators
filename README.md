# The Hallucinators: open-source agentic venture builder

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product across six phases (Discover, Validate, Build, Commercial setup, Launch, Operate and learn). Every phase ends with a gate whose criteria are fixed in code before the phase runs, and the system can recommend **STOP**. The founder approves every outward-facing step; payments are **MOCKED**.

## Quickstart

```bash
docker compose up
```

Then open http://localhost:8000, pick a demo brief (or paste your own), and press **Start run**. The first start downloads the open-weight model (`qwen3:8b`, about 5 GB). Answer questions and approve or reject items in the founder inbox. When Phase 3 has built the founder's website, the run page shows **Preview website** and **Download site folder**; the system never publishes it.

Offline, without Docker or a model: `pip install -r requirements.txt && make demo-mock` (writes to `runs/demo_mock`, every output labeled `MOCKED`). Tests: `python -m pip install -r requirements.txt` once, then `python -m pytest -q` (same as `make test`).

## What works and what is mocked

| Step | Status |
|---|---|
| Orchestrator, gates (pre-registered), founder approval, decision log | Working |
| Founder UI (web) and CLI | Working |
| Founder website (Phase 3 build, Phase 5 store version, website checks in Gate 3) | In progress |
| Preview website and Download site folder buttons (local only; the system never publishes) | Working |
| Search and fetch (free public sources, cached) | Working |
| Phase 1 to 6 agents | In progress (STUBBED phases are labeled in the run) |
| Sale to cash: payments, webhooks, delivery, refunds, reconciliation | MOCKED by design; currently STUBBED (functions not yet implemented) |
| Demand-test results and interview notes in the demo run | MOCKED / SAMPLE inputs (labeled) |
| Publishing pages, sending posts or emails | Not implemented by design (the founder does it) |
| Real payment provider | STUBBED (roadmap) |

## Architecture

Control is plain code: `orchestrator.py` runs each phase's stages, `gates.py` evaluates criteria registered before the phase, and `approval.py` is the only door to anything outward-facing. AI agents (`agents/<role>.py`, prompts in `prompts/<role>.md`) only produce typed artifacts in `outputs/`, and every action is appended to `decision_log.json`. Market claims carry a source URL and an exact quote that code re-checks, or are labeled `ASSUMPTION`. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- Default model: `qwen3:8b` (open weights) served locally by Ollama, pulled and started by `docker compose up`.
- Optional: `gpt-oss:20b` (set `LLM_MODEL=gpt-oss:20b` in `.env`), or any free OpenAI-compatible endpoint via `LLM_BASE_URL`.
- Web evidence comes from free public search and pages, cached on disk.
- No paid API, key or account is needed.

## Cost per run

About $0.00 per run (local model); token count measured in the final run and recorded in `decision_log.json`.

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

- Maintainers: the four team members, under the MIT licence.
- Roadmap: see [ARCHITECTURE.md](ARCHITECTURE.md#roadmap).
- Community: issues and pull requests welcome; new agents are one file plus one prompt.
- Funding: none needed to run; it uses free local models.
