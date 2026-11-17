# OWNER: M4
# STUB: replace the contents, keep the public names
"""Input, output and release checks.

check_input(text)  -> GuardResult  (redacts card-like numbers)
check_output(text) -> GuardResult  (allowed=False blocks the text)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_BLOCKED = [("income_promise", re.compile(r"guarantee", re.I)),
            ("unsupported_praise", re.compile(r"great idea", re.I)),
            ("fake_reviews", re.compile(r"5-star", re.I))]


@dataclass
class GuardResult:
    allowed: bool
    text: str
    findings: list[str] = field(default_factory=list)


def check_input(text: str) -> GuardResult:
    findings = ["card_number"] if _CARD.search(text or "") else []
    return GuardResult(True, _CARD.sub("[REDACTED]", text or ""), findings)


def check_output(text: str) -> GuardResult:
    findings = [name for name, rx in _BLOCKED if rx.search(text or "")]
    return GuardResult(not findings, text or "", findings)
