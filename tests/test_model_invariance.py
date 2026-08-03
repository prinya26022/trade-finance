"""ผลลัพธ์ที่ระบบใช้ตัดสินต้องไม่ขึ้นกับว่าโมเดลไหนเป็นคนเขียนบทวิเคราะห์ (Phase 33.4).

คำอ้างนี้ถูกพูดมาตลอดตั้งแต่เริ่มเทียบสองสำนัก แต่หลักฐานคือ 'อ่านโค้ดแล้วเห็นว่าใช้แค่ facts'
ซึ่งอ่อนเกินไปสำหรับสิ่งที่ทั้งฟีเจอร์ยืนอยู่บนนั้น — และโปรเจกต์นี้เพิ่งเจอมาแล้วว่าการอ่านโค้ด
ตกหล่นได้จริง (เรื่องสกุลเงิน). ชุดนี้ล็อกไว้เป็นเทสต์ถาวร ถ้าวันไหนมีใครต่อสาย LLM กลับเข้า
คะแนน (เช่น เอา sentiment กลับเข้าผลรวม) จะพังทันทีที่นี่
"""
from src.evals.check_model_invariance import compare_one

SENTIMENTS = ("bullish", "neutral", "bearish")


def _f(label, value, unit="%", period="FY2025"):
    return {"label": label, "value": value, "unit": unit, "period": period}


def _stock_facts() -> list[dict]:
    return [
        _f("Revenue", 1_037_589_000.0, "USD"), _f("Market Cap", 6_281_218_048.0, "USD"),
        _f("ROIC", 76.1), _f("Net Margin", 39.91), _f("Operating Margin", 13.07),
        _f("Operating Margin", 8.37, period="FY2024"),
        _f("Net Margin", 11.84, period="FY2024"),
        _f("Revenue CAGR", 41.08), _f("FCF Margin", 28.44, "%", "TTM"),
        _f("FCF Yield", 4.97, "%", "TTM"),
        _f("Net Income", 414_065_000.0, "USD"), _f("CFO", 387_823_000.0, "USD"),
        _f("Net Debt", -942_610_000.0, "USD"), _f("Net Debt / EBITDA", -6.29, "x"),
        _f("Capex", -27_399_000.0, "USD"), _f("D&A", 14_391_000.0, "USD"),
        _f("NWC Change", 48_966_000.0, "USD"), _f("NOPAT", 307_739_663.0, "USD"),
        _f("Invested Capital", 404_396_000.0, "USD"), _f("Beta", 0.881, "x"),
        _f("Free Cash Flow", 360_424_000.0, "USD"),
        _f("Free Cash Flow", 264_373_000.0, "USD", "FY2024"),
        _f("Free Cash Flow", 139_930_000.0, "USD", "FY2023"),
        _f("Revenue FY", 1_037_589_000.0, "USD"),
        _f("Revenue FY", 748_024_000.0, "USD", "FY2024"),
        _f("Diluted Shares", 46_628_000.0, "shares"),
        _f("Diluted Shares", 44_936_000.0, "shares", "FY2024"),
        _f("Current Ratio", 2.61, "x"), _f("Interest Coverage", 50.0, "x"),
    ]


def _bank_facts() -> list[dict]:
    return [
        _f("Revenue", 181_847_000_000.0, "USD"),
        _f("Net Interest Income", 95_443_000_000.0, "USD"),
        _f("ROTCE", 20.53), _f("Equity / Assets", 8.19), _f("NII / Assets", 2.16),
        _f("Cost+Provision / Revenue", 61.04), _f("Revenue CAGR", 12.5),
        _f("P/B", 2.6448984, "x"), _f("Beta", 0.977, "x"),
        _f("ROE", 15.74), _f("Net Margin", 31.37),
        _f("Diluted Shares", 2_781_500_000.0, "shares"),
        _f("Diluted Shares", 2_879_000_000.0, "shares", "FY2024"),
    ]


def test_every_sentiment_gives_the_same_deterministic_result_for_a_stock():
    for other in SENTIMENTS[1:]:
        result = compare_one(_stock_facts(), SENTIMENTS[0], other)
        assert result["identical"], result["differing_fields"]


def test_every_sentiment_gives_the_same_deterministic_result_for_a_bank():
    """กรอบธนาคารเพิ่งเพิ่มเข้ามา — ต้องอยู่ใต้กติกาเดียวกัน ไม่ใช่ทางลัดที่หลุดการตรวจ."""
    for other in SENTIMENTS[1:]:
        result = compare_one(_bank_facts(), SENTIMENTS[0], other)
        assert result["identical"], result["differing_fields"]


def test_score_and_every_subcriterion_match_exactly_not_just_the_total():
    """คะแนนรวมเท่ากันแต่เกณฑ์ย่อยชดเชยกันเอง ก็ยังถือว่าโมเดลมีอิทธิพล — ต้องตรงทุกช่อง."""
    result = compare_one(_stock_facts(), "bullish", "bearish")
    assert result["a"] == result["b"]
    assert result["a"]["criteria"] == result["b"]["criteria"]
    assert result["a"]["valuation_reason"] == result["b"]["valuation_reason"]


def test_the_check_actually_detects_a_difference_when_one_exists():
    """กันเทสต์ที่ผ่านเพราะไม่ได้ตรวจอะไรเลย: เปลี่ยน 'ข้อมูล' จริงต้องถูกจับได้."""
    weaker = [f for f in _stock_facts() if f["label"] != "ROIC"] + [_f("ROIC", 1.0)]
    from src.evals.check_model_invariance import _score_with

    a = _score_with("neutral", _stock_facts(), [], 4.0)
    b = _score_with("neutral", weaker, [], 4.0)
    assert a != b
    assert a["score"] != b["score"]
