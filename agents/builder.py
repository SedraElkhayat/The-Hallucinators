"""builder: the model writes the files of a small static product; code validates and saves them.

Files are written ONLY inside <ctx.out_dir>/phase3_build/. Nothing is deployed and no network
connection is opened. Rejected files get one rewrite chance, then they are dropped and recorded.
"""
import json
import shutil
from pathlib import Path

from agents.base import Agent
from agents.m3_common import (BUILD_DIRNAME, M3InputsMixin, P3_BUILD, P3_COPY, P3_SPEC, build_dir,
                              content_violations, guardrail_findings, load_system_prompt, log_action,
                              network_code_present, safe_rel_path)

ALLOWED_EXTENSIONS = (".html", ".md", ".txt", ".csv", ".json")
MAX_FILES = 6
MAX_CHARS = 20000


def check_file(path, content) -> tuple:
    """Return (normalized_path, reasons). Empty reasons means the file is accepted."""
    reasons = []
    rel = safe_rel_path(path)
    if rel is None:
        reasons.append(f"unsafe path {path!r} (relative paths only, no '..')")
    elif not rel.lower().endswith(ALLOWED_EXTENSIONS):
        reasons.append(f"extension not allowed for {rel} (allowed: {', '.join(ALLOWED_EXTENSIONS)})")
    if not isinstance(content, str) or not content.strip():
        reasons.append("empty content")
        return rel, reasons
    if len(content) > MAX_CHARS:
        reasons.append(f"content longer than {MAX_CHARS} characters")
    reasons += content_violations(content)
    if network_code_present(content):
        reasons.append("network code")
    reasons += [f"guardrails: {f}" for f in guardrail_findings(content)]
    return rel, sorted(set(reasons))


def validate_files(files) -> tuple:
    """Split model output into accepted [{path, content}] and rejected [{path, reasons, content}]."""
    accepted, rejected, seen = [], [], set()
    for f in files or []:
        if not isinstance(f, dict):
            rejected.append({"path": str(f)[:80], "reasons": ["not an object with path and content"], "content": ""})
            continue
        rel, reasons = check_file(f.get("path"), f.get("content"))
        if not reasons and rel in seen:
            reasons = ["duplicate path"]
        if reasons:
            rejected.append({"path": str(f.get("path")), "reasons": reasons, "content": f.get("content") or ""})
        else:
            seen.add(rel)
            accepted.append({"path": rel, "content": f["content"]})
    return accepted, rejected


class Builder(M3InputsMixin, Agent):
    name = "builder"
    phase = 3
    step = P3_BUILD
    inputs = [P3_SPEC, P3_COPY]
    tools = []
    required_keys = ["files", "notes"]
    kind = "llm"

    def _rewrite(self, ctx, rejected) -> list:
        request = [{"path": r["path"], "reasons": r["reasons"]} for r in rejected]
        user = self.build_user_message(ctx) + "\n<data>\n" + json.dumps(
            {"rewrite_request": request}, ensure_ascii=False) + "\n</data>\nRewrite only these files so they follow every rule."
        try:
            resp = ctx.llm.chat(load_system_prompt(self.name), user, agent=self.name, json_mode=True)
        except Exception as exc:  # noqa: BLE001 - a failed rewrite leaves the files dropped
            log_action(ctx, self.name, "rewrite_rejected_files", error=str(exc)[:200])
            return []
        log_action(ctx, self.name, "rewrite_rejected_files", model=getattr(resp, "model", None),
                   cost=getattr(resp, "cost", 0.0) or 0.0, files=[r["path"] for r in request])
        data = resp.data if isinstance(getattr(resp, "data", None), dict) else {}
        wanted = {safe_rel_path(r["path"]) or r["path"] for r in rejected}
        return [f for f in data.get("files") or []
                if isinstance(f, dict) and (safe_rel_path(f.get("path")) or f.get("path")) in wanted]

    def run(self, ctx):
        result = super().run(ctx)  # model call, required keys, guardrails, artifact, log entry
        data = result.data or {}
        accepted, rejected = validate_files(data.get("files"))
        dropped = []
        if rejected:
            retry_ok, retry_bad = validate_files(self._rewrite(ctx, rejected))
            fixed = {f["path"] for f in retry_ok}
            have = {f["path"] for f in accepted}
            accepted += [f for f in retry_ok if f["path"] not in have]
            retried_bad = {safe_rel_path(r["path"]) or r["path"] for r in retry_bad}
            for r in rejected:
                key = safe_rel_path(r["path"]) or r["path"]
                if key not in fixed and key not in retried_bad:
                    dropped.append({"path": r["path"], "reasons": r["reasons"]})
            for r in retry_bad:
                dropped.append({"path": r["path"], "reasons": ["after rewrite: " + "; ".join(r["reasons"])]})
        if len(accepted) > MAX_FILES:
            dropped += [{"path": f["path"], "reasons": [f"more than {MAX_FILES} files"]} for f in accepted[MAX_FILES:]]
            accepted = accepted[:MAX_FILES]

        root = build_dir(ctx)
        if root.exists():  # a repeat round starts from a clean sandbox folder
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        base = root.resolve()
        written = []
        for f in accepted:
            target = (root / f["path"]).resolve()
            if base not in target.parents:  # defence in depth; safe_rel_path already checked
                dropped.append({"path": f["path"], "reasons": ["resolved outside the build folder"]})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f["content"], encoding="utf-8")
            written.append({"path": f["path"], "chars": len(f["content"])})

        manifest = {
            "build_dir": BUILD_DIRNAME,
            "files": written,
            "notes": str(data.get("notes", "")),
            "dropped": dropped,
            "deployed": False,
        }
        md = [f"# Build manifest\n\nFiles written to `{BUILD_DIRNAME}/` (sandbox folder; nothing deployed).\n"]
        md += [f"- `{w['path']}` ({w['chars']} characters)" for w in written] or ["- (no files)"]
        if dropped:
            md.append("\n## Dropped files\n")
            md += [f"- `{d['path']}`: {'; '.join(d['reasons'])}" for d in dropped]
        md.append(f"\n## Notes\n\n{manifest['notes']}\n")
        markdown = "\n".join(md)
        ctx.store.put(self.step, manifest, markdown, self.name, list(result.sources or []))
        result.data, result.markdown = manifest, markdown
        return result
