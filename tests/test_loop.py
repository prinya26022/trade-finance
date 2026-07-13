"""_due_for_analysis (Phase: frozen-ticker monthly cadence) — pure logic, mock history()
เพื่อไม่แตะ DB จริง. analyze()/run_watchlist() เองยิง Gemini/yfinance จริง จึงไม่มี unit test
ตรงๆ (ทดสอบผ่าน live smoke test แทนตามธรรมเนียมโปรเจกต์นี้)."""
from datetime import datetime, timedelta
from unittest.mock import patch

from src.agent.loop import _due_for_analysis, FROZEN_INTERVAL_DAYS


def test_watching_always_due():
    with patch("src.agent.loop.history", return_value=[]) as h:
        assert _due_for_analysis("AAPL", "watching") is True
        h.assert_not_called()   # ไม่ควรแม้แต่เช็ค history — watching ไม่มีเงื่อนไข


def test_holding_always_due():
    assert _due_for_analysis("DUOL", "holding") is True


def test_frozen_due_when_never_analyzed():
    with patch("src.agent.loop.history", return_value=[]):
        assert _due_for_analysis("SBUX", "frozen") is True


def test_frozen_not_due_when_recent():
    recent = (datetime.now() - timedelta(days=5)).isoformat(timespec="seconds")
    with patch("src.agent.loop.history", return_value=[{"run_at": recent}]):
        assert _due_for_analysis("SBUX", "frozen") is False


def test_frozen_due_when_past_interval():
    old = (datetime.now() - timedelta(days=FROZEN_INTERVAL_DAYS + 1)).isoformat(timespec="seconds")
    with patch("src.agent.loop.history", return_value=[{"run_at": old}]):
        assert _due_for_analysis("SBUX", "frozen") is True


def test_frozen_exactly_at_boundary_is_due():
    boundary = (datetime.now() - timedelta(days=FROZEN_INTERVAL_DAYS)).isoformat(timespec="seconds")
    with patch("src.agent.loop.history", return_value=[{"run_at": boundary}]):
        assert _due_for_analysis("SBUX", "frozen") is True