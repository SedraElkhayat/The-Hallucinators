# OWNER: M1
"""The only door to anything outward-facing. Blocking founder approve/reject, enforced in code."""
from __future__ import annotations

import threading
from typing import Optional

from core.founder import INBOX, Inbox, ScriptedInputs

APPROVE_WORDS = {"approve", "approved", "yes", "y", "go", "ok"}


class NotApproved(Exception):
    """Raised when something outward-facing is released without a founder approval."""


class Approvals:
    def __init__(self, mode: str, log, scripted: Optional[ScriptedInputs] = None,
                 inbox: Optional[Inbox] = None, input_fn=input):
        self.mode, self.log, self.scripted = mode, log, scripted
        self.inbox = inbox or INBOX
        self.input_fn = input_fn
        self.records: list[dict] = []
        self._lock = threading.Lock()

    def _decide(self, kind: str, title: str, content: str, phase: int,
                outcome: Optional[str] = None) -> tuple[str, str]:
        if self.mode == "scripted":
            return self.scripted.approval(kind, phase, outcome), "SCRIPTED"
        if self.mode == "cli":
            print(f"\n===== APPROVAL NEEDED (phase {phase}, {kind}) =====\n{title}\n\n{content[:3000]}\n")
            return self.input_fn("[FOUNDER] approve or reject? > ").strip(), "CLI"
        item = self.inbox.open("approval", kind, title, ["approve", "reject"], content=content, phase=phase)
        return self.inbox.wait(item), "WEB"

    def request(self, kind: str, title: str, content: str, phase: int, outcome: Optional[str] = None) -> bool:
        """``outcome`` (optional, gates only) is the system's verdict, so scripted answers can target it."""
        self.log.action("approval", f"approval_requested:{kind}", phase=phase, title=title)
        answer, provenance = self._decide(kind, title, content, phase, outcome)
        approved = str(answer).strip().lower() in APPROVE_WORDS
        rec = {"kind": kind, "title": title, "phase": phase,
               "status": "approved" if approved else "rejected", "provenance": provenance}
        with self._lock:
            self.records.append(rec)
        self.log.action("founder", f"{'approved' if approved else 'rejected'}:{kind}",
                        approved_by="founder" if approved else None,
                        phase=phase, title=title, provenance=provenance)
        return approved

    def is_approved(self, kind: str, title: str) -> bool:
        with self._lock:
            return any(r["kind"] == kind and r["title"] == title and r["status"] == "approved"
                       for r in self.records)

    def release(self, kind: str, title: str, content: str, phase: int) -> bool:
        """Mark an outward-facing item (page, post, draft) released. Only possible after founder approval.

        Asks the founder if no approval exists yet. Rejected items are never released (NotApproved).
        Releasing only records the decision: the system itself never publishes, sends, spends or signs.
        """
        if not self.is_approved(kind, title) and not self.request(kind, title, content, phase):
            self.log.action("approval", f"release_blocked:{kind}", phase=phase, title=title, outcome="blocked")
            raise NotApproved(f"{kind} '{title}' was rejected by the founder")
        self.log.action("approval", f"released:{kind}", approved_by="founder", phase=phase, title=title)
        return True
