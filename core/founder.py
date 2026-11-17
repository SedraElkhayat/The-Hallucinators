# OWNER: M1
"""Founder input. Modes: web (inbox shared with app.py), cli (stdin), scripted (demo file, labeled SCRIPTED)."""
from __future__ import annotations

import itertools
import json
import threading
from pathlib import Path
from typing import Optional


class Inbox:
    """Thread-safe queue of open questions for the web UI. The pipeline thread blocks until answered."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.items: dict[int, dict] = {}

    def open(self, kind: str, key: str, prompt: str, options=None, content: str = "", phase=None) -> dict:
        with self._lock:
            i = next(self._ids)
            item = {"id": i, "kind": kind, "key": key, "prompt": prompt, "options": options or [],
                    "content": content, "phase": phase, "status": "pending", "answer": None,
                    "_event": threading.Event()}
            self.items[i] = item
        return item

    def answer(self, item_id: int, answer: str) -> None:
        with self._lock:
            item = self.items[item_id]
            if item["status"] != "pending":
                return
            item["answer"], item["status"] = answer, "answered"
        item["_event"].set()

    def wait(self, item: dict, timeout: Optional[float] = None) -> str:
        if not item["_event"].wait(timeout):
            raise TimeoutError(f"no founder answer for {item['key']}")
        return item["answer"]

    def pending(self) -> list[dict]:
        with self._lock:
            return [{k: v for k, v in it.items() if k != "_event"}
                    for it in self.items.values() if it["status"] == "pending"]

    def all(self) -> list[dict]:
        with self._lock:
            return [{k: v for k, v in it.items() if k != "_event"} for it in self.items.values()]


INBOX = Inbox()


class ScriptedInputs:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def lookup(self, key: str) -> str:
        if key in self.data and key not in ("prefix_defaults", "approvals", "answers"):
            return self.data[key]
        answers = self.data.get("answers", {})
        if key in answers:
            return answers[key]
        defaults = self.data.get("prefix_defaults", {})
        best = max((p for p in defaults if key.startswith(p)), key=len, default=None)
        if best is not None:
            return defaults[best]
        raise KeyError(f"SCRIPTED founder inputs have no answer for '{key}' "
                       f"(add the key or a matching 'prefix_defaults' entry to {self.path.name})")

    def approval(self, kind: str, phase: Optional[int] = None, outcome: Optional[str] = None) -> str:
        """Most specific key wins: ``<kind>_<phase>_<outcome>`` (e.g. ``gate_1_stop``: only when the
        system recommends STOP at Gate 1), then ``<kind>_<phase>``, then ``<kind>``, then ``default``."""
        appr = self.data.get("approvals", {})
        if phase is not None and outcome and f"{kind}_{phase}_{outcome}" in appr:
            return appr[f"{kind}_{phase}_{outcome}"]
        if phase is not None and f"{kind}_{phase}" in appr:
            return appr[f"{kind}_{phase}"]
        return appr.get(kind, appr.get("default", "approve"))


class FounderInput:
    def __init__(self, mode: str, log, scripted: Optional[ScriptedInputs] = None,
                 inbox: Optional[Inbox] = None, input_fn=input):
        if mode not in ("web", "cli", "scripted"):
            raise ValueError(mode)
        if mode == "scripted" and scripted is None:
            raise ValueError("scripted mode needs a founder inputs file")
        self.mode, self.log, self.scripted = mode, log, scripted
        self.inbox = inbox or INBOX
        self.input_fn = input_fn

    def _get(self, key: str, prompt: str, options=None) -> str:
        if self.mode == "scripted":
            value = self.scripted.lookup(key)
            label = "SCRIPTED"
        elif self.mode == "cli":
            opts = f" [{' / '.join(options)}]" if options else ""
            value = self.input_fn(f"\n[FOUNDER] {prompt}{opts}\n> ").strip()
            label = "CLI"
        else:
            item = self.inbox.open("input", key, prompt, options)
            value = self.inbox.wait(item)
            label = "WEB"
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        self.log.action("founder", f"founder_input:{key}", provenance=label, approved_by=None)
        return str(value)

    def ask(self, key: str, prompt: str, options: Optional[list[str]] = None) -> str:
        return self._get(key, prompt, options)

    def provide(self, key: str, prompt: str) -> str:
        return self._get(key, prompt)
