"""แปลงสกุลเงินให้ ADR ต่างชาติ (Phase 45). Offline ล้วน — ไม่ยิง yfinance.

Phase 33 ปฏิเสธหุ้นที่งบกับราคาคนละสกุลทั้งชุด ซึ่งถูกต้องในตอนนั้น (ตัวเลขที่ผิดแบบดูน่าเชื่อ
แย่กว่าไม่มีตัวเลข) แต่ผลข้างเคียงคือ **ธุรกิจที่คะแนนพื้นฐานสูงสุดสองอันดับแรกของ watchlist
(ASML 7.90/8, TSM 7.50/8) ไม่มีคำตอบด้านราคาเลย** ด้วยเหตุผลที่ไม่เกี่ยวกับตัวธุรกิจ
"""
import pytest

from src.agent.health import _build_duck_fundamentals, no_valuation_reason
from src.providers.stock.fundamentals import StockFundamentals


def _f(**kw):
    return StockFundamentals(market_cap=1000.0, financial_currency="EUR",
                             price_currency="USD", **kw)


# ---------- แปลงตัวเดียว: market cap ----------

def test_only_the_market_cap_needs_converting():
    """net debt / FCF / รายได้ เป็นสกุลงบอยู่แล้ว เอา market cap เข้าไปอยู่ในสกุลเดียวกัน
    แล้ว reverse-DCF ทั้งเส้นก็ทำงานในสกุลเดียว ผลลัพธ์ที่ออกมาไม่มีหน่วยเงินอยู่แล้ว."""
    assert _f(fx_rate=0.8631).market_cap_stmt == pytest.approx(863.1)


def test_same_currency_passes_through_untouched():
    same = StockFundamentals(market_cap=1000.0, financial_currency="USD", price_currency="USD")

    assert same.currency_mismatch is False
    assert same.market_cap_stmt == 1000.0


def test_no_rate_means_no_answer_rather_than_a_guessed_one():
    """เดาเรตแล้วให้คะแนนออกมา = สร้างตัวเลขผิดที่ดูน่าเชื่อ ซึ่งเป็นสิ่งเดียวกับที่ Phase 33
    ปฏิเสธไปแล้ว ต่างกันแค่ผิดที่เรตแทนที่จะผิดที่สกุล."""
    assert _f().market_cap_stmt is None
    assert _f(fx_rate=0.0).market_cap_stmt is None


def test_no_market_cap_means_nothing_to_convert():
    assert StockFundamentals(financial_currency="EUR", price_currency="USD",
                             fx_rate=0.86).market_cap_stmt is None


# ---------- เรตต้องติดไปกับ facts (point-in-time) ----------

def test_the_rate_actually_used_is_stored_as_a_fact():
    """ไม่เก็บ = การคำนวณย้อนหลังจะหยิบเรตวันนี้ไปใช้กับแถวปีที่แล้วเงียบๆ ซึ่งเป็นบั๊ก
    ตระกูลเดียวกับที่ Phase 32 (anchor สลับฐานเงียบๆ) และ 36 (หน้าต่างเปลี่ยนความหมาย) เจอ."""
    facts = {f.label: f for f in _f(fx_rate=0.8631).to_facts()}

    assert facts["FX Rate"].value == 0.8631
    assert facts["FX Rate"].unit == "USD->EUR"      # ป้ายบอกทิศทาง ไม่ต้องเดา
    assert facts["Market Cap (สกุลงบ)"].value == pytest.approx(863.1)
    assert facts["Market Cap (สกุลงบ)"].unit == "EUR"


def test_a_same_currency_company_gets_no_conversion_facts_at_all():
    """หุ้น US ปกติต้องไม่มี Fact เกินมา — ไม่งั้นทุกแถวจะพองขึ้นเพื่อรองรับเคสส่วนน้อย."""
    labels = {f.label for f in StockFundamentals(
        market_cap=1000.0, financial_currency="USD", price_currency="USD").to_facts()}

    assert "FX Rate" not in labels
    assert "Market Cap (สกุลงบ)" not in labels


# ---------- ฝั่งที่อ่าน facts กลับมาใช้ ----------

_CROSS = [
    {"label": "Market Cap", "value": 1000.0, "unit": "USD", "period": "FY2025"},
    {"label": "Revenue", "value": 400.0, "unit": "EUR", "period": "TTM"},
    {"label": "Net Debt", "value": -50.0, "unit": "EUR", "period": "FY2025"},
]


def test_the_duck_object_uses_the_converted_cap_and_stops_reporting_a_mismatch():
    facts = _CROSS + [
        {"label": "FX Rate", "value": 0.8631, "unit": "USD->EUR", "period": "FY2025"},
        {"label": "Market Cap (สกุลงบ)", "value": 863.1, "unit": "EUR", "period": "FY2025"},
    ]

    duck = _build_duck_fundamentals(facts)

    assert duck.currency_mismatch is False
    assert duck.market_cap == pytest.approx(863.1)


def test_rows_recorded_before_this_phase_behave_exactly_as_before():
    """แถวเก่าไม่มี Fact เรต -> ยังถูกปฏิเสธเหมือนเดิม. ประวัติที่บันทึกไว้แล้วต้องไม่ถูก
    เขียนใหม่ย้อนหลังด้วยเรตวันนี้ ซึ่งเป็นทั้งเรื่องความถูกต้องและเรื่องความซื่อสัตย์."""
    duck = _build_duck_fundamentals(_CROSS)

    assert duck.currency_mismatch is True
    assert duck.market_cap == 1000.0        # ค่าดิบเดิม ไม่ถูกแตะ


def test_a_surviving_mismatch_is_reported_as_a_fetch_problem_now():
    """แปลงได้แล้วถ้าดึงเรตสำเร็จ ดังนั้นที่ยังเหลือ mismatch = ดึงเรตไม่ได้รอบนั้น =
    รอบหน้าอาจหายเอง ผู้ใช้ควรเมินรอบนี้ ไม่ใช่เอาไปสรุปเรื่องบริษัท."""
    reason, data_gap = no_valuation_reason(_build_duck_fundamentals(_CROSS))

    assert data_gap is True
    assert "อัตราแลกเปลี่ยน" in reason and "รอบวิเคราะห์ถัดไป" in reason
