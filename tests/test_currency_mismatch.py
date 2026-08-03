"""ADR ต่างชาติ: งบสกุลบ้านเกิด ราคาสกุลที่ซื้อขาย (ASML EUR/USD, TSM TWD/USD).

เจอจริง 2026-08 ตอนวิเคราะห์เทียบสองโมเดล — ทั้งระบบเคยสมมติเงียบๆ ว่าทุกอย่างเป็น USD:
- ป้ายหน่วยบอกว่า TSM มีรายได้ 4.44e12 **USD** (จริงคือ TWD)
- P/S 0.47x, P/B 84.3x, EV/EBITDA, FCF Yield 35.25% = เอาราคาหารงบข้ามสกุล
- reverse-DCF บวก market_cap (USD) กับ net_debt (TWD) เป็น EV แล้วให้คะแนนขาราคาไปเต็มๆ
  (ASML ได้ 0.0/3 จากตัวเลขที่ไม่มีความหมาย; TSM รอดเพราะผลลัพธ์บังเอิญหลุดช่วงที่โมเดล
  ตีความได้ = รอดด้วยโชค ไม่ใช่ด้วยการออกแบบ)

หลักที่ใช้แก้: ไม่แปลงค่าเงินให้ (ไม่รู้แน่ว่า field ไหนของ yfinance อยู่ฝั่งไหน — เดาผิดแย่กว่า
ไม่มี) แต่ **ติดป้ายหน่วยให้ตรงจริง + ตัดอัตราส่วนข้ามสกุลทิ้ง + ปฏิเสธการคำนวณ EV**.
"""
from src.agent.health import _currency_mismatch, compute_health
from src.agent.valuation import reverse_dcf
from src.providers.stock.fundamentals import StockFundamentals

_SUMMARY = type("S", (), {"sentiment": "neutral"})()


def _fundamentals(financial_currency="USD", price_currency="USD") -> StockFundamentals:
    return StockFundamentals(
        period="FY2025",
        financial_currency=financial_currency, price_currency=price_currency,
        revenue=4_440_000_000_000.0, net_income=1_697_000_000_000.0,
        cfo=2_274_000_000_000.0, net_debt=-1_703_000_000_000.0,
        market_cap=2_096_000_000_000.0, free_cash_flow=992_000_000_000.0,
        fcf_yield=35.25, price_to_sales=0.47, price_to_book=84.3, ev_ebitda=4.497,
        pe=35.58, forward_pe=18.71, peg=0.98, revenue_cagr=18.94,
    )


def test_statement_facts_carry_the_reporting_currency():
    facts = {f.label: f.unit for f in _fundamentals("TWD", "USD").to_facts()}
    assert facts["Revenue"] == "TWD"
    assert facts["Net Income"] == "TWD"
    assert facts["Net Debt"] == "TWD"
    assert facts["Market Cap"] == "USD"      # ฝั่งราคา — คนละสกุลกับงบ และต้องบอกให้รู้


def test_cross_currency_ratios_are_dropped_not_shown_wrong():
    """P/S 0.47x ของ TSM ไม่ใช่ 'ถูกมาก' แต่คือการหารข้ามสกุล — ปล่อยขึ้นหน้าจอแย่กว่าไม่มี."""
    labels = {f.label for f in _fundamentals("TWD", "USD").to_facts()}
    assert {"P/S", "P/B", "EV/EBITDA", "FCF Yield"}.isdisjoint(labels)
    # P/E ของ ADR คิดจากราคาและ EPS ฝั่งเดียวกัน (ตรวจแล้วกับ TSM/ASML จริง) จึงยังใช้ได้
    assert {"P/E", "Forward P/E", "PEG"} <= labels


def test_same_currency_keeps_everything_as_before():
    labels = {f.label for f in _fundamentals("USD", "USD").to_facts()}
    assert {"P/S", "P/B", "EV/EBITDA", "FCF Yield"} <= labels


def test_reverse_dcf_refuses_instead_of_adding_two_currencies():
    assert reverse_dcf(_fundamentals("TWD", "USD"), risk_free_pct=4.0) is None
    assert reverse_dcf(_fundamentals("USD", "USD"), risk_free_pct=4.0) is not None


def test_mismatch_detected_from_fact_units_for_backfill():
    """path ของ health อ่านจาก facts ใน DB (ไม่มี object ต้นทาง) — ต้องจับได้จากป้ายหน่วย."""
    mixed = [{"label": "Market Cap", "value": 1.0, "unit": "USD", "period": "FY2025"},
             {"label": "Net Debt", "value": -2.0, "unit": "TWD", "period": "FY2025"}]
    assert _currency_mismatch(mixed) is True


def test_old_rows_labelled_usd_everywhere_behave_exactly_as_before():
    """แถวเก่าติดป้าย USD ทั้งหมด -> ต้องไม่ถูกตีความว่าปนสกุล ไม่งั้นเป็นการรื้อประวัติ."""
    old = [{"label": "Market Cap", "value": 1.0, "unit": "USD", "period": "FY2025"},
           {"label": "Net Debt", "value": -2.0, "unit": "USD", "period": "FY2025"},
           {"label": "ROIC", "value": 44.0, "unit": "%", "period": "FY2025"}]
    assert _currency_mismatch(old) is False


def test_mismatch_ignores_non_currency_units():
    """เจอ '%' หรือ 'x' ก่อนต้องไม่ตัดสินว่าปนสกุล — ต้องไล่หาตัวที่เป็นสกุลเงินจริง."""
    facts = [{"label": "Market Cap", "value": 1.0, "unit": "USD", "period": "FY2025"},
             {"label": "Revenue", "value": 5.0, "unit": "%", "period": "FY2025"},
             {"label": "Net Income", "value": 2.0, "unit": "USD", "period": "FY2025"}]
    assert _currency_mismatch(facts) is False


def test_health_excludes_the_price_leg_with_an_honest_reason():
    facts = _fundamentals("TWD", "USD").to_facts()
    health = compute_health(_SUMMARY, [], facts, 4.0)

    assert health["valuation"]["excluded"] is True
    assert "คนละสกุลเงิน" in health["valuation"]["reason"]
    # เหตุผลต้องบอกสาเหตุจริง ไม่ใช่ 'ไม่มี Market Cap' ซึ่งมีอยู่และไม่ใช่ปัญหา
    assert "ไม่มี Market Cap" not in health["valuation"]["reason"]
