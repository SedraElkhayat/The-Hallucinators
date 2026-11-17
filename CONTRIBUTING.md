# Contributing

Thanks for helping. The project is small on purpose: one agent is one file, one prompt and one mock fixture, and every change is checked offline.

## Set up

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

The tests run offline with the mock model (no Ollama, no network). For a real run, start the stack with `docker compose up` (see the README).

## Add an agent

1. `agents/<role>.py`: a subclass of `agents.base.Agent` with `name`, `phase`, `step` (artifact stem `phase<N>_step<M>_<short>`), `inputs`, `tools` and `required_keys`. The registry finds it automatically.
2. `prompts/<role>.md` with the sections `## Role`, `## Task`, `## Inputs`, `## Output` (exact JSON keys and one example) and `## Rules`. `prompts/_common.md` is added to every prompt.
3. `tests/fixtures/mock/<role>.json`: a mock answer that satisfies the schema. Mock sources use `https://example.com/mock/...`.
4. Add the agent to a stage in `phases/phase<N>.py`. If it changes what a gate measures, update `gate_checks()` and `measure()` there.
5. Tests: the agent is registered, its mock run writes `<step>.json`, `<step>.md` and a decision-log entry with all seven keys, and a guardrail violation in its output is blocked.

## Rules every change keeps

- Market claims carry a source URL and an exact quote that code re-checks, or are labeled `ASSUMPTION`.
- Nothing is published, sent, spent or signed without a founder approval enforced in code (`approval.py`).
- No real payments: payment, delivery, refund and reconciliation code stays `MOCKED`.
- Never write results into `outputs/` or `decision_log.json` by hand; they come from a pipeline run.
- No secrets in git: keys go in an untracked `.env`.

## Before a pull request

```bash
python -m pytest -q
python scripts/verify_submission.py
python evals/run_redteam.py
```

All three must pass. Keep pull requests small, one agent or one fix at a time.
