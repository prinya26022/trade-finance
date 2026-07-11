from dataclasses import dataclass

from src.agent.valuation import (
    intrinsic_equity_value,
    implied_growth_rate,
    reverse_dcf,
)


def test_intrinsic_value_monotonic_in_growth():
    low = intrinsic_equity_value(100, 0.05, 0.09, 0.025, 10)
    high = intrinsic_equity_value(100, 0.20, 0.09, 0.025, 10)
    assert high > low


def test_implied_growth_recovers_known_growth():
    # สร้าง market_cap จาก growth ที่รู้อยู่แล้ว (15%) แล้วแก้ย้อนกลับต้องได้ ~15% คืนมา
    known_growth = 0.15
    fcf = 100.0
    market_cap = intrinsic_equity_value(fcf, known_growth, 0.09, 0.025, 10)
    implied = implied_growth_rate(market_cap, fcf, 0.09, 0.025, 10)
    assert implied is not None
    assert abs(implied - known_growth * 100) < 0.1


def test_implied_growth_none_when_discount_below_terminal():
    assert implied_growth_rate(1000, 100, discount_rate=0.02, terminal_growth=0.025) is None


def test_implied_growth_none_when_market_cap_out_of_range():
    # market cap เท่ากับ fcf เป๊ะๆ (แทบไม่มี multiple เลย) ต่ำกว่าแม้ growth -30% ตลอด 10 ปี
    assert implied_growth_rate(1.0, 100.0) is None


@dataclass
class FakeFundamentals:
    free_cash_flow: float | None
    market_cap: float | None
    revenue_cagr: float | None


def test_reverse_dcf_none_when_missing_inputs():
    assert reverse_dcf(FakeFundamentals(None, 1000.0, 10.0)) is None
    assert reverse_dcf(FakeFundamentals(100.0, None, 10.0)) is None


def test_reverse_dcf_negative_fcf_returns_note_not_none():
    result = reverse_dcf(FakeFundamentals(-50.0, 1000.0, 10.0))
    assert result is not None
    assert result["implied_growth"] is None
    assert "burn cash" in result["note"]


def test_reverse_dcf_computes_gap_vs_historical():
    fcf = 100.0
    market_cap = intrinsic_equity_value(fcf, 0.20, 0.09, 0.025, 10)
    result = reverse_dcf(FakeFundamentals(fcf, market_cap, historical_growth_stub := 8.0))
    assert result["implied_growth"] is not None
    assert result["historical_cagr"] == 8.0
    assert result["gap"] == round(result["implied_growth"] - 8.0, 2)


def test_reverse_dcf_serializable_dict():
    import json

    fcf = 100.0
    market_cap = intrinsic_equity_value(fcf, 0.10, 0.09, 0.025, 10)
    result = reverse_dcf(FakeFundamentals(fcf, market_cap, 5.0))
    json.dumps(result)  # ไม่ raise = pass