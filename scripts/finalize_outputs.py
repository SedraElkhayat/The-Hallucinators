# OWNER: M1
"""Copy a real run (runs/<id>) into the committed outputs/ and decision_log.json, without editing any artifact."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(run_dir: str) -> int:
    src = Path(run_dir)
    if not (src / "outputs").is_dir() or not (src / "decision_log.json").exists():
        print(f"{src} is not a run folder (needs outputs/ and decision_log.json)")
        return 1
    dst = ROOT / "outputs"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src / "outputs", dst)
    shutil.copy2(src / "decision_log.json", ROOT / "decision_log.json")
    print(f"copied {src} -> outputs/ and decision_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else 1)
