"""Portfolio performance vs benchmark (Phase 5.5) — regression test for a real bug found live:

/api/portfolio (FastAPI) crashed with `ValueError: Out of range float values are not JSON compliant:
nan` because yfinance's most recent daily bar can be NaN (still-forming candle while the market is
open — reproduced live with VT: today's Open/High/Low/Close/Volume were all NaN). `_latest_close()`
converted that straight to a Python float without checking for NaN, so it slipped past the existing
`is None` guard in compute_edge() and reached the API's JSON response, which Starlette rejects.
Offline (mocked yfinance) so no network hit.
"""
from types import SimpleNamespace

import pytest

from src.agent.performance import _close_on_or_after, _latest_close, _health_at_entry, compute_edge

pd = pytest.importorskip("pandas")   # มากับ yfinance อยู่แล้ว


def _fake_history(closes: list[float | None]):
    """DataFrame ที่หน้าตาเหมือนที่ yf.Ticker(...).history() คืนมา — คอลัมน์ Close ตามที่ระบุ."""
    return pd.DataFrame({"Close": closes})


def test_latest_close_drops_nan_last_bar(monkeypatch):
    # เคสจริงที่เจอ: แท่งล่าสุด (วันนี้ ตลาดยังเปิดอยู่) เป็น NaN ทั้งแท่ง
    monkeypatch.setattr(
        "src.agent.performance.yf.Ticker",
        lambda t: SimpleNamespace(history=lambda **kw: _fake_history([155.8, 157.0, 157.6, 155.8, float("nan")])),
    )
    result = _latest_close("VT")
    assert result == 155.8   # ต้องหยิบแท่งจริงตัวสุดท้าย ไม่ใช่ NaN


def test_latest_close_none_when_all_bars_nan(monkeypatch):
    monkeypatch.setattr(
        "src.agent.performance.yf.Ticker",
        lambda t: SimpleNamespace(history=lambda **kw: _fake_history([float("nan")] * 5)),
    )
    assert _latest_close("VT") is None   # ไม่มีข้อมูลจริงเลย -> None (ไม่ใช่ NaN หลุดออกไป)


def test_close_on_or_after_drops_leading_nan(monkeypatch):
    # แท่งแรกในช่วงที่ขอ (วันซื้อ) เป็น NaN -> ต้องข้ามไปหยิบแท่งจริงตัวถัดไป ไม่ใช่คืน NaN
    monkeypatch.setattr(
        "src.agent.performance.yf.Ticker",
        lambda t: SimpleNamespace(history=lambda **kw: _fake_history([float("nan"), 154.5, 153.2])),
    )
    result = _close_on_or_after("VT", "2026-05-06")
    assert result == 154.5


def test_close_on_or_after_none_when_history_empty(monkeypatch):
    monkeypatch.setattr(
        "src.agent.performance.yf.Ticker",
        lambda t: SimpleNamespace(history=lambda **kw: _fake_history([])),
    )
    assert _close_on_or_after("VT", "2026-05-06") is None


def test_latest_close_none_on_exception(monkeypatch):
    def _raise(t):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.agent.performance.yf.Ticker", _raise)
    assert _latest_close("VT") is None   # ล้มเงียบๆ ไม่ raise (กัน report ทั้งฉบับพัง)


# --- _health_at_entry (Phase 20.3) — point-in-time health ณ วันซื้อ, ไม่ใช่คะแนนปัจจุบัน ---
# history() คืนเรียงใหม่->เก่า (run_at DESC) เหมือนของจริง

def _row(run_at, health_score):
    return {"run_at": run_at, "health_score": health_score}


def test_health_at_entry_exact_when_analysis_exists_before_entry(monkeypatch):
    # มีรอบวิเคราะห์ก่อน/วันเดียวกับวันซื้อ -> ใช้ตัวล่าสุดในกลุ่มนั้น (exact=True)
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [
        _row("2026-06-01T10:00:00", 9.0),
        _row("2026-05-10T10:00:00", 8.5),   # ใกล้ entry_date ที่สุดฝั่งก่อนหน้า -> ต้องเลือกตัวนี้
        _row("2026-04-01T10:00:00", 7.0),
    ])
    score, exact = _health_at_entry("DUOL", "2026-05-15")
    assert (score, exact) == (8.5, True)


def test_health_at_entry_exact_same_day_as_entry(monkeypatch):
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [
        _row("2026-05-06T10:00:00", 8.0),
    ])
    score, exact = _health_at_entry("DUOL", "2026-05-06")
    assert (score, exact) == (8.0, True)


def test_health_at_entry_fallback_when_no_analysis_before_entry(monkeypatch):
    # เคสจริงที่เจอ: DUOL ซื้อ 2026-05-06 แต่ analysis เก่าสุดในระบบเริ่ม 2026-07-07 (หลังซื้อ 2 เดือน)
    # -> ต้อง fallback ไปตัวเก่าสุดที่มี พร้อมบอกว่าเป็นค่าประมาณ (exact=False) ห้ามอ้างว่าคือคะแนนจริง
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [
        _row("2026-07-10T10:00:00", 8.3),
        _row("2026-07-07T18:26:45", 8.0),   # เก่าสุดที่มี -> fallback ต้องเลือกตัวนี้ (ใกล้สุดฝั่งหลัง)
    ])
    score, exact = _health_at_entry("DUOL", "2026-05-06")
    assert (score, exact) == (8.0, False)


def test_health_at_entry_none_when_no_health_scores_at_all(monkeypatch):
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [
        _row("2026-07-10T10:00:00", None),
    ])
    assert _health_at_entry("DUOL", "2026-05-06") == (None, False)


def test_health_at_entry_none_when_no_rows(monkeypatch):
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [])
    assert _health_at_entry("DUOL", "2026-05-06") == (None, False)


# --- compute_edge end-to-end includes entry_health/entry_health_exact ---

def test_compute_edge_includes_entry_health(monkeypatch):
    monkeypatch.setattr("src.agent.performance.get_entry", lambda t: {
        "status": "holding", "entry_price": 100.0, "entry_date": "2026-05-06", "shares": 2.0,
    })
    monkeypatch.setattr("src.agent.performance.get_benchmark", lambda: "VT")
    monkeypatch.setattr("src.agent.performance.history", lambda ticker, limit=500: [
        _row("2026-05-01T10:00:00", 7.5),
    ])
    monkeypatch.setattr(
        "src.agent.performance.yf.Ticker",
        lambda t: SimpleNamespace(history=lambda **kw: _fake_history([130.0])),
    )
    result = compute_edge("DUOL")
    assert result is not None
    assert result["entry_health"] == 7.5
    assert result["entry_health_exact"] is True
