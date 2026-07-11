from dataclasses import dataclass

from src.agent.valuation import (
    intrinsic_value,
    implied_growth_rate,
    capm_wacc,
    sustainable_growth_rate,
    reverse_dcf,
    BETA_FLOOR,
    BETA_CAP,
)


def test_intrinsic_value_monotonic_in_growth():
    low = intrinsic_value(100, 0.05, 0.09, 0.025, 10)
    high = intrinsic_value(100, 0.20, 0.09, 0.025, 10)
    assert high > low


def test_implied_growth_recovers_known_growth():
    # สร้าง target_value จาก growth ที่รู้อยู่แล้ว (15%) แล้วแก้ย้อนกลับต้องได้ ~15% คืนมา
    known_growth = 0.15
    fcf = 100.0
    target = intrinsic_value(fcf, known_growth, 0.09, 0.025, 10)
    implied = implied_growth_rate(target, fcf, 0.09, 0.025, 10)
    assert implied is not None
    assert abs(implied - known_growth * 100) < 0.1


def test_implied_growth_none_when_discount_below_terminal():
    assert implied_growth_rate(1000, 100, discount_rate=0.02, terminal_growth=0.025) is None


def test_implied_growth_none_when_target_out_of_range():
    # target เท่ากับ fcf เป๊ะๆ (แทบไม่มี multiple เลย) ต่ำกว่าแม้ growth -30% ตลอด 10 ปี
    assert implied_growth_rate(1.0, 100.0, discount_rate=0.09, terminal_growth=0.025) is None


# --- CAPM WACC ---

def test_capm_wacc_basic():
    # Rf=4%, beta=1.0, ERP=5.25% -> WACC = 4% + 1.0*5.25% = 9.25%
    w = capm_wacc(1.0, risk_free_pct=4.0, erp=0.0525)
    assert abs(w - 0.0925) < 1e-9


def test_capm_wacc_clamps_beta_floor_and_cap():
    low = capm_wacc(0.1, risk_free_pct=4.0, erp=0.0525)   # ต่ำกว่า floor -> ใช้ BETA_FLOOR
    at_floor = capm_wacc(BETA_FLOOR, risk_free_pct=4.0, erp=0.0525)
    assert abs(low - at_floor) < 1e-9

    high = capm_wacc(5.0, risk_free_pct=4.0, erp=0.0525)  # เกิน cap -> ใช้ BETA_CAP
    at_cap = capm_wacc(BETA_CAP, risk_free_pct=4.0, erp=0.0525)
    assert abs(high - at_cap) < 1e-9


def test_capm_wacc_defaults_beta_to_one_when_missing():
    assert abs(capm_wacc(None, risk_free_pct=4.0, erp=0.0525) - capm_wacc(1.0, risk_free_pct=4.0, erp=0.0525)) < 1e-9


# --- sustainable growth ---

def test_sustainable_growth_rate_basic():
    # capex=-100 (ไหลออก), da=40, nwc_change=-10 (NWC เพิ่ม 10), nopat=500, roic=20%
    # real_capex=100, real_nwc_increase=10 -> reinvestment=(100-40+10)/500=0.14 -> sg=0.14*0.20=0.028
    sg = sustainable_growth_rate(capex=-100, da=40, nwc_change=-10, nopat=500, roic_pct=20.0)
    assert sg is not None
    assert abs(sg - 0.028) < 1e-9


def test_sustainable_growth_rate_none_when_input_missing():
    assert sustainable_growth_rate(None, 40, -10, 500, 20.0) is None
    assert sustainable_growth_rate(-100, 40, -10, 0, 20.0) is None   # nopat=0 -> หารไม่ได้


# --- reverse_dcf end-to-end ---

@dataclass
class FakeFundamentals:
    free_cash_flow: float | None
    market_cap: float | None
    revenue_cagr: float | None
    fcf_series: list = None
    net_debt: float | None = None
    beta: float | None = None
    capex: float | None = None
    depreciation_amortization: float | None = None
    nwc_change: float | None = None
    nopat: float | None = None
    roic: float | None = None


def test_reverse_dcf_none_when_missing_market_cap():
    assert reverse_dcf(FakeFundamentals(100.0, None, 10.0)) is None


