from dataclasses import dataclass

from src.agent.valuation import (
    intrinsic_value,
    implied_growth_rate,
    capm_wacc,
    reinvestment_rate,
    sustainable_growth_rate,
    valuation_guard,
    growth_lens_realistic,
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


# --- reinvestment_rate (แยกจาก sustainable_growth_rate เพื่อทดสอบ sign-flip ตรงๆ) ---

def test_reinvestment_rate_deferred_revenue_can_go_negative():
    # เหมือน DUOL จริง: nwc_change เป็นบวกมาก (ลูกค้าจ่ายล่วงหน้า = เงินสดไหลเข้าจาก NWC)
    # -> real_nwc_increase ติดลบมาก -> reinvestment ติดลบได้ทั้งที่ capex/da ปกติ
    rr = reinvestment_rate(capex=-27_399_000, da=14_391_000, nwc_change=48_966_000, nopat=307_739_663.67)
    assert rr is not None
    assert rr < 0


def test_reinvestment_rate_none_when_missing():
    assert reinvestment_rate(None, 10, -5, 100) is None
    assert reinvestment_rate(-10, 10, -5, 0) is None


# --- valuation_guard: 4 เคสจาก valuation_guard_growth_lens.md ---

def test_valuation_guard_case1_duol_like_asset_light_routes_to_growth():
    # rev growth สูง, asset-light + deferred revenue สูง (ΔNWC บวกมาก) -> reinvestment ติดลบ
    # + sustainable ขัดแย้งกับ CAGR จริงมหาศาล -> ต้อง route 'growth'
    route, flags, sustainable = valuation_guard(
        fcf_base=254_909_000.0, nopat=307_739_663.67, revenue=1_037_589_000.0,
        capex=-27_399_000, da=14_391_000, nwc_change=48_966_000, roic_pct=76.1,
        historical_cagr=41.08,
    )
    assert route == "growth"
    assert "NEGATIVE_REINVESTMENT" in flags
    assert "SUSTAINABLE_DIVERGES" in flags
    assert sustainable is not None and sustainable < 0   # sustainable เพี้ยนติดลบ (เหตุผลที่ห้ามใช้ตรงๆ)


def test_valuation_guard_case2_standard_value_stock_routes_to_standard():
    # หุ้น value โตช้า, reinvestment บวกปกติ, sustainable ใกล้เคียง CAGR จริง -> ไม่ trip flag ไหนเลย
    route, flags, sustainable = valuation_guard(
        fcf_base=100.0, nopat=1000.0, revenue=5000.0,
        capex=-250, da=50, nwc_change=0, roic_pct=25.0,
        historical_cagr=5.0,   # sustainable = (200/1000)*25 = 5.0 ตรงกับ CAGR เป๊ะ
    )
    assert route == "standard"
    assert flags == []
    assert abs(sustainable - 5.0) < 1e-6


def test_valuation_guard_case3_loss_making_returns_na():
    route, flags, sustainable = valuation_guard(
        fcf_base=-50.0, nopat=None, revenue=None, capex=None, da=None, nwc_change=None,
        roic_pct=None, historical_cagr=5.0,
    )
    assert route == "NA"
    assert flags == ["FCF_NONPOSITIVE"]
    assert sustainable is None


def test_valuation_guard_case4_thin_nopat_margin_routes_to_growth():
    # เพิ่งพลิกกำไร: NOPAT บวกนิดเดียวเทียบ revenue (margin < MIN_NOPAT_MARGIN=2%) -> ไม่เชื่อ ratio
    route, flags, sustainable = valuation_guard(
        fcf_base=100.0, nopat=10.0, revenue=10_000.0,   # margin = 0.1% << 2%
        capex=-50, da=20, nwc_change=-5, roic_pct=15.0, historical_cagr=8.0,
    )
    assert route == "growth"
    assert "NOPAT_UNSTABLE" in flags


# --- growth_lens_realistic ---

def test_growth_lens_realistic_caps_initial_growth():
    # rev_growth_recent 60% (เกิน CAP_INITIAL_GROWTH=35%) -> ต้อง cap ที่ 35% ก่อน fade
    capped = growth_lens_realistic(60.0, terminal_growth=0.025, years=10)
    uncapped_would_be = growth_lens_realistic(35.0, terminal_growth=0.025, years=10)
    assert capped == uncapped_would_be   # 60% กับ 35% ต้องให้ผลเหมือนกันเป๊ะ (โดน cap ที่ระดับเดียวกัน)


def test_growth_lens_realistic_between_initial_and_terminal():
    # g0=10%, terminal=2.5% -> ผลลัพธ์ต้องอยู่ระหว่างสองค่านี้ (fade เฉลี่ยถ่วงเวลา)
    result = growth_lens_realistic(10.0, terminal_growth=0.025, years=10)
    assert 2.5 < result < 10.0


def test_growth_lens_realistic_never_negative_for_positive_recent_growth():
    # ต่างจาก sustainable_growth ที่ติดลบมั่วได้ — growth lens ต้องไม่ติดลบถ้า recent growth เป็นบวก
    result = growth_lens_realistic(40.0, terminal_growth=0.025, years=10)
    assert result > 0


# --- _rev_growth_recent: bug จริงที่เจอ — health.py ประกอบ revenue_series เก่า->ใหม่ (ascending)
# แต่ StockFundamentals.revenue_series ดิบเป็นใหม่->เก่า (descending) — ต้องถูกต้องทั้ง 2 แบบ ---

def test_rev_growth_recent_correct_with_newest_first_order():
    # เหมือน StockFundamentals.revenue_series ดิบ (จาก fundamentals.py)
    series = [("FY2025", 1_037_589_000.0), ("FY2024", 748_024_000.0), ("FY2023", 531_109_000.0)]
    from src.agent.valuation import _rev_growth_recent
    g = _rev_growth_recent(series)
    assert g is not None and g > 0   # FY2025 vs FY2024 ต้องเป็นบวก (โตจริง)


def test_rev_growth_recent_correct_with_oldest_first_order():
    # เหมือน health.py::_fy_series() ที่ sort เก่า->ใหม่ ตอนประกอบ duck object จาก facts
    series = [("FY2023", 531_109_000.0), ("FY2024", 748_024_000.0), ("FY2025", 1_037_589_000.0)]
    from src.agent.valuation import _rev_growth_recent
    g = _rev_growth_recent(series)
    assert g is not None and g > 0   # ต้องได้ผลเดียวกับ newest-first — ไม่ใช่ติดลบจากหยิบผิดปี


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
    revenue: float | None = None
    revenue_series: list = None
    fcf_margin: float | None = None


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


def test_reverse_dcf_routes_to_growth_lens_when_sustainable_diverges():
    # reinvestment_rate สูง (capex ใหญ่เทียบ NOPAT เล็ก) + ROIC สูงมาก (คล้าย AAPL จริง ~80%)
    # -> sustainable growth ชนเพดาน 20% ห่างจาก historical CAGR (1%) เกิน DIVERGENCE_TRIGGER_PP มาก
    f = FakeFundamentals(
        free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=1.0,
        capex=-30, depreciation_amortization=10, nwc_change=-5, nopat=50, roic=80.0,
    )
    result = reverse_dcf(f)
    assert result["lens"] == "growth"
    assert "SUSTAINABLE_DIVERGES" in result["flags"]


def test_reverse_dcf_duol_like_case_no_longer_shows_negative_realistic_growth():
    # เคสจริงที่พัง (valuation_guard_growth_lens.md): DUOL asset-light + deferred revenue
    # ทำให้ sustainable_growth ติดลบทั้งที่บริษัทโตจริง 41%/ปี -> ต้องไม่เห็น realistic_growth
    # ติดลบอีกต่อไป (route ไป growth lens แทน)
    f = FakeFundamentals(
        free_cash_flow=254_909_000.0, market_cap=5_812_957_184.0, revenue_cagr=41.08,
        beta=0.88, net_debt=-942_610_000.0,
        capex=-27_399_000, depreciation_amortization=14_391_000, nwc_change=48_966_000,
        nopat=307_739_663.67, roic=76.1, revenue=1_037_589_000.0,
        revenue_series=[("FY2025", 1_037_589_000.0), ("FY2024", 748_024_000.0)],
        fcf_margin=24.57,
    )
    result = reverse_dcf(f, risk_free_pct=4.57)
    assert result["lens"] == "growth"
    assert result["realistic_growth"] > 0   # เดิมได้ -8.89, ตอนนี้ต้องเป็นบวก (บริษัทโตจริง)
    assert result["score"] >= 2             # gap ควรติดลบ/เล็ก -> คะแนนดี ไม่ใช่ 0 (แพงมาก) เหมือนเดิม


def test_reverse_dcf_score_step_bands():
    # gap < 0 -> 3, 0<=gap<5 -> 2, 5<=gap<10 -> 1, gap>=10 -> 0
    # บังคับ lens='standard' ด้วย reinvestment/ROIC ที่ sustainable ตรงกับ revenue_cagr เป๊ะ (5.0%)
    # กัน growth-lens fade มาบิด realistic_growth จนเทียบ band ตรงๆ ไม่ได้
    fcf = 100.0
    for target_growth, expected_score in [(-0.05, 3), (0.06, 2), (0.12, 1), (0.20, 0)]:
        ev = intrinsic_value(fcf, target_growth, 0.0925, 0.025, 10)
        f = FakeFundamentals(
            free_cash_flow=fcf, market_cap=ev, revenue_cagr=5.0,
            capex=-250, depreciation_amortization=50, nwc_change=0, nopat=1000.0, roic=25.0,
        )
        result = reverse_dcf(f, risk_free_pct=4.0)
        assert result["lens"] == "standard", f"expected standard lens, got {result['lens']} flags={result['flags']}"
        assert result["score"] == expected_score, f"growth={target_growth}: gap={result['gap']}, score={result['score']}"


def test_reverse_dcf_serializable_dict():
    import json
    f = FakeFundamentals(free_cash_flow=100.0, market_cap=2000.0, revenue_cagr=5.0)
    result = reverse_dcf(f)
    json.dumps(result)   # ไม่ raise = pass