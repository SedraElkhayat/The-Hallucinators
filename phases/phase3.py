# OWNER: M3
# STUB: replace the contents, keep the public names. Empty STAGES means the phase is STUBBED in a run.
"""Phase 3."""
from gates import Check

PHASE = 3
STAGES: list[list[str]] = []      # e.g. [["agent_a"], ["agent_b", "agent_c"]]; empty = phase STUBBED
REVISE = None                     # (producer, critic) or None
PIVOT_TO = 2


def gate_checks(ctx) -> list[Check]:
    return []


def measure(ctx) -> dict:
    return {}
