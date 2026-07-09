"""Phase 4 eval + regression: extraction accuracy ต้องเป็น native bool/serializable.

บั๊กจริงที่หลุด: _ratio_series ปล่อยค่าเป็น numpy.float64 -> เทียบ <= ได้ numpy.bool_
ซึ่งไม่ใช่ subclass ของ bool -> json.dumps() พังตอน save ลง DB ("Object of type bool
is not JSON serializable"). test นี้ยืนยันว่าผลของ _within_tolerance เป็น bool แท้และ
ผลรวมทั้ง dict serialize ได้ + เป็น golden headline accuracy แบบ offline (ไม่แตะ network).
"""
import json
from types import SimpleNamespace

import pytest

from src.evals.check_extraction_accuracy import _within_tolerance, check_extraction_accuracy


def test_within_tolerance_returns_native_bool():
    r = _within_tolerance(10.0, 10.1)
    assert type(r) is bool          # ไม่ใช่ numpy.bool_
    json.dumps(r)                   # ต้อง serialize ได้


def test_within_tolerance_handles_numpy_scalars():
    np = pytest.importorskip("numpy")   # numpy มากับ yfinance อยู่แล้ว
    r = _within_tolerance(np.float64(31.9), np.float64(32.0))
    assert type(r) is bool
    json.dumps(r)


def test_within_tolerance_boundaries():
    # ต่างกัน 4 pp < TOLERANCE_ABS (5.0) -> ผ่าน
    assert _within_tolerance(30.0, 34.0) is True
    # ต่างกันมากเกินทั้ง abs และ rel -> ไม่ผ่าน (จับสูตรผิด/สลับเครื่องหมาย)
    assert _within_tolerance(30.0, -30.0) is False


def _fake_fundamentals():
    """ค่าที่ 'เราคำนวณเอง' — ตรงกับ fake info (ควรผ่าน tolerance ทุกตัว)."""
    return SimpleNamespace(
        roe=150.0, current_ratio=0.87,
        gross_margin_series=[("FY2025", 46.9)],
        operating_margin_series=[("FY2025", 31.5)],
        net_margin_series=[("FY2025", 26.9)],
    )


def test_check_extraction_accuracy_golden(monkeypatch):
    """golden: fundamentals ของเรา vs info ที่ freeze ไว้ -> accuracy 100% + serializable."""
    fake_info = {
        "returnOnEquity": 1.50, "currentRatio": 0.87,
        "grossMargins": 0.469, "operatingMargins": 0.315, "profitMargins": 0.269,
    }
    monkeypatch.setattr(
        "src.evals.check_extraction_accuracy.yf.Ticker",
        lambda t: SimpleNamespace(info=fake_info),
    )
    result = check_extraction_accuracy(_fake_fundamentals(), "AAPL")

    assert result["accuracy"] == 1.0
    assert len(result["checks"]) == 5
    assert all(c["within_tolerance"] for c in result["checks"])
    json.dumps(result)   # ทั้งก้อนต้อง serialize ได้ (นี่คือสิ่งที่ save_analysis ทำ)


def test_check_extraction_accuracy_flags_mismatch(monkeypatch):
    """ถ้า 'การคำนวณของเรา' เพี้ยนหนัก (เช่น ROE ผิดสูตร) accuracy ต้องต่ำลง."""
    fake_info = {
        "returnOnEquity": 1.50, "currentRatio": 0.87,
        "grossMargins": 0.469, "operatingMargins": 0.315, "profitMargins": 0.269,
    }
    monkeypatch.setattr(
        "src.evals.check_extraction_accuracy.yf.Ticker",
        lambda t: SimpleNamespace(info=fake_info),
    )
    fund = _fake_fundamentals()
    fund.roe = -5.0   # ผิดชัดเจน (จริง 150) -> ตัวนี้ต้อง fail tolerance
    result = check_extraction_accuracy(fund, "AAPL")

    assert result["accuracy"] < 1.0
    roe_check = next(c for c in result["checks"] if c["metric"] == "roe")
    assert roe_check["within_tolerance"] is False
