# OWNER: M4
# STUB: replace the contents, keep the public names
"""MOCKED webhook handler: verifies the mock signature and ignores repeated idempotency keys."""
MOCKED = True


def handle_event(event: dict) -> dict:
    """Process one MOCKED event; repeated idempotency keys are ignored. Returns {"status", "detail"}."""
    raise NotImplementedError
