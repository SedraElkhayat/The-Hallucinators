"""qa_agent (code kind): runs each acceptance check from the spec against the built files."""
from pathlib import Path

from agents.base import Agent
from agents.m3_common import P3_BUILD, P3_QA, P3_SPEC, build_dir, get_artifact, safe_rel_path


def run_check(root: Path, check: dict) -> tuple:
    """Run one check against the build folder. Returns (passed, detail)."""
    if not isinstance(check, dict):
        return False, "check missing"
    ctype = str(check.get("type", ""))
    raw = check.get("path", "")
    rel = safe_rel_path(raw)
    if rel is None:
        return False, f"{ctype} {raw!r}: path is not a safe relative path inside the build folder"
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        return False, f"{ctype} {rel}: path leaves the build folder"
    if ctype == "file_exists":
        return (True, f"file_exists {rel}: found") if target.is_file() else (False, f"file_exists {rel}: not found")
    if ctype == "text_contains":
        needle = str(check.get("text") or "")
        if not needle:
            return False, f"text_contains {rel}: no text given to look for"
        if not target.is_file():
            return False, f"text_contains {rel}: file not found"
        content = target.read_text(encoding="utf-8", errors="replace")
        return (True, f"text_contains {rel}: found {needle!r}") if needle in content else \
            (False, f"text_contains {rel}: text {needle!r} not found")
    return False, f"unknown check type {ctype!r}"


class QaAgent(Agent):
    name = "qa_agent"
    phase = 3
    step = P3_QA
    inputs = [P3_SPEC, P3_BUILD]
    tools = []
    required_keys = ["results", "pass_ratio"]
    kind = "code"

    def run(self, ctx):
        self.check_inputs(ctx)
        spec = get_artifact(ctx, P3_SPEC) or {}
        root = build_dir(ctx)
        results = []
        for n, t in enumerate(spec.get("acceptance_tests") or [], 1):
            tid = str(t.get("id") or f"AT{n}") if isinstance(t, dict) else f"AT{n}"
            passed, detail = run_check(root, t.get("check") if isinstance(t, dict) else None)
            results.append({"id": tid, "passed": bool(passed), "detail": detail})
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        data = {"results": results, "pass_ratio": round(passed / total, 4) if total else 0.0,
                "total": total, "passed": passed}
        lines = [f"# QA report\n\nAcceptance checks run in code against `{root.name}/`: "
                 f"{passed} of {total} passed (pass ratio {data['pass_ratio']}).\n",
                 "| Test | Result | Detail |", "|---|---|---|"]
        lines += [f"| {r['id']} | {'PASS' if r['passed'] else 'FAIL'} | {r['detail']} |" for r in results]
        if not total:
            lines.append("\nNo acceptance tests were found in the spec, so nothing passed.")
        md = "\n".join(lines) + "\n"
        return self.save(ctx, data, markdown=md, sources=[], model=None, cost=0.0, mocked=False,
                         action="run_acceptance_tests", passed_count=passed, total_count=total)
