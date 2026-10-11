"""decision journal (Phase 27) — จดการตัดสินใจซื้อ/ผ่าน รวมถึงจดย้อนหลังวันที่ตัดสินใจจริง."""
import pytest

from src.decisions.store import list_decisions, log_decision


def test_log_and_list_newest_first(tmp_db):
    log_decision("duol", "buy", price=99.63, gate2="ready", decided_at="2026-05-06")
    log_decision("DUOL", "wait", price=150.0)
    rows = list_decisions("DUOL")
    assert [r["action"] for r in rows] == ["wait", "buy"]
    assert rows[1]["ticker"] == "DUOL" and rows[1]["decided_at"] == "2026-05-06T00:00:00"


def test_backdated_decision_cannot_be_in_the_future(tmp_db):
    with pytest.raises(ValueError):
        log_decision("DUOL", "buy", decided_at="2999-01-01")


def test_bad_date_or_action_is_rejected(tmp_db):
    with pytest.raises(ValueError):
        log_decision("DUOL", "buy", decided_at="6 May")
    with pytest.raises(ValueError):
        log_decision("DUOL", "hold")
    assert list_decisions("DUOL") == []
