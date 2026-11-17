# OWNER: M1
import json
import threading

import pytest

from core.decision_log import DecisionLog
from tests.helpers import DECISION_KEYS


def test_creates_empty_array(tmp_path):
    p = tmp_path / "decision_log.json"
    DecisionLog(p)
    assert json.loads(p.read_text()) == []


def test_entry_has_all_seven_keys_and_extras(tmp_path):
    log = DecisionLog(tmp_path / "decision_log.json")
    log.action("gate", "gate_1", outcome="stop")
    e = json.loads((tmp_path / "decision_log.json").read_text())[0]
    assert all(k in e for k in DECISION_KEYS)
    assert e["outcome"] == "stop" and e["sources"] == [] and e["model"] is None and e["approved_by"] is None
    assert e["timestamp"].endswith("Z")


def test_approved_by_only_founder_or_none(tmp_path):
    log = DecisionLog(tmp_path / "d.json")
    with pytest.raises(ValueError):
        log.action("x", "y", approved_by="agent")


def test_atomic_write_leaves_no_temp_files(tmp_path):
    log = DecisionLog(tmp_path / "d.json")
    for i in range(5):
        log.action("x", f"a{i}")
    assert [p.name for p in tmp_path.iterdir()] == ["d.json"]
    assert len(json.loads((tmp_path / "d.json").read_text())) == 5


def test_concurrent_appends(tmp_path):
    log = DecisionLog(tmp_path / "d.json")
    threads = [threading.Thread(target=lambda i=i: [log.action(f"t{i}", f"a{j}") for j in range(20)])
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(json.loads((tmp_path / "d.json").read_text())) == 160
