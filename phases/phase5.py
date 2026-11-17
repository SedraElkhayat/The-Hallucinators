# OWNER: M4
# STUB: replace the contents, keep the public names. Empty STAGES means the phase is STUBBED in a run.
"""Phase 5."""
from gates import Check

PHASE = 5
STAGES: list[list[str]] = []      # e.g. [["agent_a"], ["agent_b", "agent_c"]]; empty = phase STUBBED
REVISE = None                     # (producer, critic) or None
PIVOT_TO = None


def gate_checks(ctx) -> list[Check]:
    return []


def measure(ctx) -> dict:
    return {}
