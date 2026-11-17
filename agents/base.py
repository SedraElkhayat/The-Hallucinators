# OWNER: M1
"""Agent base class. Subclass it in agents/<name>.py; the registry finds it automatically."""
from __future__ import annotations

import json
from pathlib import Path

from core.contracts import AgentResult, Context

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
BLOCK_MARK = "[BLOCKED by guardrails]"


class MissingInput(Exception):
    pass


def _walk_strings(obj, path=()):
    """Yield (path, string) for every string inside obj."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, path + (i,))


def _set_path(obj, path, value):
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def default_markdown(title: str, data: dict, mocked: bool) -> str:
    head = f"# {title}\n\n"
    if mocked:
        head += "> **MOCKED**: produced offline by MockLLM or a mock component, not by a real model run.\n\n"
    body = []
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (dict, list)):
            body.append(f"## {k}\n\n```json\n{json.dumps(v, indent=2, ensure_ascii=False)}\n```\n")
        else:
            body.append(f"## {k}\n\n{v}\n")
    return head + "\n".join(body)


def collect_sources(data: dict) -> list[str]:
    urls = []
    for c in data.get("claims", []) or []:
        if isinstance(c, dict) and c.get("source_url"):
            urls.append(c["source_url"])
    for s in data.get("sources", []) or []:
        if isinstance(s, str):
            urls.append(s)
    return list(dict.fromkeys(urls))


class Agent:
    name: str = ""
    phase: int = 0
    step: str = ""
    inputs: list[str] = []
    tools: list[str] = []
    required_keys: list[str] = []
    kind: str = "llm"
    json_retries: int = 2

    # ---------- hooks for subclasses ----------
    def system_prompt(self) -> str:
        own = (PROMPT_DIR / f"{self.name}.md").read_text(encoding="utf-8")
        common_p = PROMPT_DIR / "_common.md"
        common = common_p.read_text(encoding="utf-8") if common_p.exists() else ""
        return f"{own}\n\n{common}"

    def build_user_message(self, ctx: Context) -> str:
        payload = {"brief": ctx.brief, "inputs": {s: ctx.store.get(s) for s in self.inputs if ctx.store.has(s)}}
        if ctx.extra:
            payload["extra"] = {k: v for k, v in ctx.extra.items() if k != "halt_phase"}
        return "<data>\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n</data>"

    def post_process(self, ctx: Context, data: dict) -> dict:
        return data

    def render_markdown(self, ctx: Context, data: dict, mocked: bool) -> str:
        return default_markdown(f"{self.step} ({self.name})", data, mocked)

    # ---------- shared machinery ----------
    def check_inputs(self, ctx: Context) -> None:
        missing = [s for s in self.inputs if not ctx.store.has(s)]
        if missing:
            raise MissingInput(f"{self.name} needs {missing}")

    def save(self, ctx: Context, data: dict, markdown: str | None = None, sources=(), model=None,
             cost: float = 0.0, mocked: bool = False, action: str | None = None, **extra) -> AgentResult:
        if mocked:
            data.setdefault("mocked", True)
        md = markdown if markdown is not None else self.render_markdown(ctx, data, mocked)
        srcs = list(sources) or collect_sources(data)
        ctx.store.put(self.step, data, md, agent=self.name, sources=srcs)
        ctx.log.action(self.name, action or f"run_{self.name}", sources=srcs, model=model, cost=cost,
                       **({"mocked": True} if mocked else {}), **extra)
        return AgentResult(data=data, markdown=md, sources=srcs, model=model, cost=cost, mocked=mocked)

    def _call(self, ctx: Context, system: str, user: str):
        total_cost, last_err, resp = 0.0, None, None
        for attempt in range(self.json_retries + 1):
            msg = user if last_err is None else (
                f"{user}\n\nYour previous answer was invalid: {last_err}. Reply with valid JSON only, "
                f"containing the keys {self.required_keys}.")
            resp = ctx.llm.chat(system, msg, agent=self.name, json_mode=True)
            total_cost += resp.cost
            if resp.data is None:
                last_err = "not valid JSON"
                continue
            missing = [k for k in self.required_keys if k not in resp.data]
            if missing:
                last_err = f"missing keys {missing}"
                continue
            return resp, resp.data, total_cost
        raise ValueError(f"{self.name}: model output invalid after retries ({last_err})")

    def _guard(self, ctx: Context, data: dict, system: str, user: str) -> tuple[dict, float]:
        from core.guardrails import check_output as _check

        def check_output(s):
            r = _check(s)
            return bool(r.allowed), (", ".join(map(str, r.findings)) or "blocked")
        extra_cost = 0.0
        blocked = [(p, s, r) for p, s in _walk_strings(data) for ok, r in [check_output(s)] if not ok]
        if not blocked:
            return data, extra_cost
        reasons = sorted({r for _, _, r in blocked})
        ctx.log.action(self.name, "guardrail_block", reasons=reasons, outcome="rewrite_requested")
        try:
            resp = ctx.llm.chat(system, f"{user}\n\nYour answer was blocked by the guardrails ({reasons}). "
                                        f"Rewrite it without that content. JSON only.", agent=self.name)
            extra_cost += resp.cost
            if resp.data and all(k in resp.data for k in self.required_keys):
                still = [(p, r) for p, s in _walk_strings(resp.data) for ok, r in [check_output(s)] if not ok]
                if not still:
                    return resp.data, extra_cost
                data = resp.data
                blocked = [(p, None, r) for p, r in still]
        except Exception:
            pass
        for p, _, r in blocked:
            _set_path(data, p, f"{BLOCK_MARK} {r}")
        ctx.log.action(self.name, "guardrail_drop", reasons=sorted({r for *_, r in blocked}), outcome="dropped")
        return data, extra_cost

    def run(self, ctx: Context) -> AgentResult:
        if self.kind != "llm":
            raise NotImplementedError(f"{self.name}: kind '{self.kind}' must override run()")
        self.check_inputs(ctx)
        system, user = self.system_prompt(), self.build_user_message(ctx)
        resp, data, cost = self._call(ctx, system, user)
        tokens = {"tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out}
        if "claims" in data:
            from core.claims import verify_claims
            data = verify_claims(ctx, data)
        data, gcost = self._guard(ctx, data, system, user)
        data = self.post_process(ctx, data)
        mocked = bool(ctx.mock or data.get("mocked") or resp.model == "mock-llm")
        return self.save(ctx, data, sources=collect_sources(data), model=resp.model,
                         cost=cost + gcost, mocked=mocked, **tokens)
