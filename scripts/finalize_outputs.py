# OWNER: M1
"""Copy a real run (runs/<id>) into the committed outputs/ and decision_log.json, without editing any artifact.

    python scripts/finalize_outputs.py runs/final [--weak runs/weak]

--weak adds a second run (the weak brief) next to the main one: its gate files are copied as
phase<N>_gate_weak_<name> (contents unchanged), and its log entries are appended to decision_log.json
with "run": "weak". The main run's entries get "run": "strong".
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_RX = re.compile(r"^(phase\d+)_gate_(.+)$")


def _is_run(src: Path) -> bool:
    ok = (src / "outputs").is_dir() and (src / "decision_log.json").exists()
    if not ok:
        print(f"{src} is not a run folder (needs outputs/ and decision_log.json)")
    return ok


def _tagged(log_path: Path, run: str) -> list:
    return [{**e, "run": run} for e in json.loads(log_path.read_text(encoding="utf-8"))]


def main(run_dir: str, weak_dir: str | None = None, root: Path = ROOT) -> int:
    src = Path(run_dir)
    weak = Path(weak_dir) if weak_dir else None
    if not _is_run(src) or (weak and not _is_run(weak)):
        return 1
    dst = root / "outputs"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src / "outputs", dst)
    if not weak:
        shutil.copy2(src / "decision_log.json", root / "decision_log.json")
        print(f"copied {src} -> outputs/ and decision_log.json")
        return 0
    copied = []
    for f in sorted((weak / "outputs").iterdir()):
        m = GATE_RX.match(f.name)
        if f.is_file() and m:
            name = f"{m.group(1)}_gate_weak_{m.group(2)}"
            shutil.copy2(f, dst / name)
            copied.append(name)
    log = _tagged(src / "decision_log.json", "strong") + _tagged(weak / "decision_log.json", "weak")
    (root / "decision_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"copied {src} -> outputs/; weak run {weak}: {', '.join(copied) or 'no gate files'}; "
          f"decision_log.json has {len(log)} entries")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    weak_arg = None
    if "--weak" in args:
        i = args.index("--weak")
        weak_arg = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
        if weak_arg is None:
            sys.exit(1)
    sys.exit(main(args[0], weak_arg) if args else 1)
