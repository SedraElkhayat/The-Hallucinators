# OWNER: M1
"""Phase modules phases/phase1.py .. phase6.py, loaded by number."""
import importlib


def load_phase(n: int):
    return importlib.import_module(f"phases.phase{n}")
