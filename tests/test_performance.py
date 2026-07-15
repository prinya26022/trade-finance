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

from src.agent.performance import _close_on_or_after, _latest_close

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
