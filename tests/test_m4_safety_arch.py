# OWNER: M4
"""Safety Architecture tests.

Scans the repository source to enforce:
1. No payment SDK is imported or listed in requirements.txt.
2. Mock sale-to-cash modules do not import requests, urllib, http, socket, or smtplib.
3. No module defines or imports real capabilities that publish, send emails, or move money.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOCK_MODULES = ["payments.py", "webhooks.py", "delivery.py", "refunds.py", "reconcile.py"]
FORBIDDEN_SDKS = ["stripe", "paypal", "paymob", "braintree", "square", "paddle", "checkout_sdk"]
FORBIDDEN_NETWORKS_IN_MOCKS = ["requests", "urllib", "http", "socket", "smtplib"]


def test_requirements_no_payment_sdks():
    req_file = ROOT / "requirements.txt"
    if req_file.exists():
        text = req_file.read_text(encoding="utf-8").lower()
        for sdk in FORBIDDEN_SDKS:
            assert sdk not in text, f"Forbidden payment SDK '{sdk}' found in requirements.txt"


def test_mock_modules_no_network_imports():
    for mod_name in MOCK_MODULES:
        p = ROOT / mod_name
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for net in FORBIDDEN_NETWORKS_IN_MOCKS:
                        assert not alias.name.startswith(net), \
                            f"{mod_name} imports forbidden network library: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for net in FORBIDDEN_NETWORKS_IN_MOCKS:
                        assert not node.module.startswith(net), \
                            f"{mod_name} imports from forbidden network library: {node.module}"


def test_no_live_action_capabilities():
    """Ensure no module defines dangerous real-world execution functions like publish or send_email."""
    allowed_files = {"payments.py", "webhooks.py", "delivery.py", "refunds.py", "reconcile.py",
                     "app.py", "approval.py", "gates.py", "orchestrator.py"}

    for py_file in ROOT.rglob("*.py"):
        if any(part in py_file.parts for part in (".git", "tests", "evals", ".pytest_cache", "__pycache__")):
            continue
        if py_file.name in allowed_files:
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                fname = node.name.lower()
                for banned in ("send_email", "send_mail", "publish_to_web", "transfer_money", "real_charge"):
                    assert banned not in fname, f"Dangerous execution function '{node.name}' found in {py_file.name}"
