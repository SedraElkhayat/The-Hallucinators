# OWNER: M2
"""Evidence and honesty audit of a run's outputs folder.

Usage: python scripts/audit_outputs.py [OUT_DIR]   (default: outputs)

Fails (exit code 1) on:
- an empty file;
- a market claim without an http(s) source URL that is not labeled as an assumption;
- a claim marked verified false that is not labeled as an assumption;
- a report finding that cites no claim and is not labeled as an assumption;
- a banned phrase (income guarantee, "risk-free", "5-star", "great idea", countdown timers), unless negated
  ("we cannot guarantee", "no countdown");
- inconsistent labels: a JSON artifact marked mocked (or with provenance MOCKED / SAMPLE) whose .md does not
  show that label.
Gate criteria files, decision logs and the build sandbox are scanned for banned phrases only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BANNED = [
    ("income guarantee", re.compile(r"\bguarantee[sd]?\b", re.I)),
    ("risk-free claim", re.compile(r"\brisk[- ]free\b", re.I)),
    ("star rating", re.compile(r"\b(?:5|five)[- ]stars?\b", re.I)),
    ("unsupported praise", re.compile(r"\bgreat idea\b", re.I)),
    ("countdown timer", re.compile(r"\bcountdown\b", re.I)),
    ("income promise", re.compile(r"\byou will earn\b", re.I)),
]
NEGATION = re.compile(r"\b(?:no|not|never|without|cannot|can't|don't|doesn't|won't|nor|avoid\w*|refuse\w*|"
                      r"block\w*|banned)\b", re.I)
WINDOW = 40
TEXT_EXT = {".md", ".json", ".html", ".txt", ".csv"}
SKIP_CLAIM_RULES = ("_gate_", "decision_log")


def _negated(text: str, start: int) -> bool:
    before = text[max(0, start - WINDOW):start]
    before = re.split(r"[.!?\n]", before)[-1]
    return bool(NEGATION.search(before))


def banned_hits(text: str) -> list[str]:
    hits = []
    for label, rx in BANNED:
        for m in rx.finditer(text):
            if not _negated(text, m.start()):
                hits.append(f"{label}: '{text[max(0, m.start() - 30):m.end() + 30].strip()}'")
                break
    return hits


def _is_assumption(d: dict) -> bool:
    if d.get("assumption") is True:
        return True
    return any("ASSUMPTION" in str(d.get(k, "")) for k in ("claim", "text"))


def claim_problems(obj, where: str = "") -> list[str]:
    """Walk JSON: check every claim dict and every report finding."""
    out = []
    if isinstance(obj, dict):
        if "claim" in obj and "source_url" in obj:
            url = str(obj.get("source_url") or "")
            if not url.lower().startswith(("http://", "https://")) and not _is_assumption(obj):
                out.append(f"{where}: claim without a source URL and not an ASSUMPTION: {str(obj.get('claim'))[:100]}")
            if obj.get("verified") is False and not _is_assumption(obj):
                out.append(f"{where}: unverified claim not labeled ASSUMPTION: {str(obj.get('claim'))[:100]}")
        for k, v in obj.items():
            if k == "findings" and isinstance(v, list):
                for i, f in enumerate(v):
                    if isinstance(f, dict) and "text" in f and not (f.get("claim_ids") or f.get("claims")
                                                                     or f.get("sources") or _is_assumption(f)):
                        out.append(f"{where}.findings[{i}]: finding cites no claim and is not an ASSUMPTION: "
                                   f"{str(f.get('text'))[:100]}")
            out += claim_problems(v, f"{where}.{k}" if where else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += claim_problems(v, f"{where}[{i}]")
    return out


def label_problems(data: dict, md_text: str) -> list[str]:
    out = []
    if data.get("mocked") is True and "MOCKED" not in md_text:
        out.append("JSON is marked mocked but the .md does not say MOCKED")
    prov = str(data.get("provenance", "")).upper()
    if prov in ("MOCKED", "SAMPLE") and prov not in md_text:
        out.append(f"provenance {prov} is not shown in the .md")
    return out


def audit(out_dir: Path) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {}

    def add(path: Path, msg: str):
        problems.setdefault(str(path.relative_to(out_dir)), []).append(msg)

    for p in sorted(out_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            add(p, "empty file")
            continue
        for h in banned_hits(text):
            add(p, f"banned phrase ({h})")
        if p.suffix.lower() != ".json" or any(s in p.name for s in SKIP_CLAIM_RULES) or p.parent != out_dir:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            add(p, f"invalid JSON ({e})")
            continue
        if not isinstance(data, dict):
            continue
        for msg in claim_problems(data):
            add(p, msg)
        md = p.with_suffix(".md")
        if md.exists():
            for msg in label_problems(data, md.read_text(encoding="utf-8", errors="replace")):
                add(p, msg)
    return problems


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out_dir = Path(argv[0] if argv else "outputs")
    if not out_dir.is_dir():
        print(f"AUDIT FAIL: {out_dir} is not a folder")
        return 1
    files = [p for p in out_dir.rglob("*") if p.is_file()]
    problems = audit(out_dir)
    print(f"Evidence and honesty audit of {out_dir} ({len(files)} files)")
    if not problems:
        print("AUDIT PASS: every claim is sourced or labeled ASSUMPTION; no banned phrases; labels consistent.")
        return 0
    n = sum(len(v) for v in problems.values())
    for name, msgs in problems.items():
        print(f"\n{name}")
        for m in msgs:
            print(f"  - {m}")
    print(f"\nAUDIT FAIL: {n} problem(s) in {len(problems)} file(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
