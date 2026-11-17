# OWNER: M1
"""Auto-discovery: every Agent subclass in agents/*.py is registered by its `name`."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from agents.base import Agent

_REGISTRY: dict[str, type[Agent]] = {}
_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    pkg_dir = Path(__file__).resolve().parent
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        if mod.name in ("base",) or mod.name.startswith("_"):
            continue
        importlib.import_module(f"agents.{mod.name}")
    stack = list(Agent.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if getattr(cls, "name", ""):
            if cls.name in _REGISTRY and _REGISTRY[cls.name] is not cls:
                raise RuntimeError(f"duplicate agent name {cls.name}")
            _REGISTRY[cls.name] = cls


def get_agent(name: str) -> Agent:
    _load()
    if name not in _REGISTRY:
        raise KeyError(f"no agent named '{name}' (expected agents/{name}.py)")
    return _REGISTRY[name]()


def has_agent(name: str) -> bool:
    _load()
    return name in _REGISTRY


def all_agents() -> dict[str, type[Agent]]:
    _load()
    return dict(_REGISTRY)
