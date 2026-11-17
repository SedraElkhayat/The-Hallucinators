# OWNER: M1
"""Append-only decision log (JSON array). Atomic and thread-safe."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()


class DecisionLog:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> list:
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "[]")
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, entries: list) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def action(self, agent: str, action: str, sources=(), model: Optional[str] = None,
               cost: float = 0.0, approved_by: Optional[str] = None, **extra) -> dict:
        if approved_by not in (None, "founder"):
            raise ValueError("approved_by must be 'founder' or None")
        entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": agent,
            "action": action,
            "sources": list(sources or []),
            "model": model,
            "cost": float(cost or 0.0),
            "approved_by": approved_by,
        }
        entry.update(extra)
        with _LOCK:
            entries = self._read()
            entries.append(entry)
            self._write(entries)
        return entry

    def entries(self) -> list:
        with _LOCK:
            return self._read()