def test_reverse_dcf_uses_3yr_fcf_average_not_ttm():
    f = FakeFundamentals(
        free_cash_flow=999.0,   # ตัวนี้ต้อง "ไม่ถูกใช้" เพราะมี fcf_series ให้แล้ว
        market_cap=2000.0, revenue_cagr=5.0,
        fcf_series=[("FY2025", 120.0), ("FY2024", 100.0), ("FY2023", 80.0), ("FY2022", 1.0)],
    )
    result = reverse_dcf(f)
    assert result["fcf_base"] == (120.0 + 100.0 + 80.0) / 3   # เฉลี่ย 3 ปีล่าสุด ไม่รวม FY2022


def test_reverse_dcf_falls_back_to_ttm_fcf_when_no_series():
    f = FakeFundamentals(free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=5.0, fcf_series=[])
    result = reverse_dcf(f)
    assert result["fcf_base"] == 100.0


def test_reverse_dcf_ev_includes_net_debt():
    f = FakeFundamentals(free_cash_flow=100.0, market_cap=1000.0, revenue_cagr=5.0, net_debt=200.0)
    result = reverse_dcf(f)
    assert result["ev"] == 1200.0


def test_reverse_dcf_negative_fcf_base_returns_note_not_crash():
    f = FakeFundamentals(free_cash_flow=-50.0, market_cap=1000.0, revenue_cagr=5.0)
    result = reverse_dcf(f)
    assert result is not None
    assert result["implied_growth"] is None
    assert result["score"] is None
    assert "burn cash" in result["note"]


def test_reverse_dcf_prefers_sustainable_growth_over_raw_cagr():
    # sustainable growth (จาก reinvestment×ROIC) ต้องถูกใช้เป็น realistic_growth แทน raw CAGR
    f = FakeFundamentals(
        free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=2.0,   # raw CAGR ต่ำ
        capex=-30, depreciation_amortization=10, nwc_change=-5, nopat=200, roic=25.0,
    )
    result = reverse_dcf(f)
    assert result["historical_cagr"] == 2.0
    assert result["realistic_growth"] != 2.0   # ต้องไม่ใช่ raw CAGR ตรงๆ (มี sustainable growth คำนวณได้)


def test_reverse_dcf_flags_divergence_between_sustainable_and_cagr():
    # reinvestment_rate สูง (capex ใหญ่เทียบ NOPAT เล็ก) + ROIC สูงมาก (คล้าย AAPL จริง ~80%)
    # -> sustainable growth ชนเพดาน 20% ห่างจาก historical CAGR (1%) เกิน DIVERGENCE_FLAG_PP มาก
    f = FakeFundamentals(
        free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=1.0,
        capex=-30, depreciation_amortization=10, nwc_change=-5, nopat=50, roic=80.0,
    )
    result = reverse_dcf(f)
    assert result["divergence_flag"] is not None


def test_reverse_dcf_score_step_bands():
    # gap < 0 -> 3, 0<=gap<5 -> 2, 5<=gap<10 -> 1, gap>=10 -> 0
    # ควบคุม gap ผ่าน market_cap ที่สอดคล้องกับ growth ที่รู้ค่า เทียบ realistic_growth คงที่ (ไม่มี sustainable data -> fallback ไป raw CAGR)
    fcf = 100.0
    for target_growth, expected_score in [(-0.05, 3), (0.06, 2), (0.12, 1), (0.20, 0)]:
        # realistic_growth = revenue_cagr (fallback, ไม่มีข้อมูล sustainable) = 5.0%
        ev = intrinsic_value(fcf, target_growth, 0.0925, 0.025, 10)
        f = FakeFundamentals(free_cash_flow=fcf, market_cap=ev, revenue_cagr=5.0)
        result = reverse_dcf(f, risk_free_pct=4.0)
        assert result["score"] == expected_score, f"growth={target_growth}: gap={result['gap']}, score={result['score']}"


def test_reverse_dcf_serializable_dict():
    import json
    f = FakeFundamentals(free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=5.0)
    result = reverse_dcf(f)
    json.dumps(result)   # ไม่ raise = pass