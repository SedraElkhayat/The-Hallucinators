# OWNER: M1
"""Typed artifacts: <out_dir>/<step>.json (machine) and <step>.md (human)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

ALLOWED_EXT = {"md", "json", "csv", "txt", "html"}


class ArtifactStore:
    def __init__(self, out_dir: Path | str):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def put(self, step: str, data: dict, markdown: str, agent: str, sources=()) -> None:
        payload = dict(data)
        payload.setdefault("_meta", {"agent": agent, "sources": list(sources or [])})
        with self._lock:
            (self.out_dir / f"{step}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            (self.out_dir / f"{step}.md").write_text(markdown or "", encoding="utf-8")

    def put_file(self, step: str, ext: str, text: str, agent: str) -> None:
        ext = ext.lstrip(".").lower()
        if ext not in ALLOWED_EXT:
            raise ValueError(f"extension .{ext} not allowed in outputs/")
        with self._lock:
            (self.out_dir / f"{step}.{ext}").write_text(text, encoding="utf-8")

    def get(self, step: str) -> dict:
        p = self.out_dir / f"{step}.json"
        if not p.exists():
            raise KeyError(step)
        data = json.loads(p.read_text(encoding="utf-8"))
        data.pop("_meta", None)
        return data

    def has(self, step: str) -> bool:
        return (self.out_dir / f"{step}.json").exists()

    def names(self) -> list[str]:
        return sorted(p.stem for p in self.out_dir.glob("*.json"))
