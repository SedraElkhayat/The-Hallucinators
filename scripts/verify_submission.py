# OWNER: M1
"""Mirror of the CLAUDE.md 'Before every push' checklist. FAIL exits 1; WARN is for work still in progress."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README_HEADINGS = ["Quickstart", "What works and what is mocked", "Architecture", "Models and free resources",
                   "Cost per run", "Demo video", "What our system will NOT do",
                   "How the project stays alive after the hackathon"]
ARCH_SECTIONS = ["Overview", "Phases", "Gates", "Sale to cash", "Data flow", "Built vs. stubbed", "Roadmap"]
LOG_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
SECRET_RX = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
NAME_RX = re.compile(r"^(phase\d+_(step\d+_[\w-]+|gate_[\w-]+)\.(md|json|csv|txt|html)|payment_test_log\.md|\.gitkeep)$")
DIR_RX = re.compile(r"^phase\d+_step\d+_[\w-]+$")          # e.g. outputs/phase3_step3_site/
TEXT_EXT = {".md", ".json", ".csv", ".txt", ".html"}           # CLAUDE.md: text formats only
MAX_OUTPUT_BYTES = 300_000                                      # "keep each file small"

results: list[tuple[str, str]] = []


def check(level_if_bad: str, ok: bool, msg: str) -> None:
    results.append(("PASS" if ok else level_if_bad, msg))


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except Exception:
        return []


def repo_files() -> list[str]:
    return tracked_files() or [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                               if p.is_file() and not {".git", "runs", ".cache", "__pycache__"} & set(p.parts)]


def run_checks(run_tests: bool = True) -> list[tuple[str, str]]:
    results.clear()
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    heads = re.findall(r"^## (.+?)\s*$", readme, flags=re.M)
    check("FAIL", [h for h in heads if h in README_HEADINGS] == README_HEADINGS, "README: eight ## headings in order")
    qs = readme.split("## Quickstart", 1)[-1].split("\n## ", 1)[0]
    check("FAIL", re.search(r"```bash\s*\ndocker compose up\s*\n```", qs) is not None, "README: Quickstart has `docker compose up`")
    cost = readme.split("## Cost per run", 1)[-1].split("\n## ", 1)[0]
    check("FAIL", "$" in cost, "README: Cost per run has a $ figure")
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8") if (ROOT / "LICENSE").exists() else ""
    check("FAIL", "Permission is hereby granted" in lic and "MIT License" in lic, "LICENSE: MIT full text")
    check("FAIL", (ROOT / "docker-compose.yml").exists() or (ROOT / "compose.yaml").exists(), "docker-compose.yml present")

    try:
        log = json.loads((ROOT / "decision_log.json").read_text(encoding="utf-8"))
        bad = [i for i, e in enumerate(log) if any(k not in e for k in LOG_KEYS)]
        check("FAIL", isinstance(log, list) and not bad, f"decision_log.json valid ({len(log)} entries, bad: {bad[:5]})")
        check("WARN", len(log) > 0, "decision_log.json has entries from the demo run")
    except Exception as e:
        check("FAIL", False, f"decision_log.json readable ({e})")

    out = ROOT / "outputs"
    entries = list(out.iterdir()) if out.is_dir() else []
    names = [p.name for p in entries if p.is_file()]
    dirs = [p for p in entries if p.is_dir()]
    check("FAIL", out.is_dir(), "outputs/ present")
    wrong = [n for n in names if not NAME_RX.match(n)] + [d.name + "/" for d in dirs if not DIR_RX.match(d.name)]
    check("FAIL", not wrong, f"outputs/ naming (wrong: {wrong[:5]})")
    nested = [f for d in dirs for f in d.rglob("*") if f.is_file()]
    bad_ext = [f.relative_to(out).as_posix() for f in nested if f.suffix.lower() not in TEXT_EXT]
    check("FAIL", not bad_ext, f"outputs/ folders hold text files only (wrong: {bad_ext[:5]})")
    big = [f.relative_to(out).as_posix() for f in [out / n for n in names] + nested
           if f.stat().st_size > MAX_OUTPUT_BYTES]
    check("FAIL", not big, f"outputs/ files are small (over {MAX_OUTPUT_BYTES // 1000} KB: {big[:5]})")
    check("WARN", any(re.match(r"phase\d+_gate_decision\.md", n) for n in names), "outputs/ has a gate decision")
    check("WARN", "payment_test_log.md" in names, "outputs/payment_test_log.md present")
    check("WARN", any("stop" in (out / n).read_text(encoding="utf-8").lower()
                      for n in names if re.match(r"phase\d+_gate_decision\.md", n)), "outputs/ shows a STOP")

    gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
    check("FAIL", ".env" in gi.split() and "CONTEXT.md" in gi.split(), ".gitignore covers .env and CONTEXT.md")
    tracked = tracked_files()
    for forbidden in ("CONTEXT.md", ".env"):
        check("FAIL", forbidden not in tracked, f"{forbidden} not committed")
    check("FAIL", not any(t.startswith("PROGRESS_") for t in tracked), "PROGRESS_*.md not committed")
    check("FAIL", not any(t.startswith("docs/") and t.lower().endswith("claude.md") for t in tracked), "CLAUDE.md not in docs/")
    env_ex = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
    check("FAIL", not SECRET_RX.search(env_ex), ".env.example has placeholders only")
    files = repo_files()
    leaks = []
    for t in files:
        p = ROOT / t
        if p.suffix in {".py", ".md", ".json", ".yml", ".yaml", ".txt", ".html", ".sh", ".example", ".csv"}:
            try:
                if SECRET_RX.search(p.read_text(encoding="utf-8", errors="ignore")):
                    leaks.append(t)
            except Exception:
                pass
    check("FAIL", not leaks, f"no secrets in files (suspects: {leaks[:5]})")

    arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8") if (ROOT / "ARCHITECTURE.md").exists() else ""
    aheads = re.findall(r"^## (.+?)\s*$", arch, flags=re.M)
    check("FAIL", all(s in aheads for s in ARCH_SECTIONS), "ARCHITECTURE.md sections")
    check("FAIL", "```mermaid" in arch, "ARCHITECTURE.md has Mermaid diagrams")
    check("FAIL", (ROOT / "prompts" / "_common.md").exists(), "prompts/ present")
    check("FAIL", any((ROOT / "tests").glob("test_*.py")), "tests/ has smoke tests")
    check("FAIL", "MOCKED" in readme, "README labels mocks")

    if run_tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or ["no output"])[-1]
        check("FAIL", r.returncode == 0, f"tests pass ({tail})")
    return list(results)


def main() -> int:
    run_checks(run_tests="--no-tests" not in sys.argv)
    for lvl, msg in results:
        print(f"{lvl:4}  {msg}")
    fails = sum(1 for l, _ in results if l == "FAIL")
    warns = sum(1 for l, _ in results if l == "WARN")
    print(f"\n{fails} FAIL, {warns} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
