"""กรอบคะแนนสำหรับธนาคาร (Phase 33.3) + ต้นตอที่ GOOGL realistic growth เด้งสองค่า.

ทั้งสองเรื่องมาจากปัญหาเดียวกัน: **สูตรที่เจอข้อมูลไม่ตรงสมมติฐานแล้วยังตอบออกมาเหมือนปกติ**
- แบงก์: เกณฑ์ 5/8 ข้อต้องใช้ตัวเลขที่ไม่มีความหมายกับธนาคาร -> JPM ตกด่านข้อมูล 4/8 ตลอดกาล
- GOOGL: D&A หายไปบางรอบ -> sustainable growth คำนวณไม่ได้ -> เงียบๆ สลับไปใช้ historical CAGR
  โดยยังปักป้าย lens ว่า 'standard' เหมือนเดิม = anchor เปลี่ยนโดยไม่มีใครรู้
"""
import pandas as pd

from src.agent.health import (
    BANK_CRITERIA, PIOTROSKI_CRITERIA, _bank_valuation_score, _is_bank, compute_health,
)
from src.agent.valuation import reverse_dcf, valuation_guard
from src.providers.stock.fundamentals import _first

_SUMMARY = type("S", (), {"sentiment": "neutral"})()


def _f(label, value, unit="%", period="FY2025"):
    return {"label": label, "value": value, "unit": unit, "period": period}


def _jpm_facts() -> list[dict]:
    """ตัวเลขจริงของ JPM รอบ 2026-08 (ย่อเฉพาะที่เกณฑ์ธนาคารใช้)."""
    return [
        _f("Revenue", 181_847_000_000.0, "USD"),
        _f("Net Interest Income", 95_443_000_000.0, "USD"),
        _f("Tangible Book Value", 277_935_000_000.0, "USD"),
        _f("ROTCE", 20.53), _f("Equity / Assets", 8.19), _f("NII / Assets", 2.16),
        _f("Cost+Provision / Revenue", 61.04),
        _f("Revenue CAGR", 12.5), _f("P/B", 2.6448984, "x"), _f("Beta", 0.977, "x"),
        _f("ROE", 15.74), _f("ROE", 16.96, period="FY2024"),
        _f("Net Margin", 31.37), _f("Net Margin", 34.51, period="FY2024"),
        _f("Diluted Shares", 2_781_500_000.0, "shares"),
        _f("Diluted Shares", 2_879_000_000.0, "shares", "FY2024"),
    ]


# ───────────────────────────────────────────────────────────── ธนาคาร ────

def test_bank_detected_from_interest_income_share_not_sector_string():
    assert _is_bank(_jpm_facts()) is True
    # บริษัททั่วไปที่มีดอกเบี้ยรับนิดหน่อยจากเงินสด ต้องไม่ถูกจับเป็นธนาคาร
    not_bank = [_f("Revenue", 1_000_000_000.0, "USD"),
                _f("Net Interest Income", 30_000_000.0, "USD")]
    assert _is_bank(not_bank) is False
    assert _is_bank([_f("Revenue", 1_000.0, "USD")]) is False


def test_bank_uses_its_own_criteria_and_is_no_longer_excluded():
    """เคสจุดชนวน: JPM เคยได้ 'ประเมินไม่ได้' ทุกวันเพราะคำนวณเกณฑ์ของหุ้นทั่วไปได้แค่ 4/8."""
    health = compute_health(_SUMMARY, [], _jpm_facts(), 4.0)

    assert health["fundamental"]["framework"] == "bank"
    assert health["fundamental"]["disqualified"] is False
    assert health["fundamental"]["computable"] == 8
    assert health["tier"] != "excluded"
    assert "เกณฑ์ธนาคาร" in health["fundamental"]["reason"]


def test_bank_scale_stays_out_of_eight_so_scores_remain_comparable():
    """ตัวหารต้องเท่าเดิม ไม่งั้นคะแนนแบงก์กับหุ้นอื่นอยู่คนละฐานทั้งที่โชว์รวมกันในตารางเดียว."""
    assert len(BANK_CRITERIA) == len(PIOTROSKI_CRITERIA) == 8


def test_non_bank_scoring_is_untouched():
    """หุ้นทั่วไปต้องไม่แตะกรอบธนาคารเลย (ไม่มี Net Interest Income = ไม่เข้าเงื่อนไข)."""
    facts = [_f("Revenue", 1_000_000_000.0, "USD"), _f("Net Margin", 39.91),
             _f("Operating Margin", 13.07)]
    assert compute_health(_SUMMARY, [], facts, 4.0)["fundamental"]["framework"] == "standard"


def test_bank_valuation_uses_justified_price_to_book():
    """ROTCE 20.53% กับ COE ~9.2% -> justified P/B ~2.7x; ราคาจริง 2.64x = ต่ำกว่าเล็กน้อย."""
    result = _bank_valuation_score(_jpm_facts(), 4.0)

    assert result["excluded"] is False
    assert result["lens"] == "bank_pb"
    assert 2.5 < result["justified_pb"] < 3.0
    assert result["premium_pct"] < 0            # ซื้อขายต่ำกว่ามูลค่าที่เป็นธรรม
    assert 2.0 < result["score"] <= 3.0


def test_bank_valuation_score_is_graded_not_a_cliff():
    """แบงก์ที่แพงขึ้นเรื่อยๆ ต้องเสียคะแนนไล่ระดับ ไม่ใช่กระโดดจาก 3 ไป 0."""
    scores = []
    for pb in (1.8, 2.65, 3.1, 3.6, 4.2):
        facts = [f for f in _jpm_facts() if f["label"] != "P/B"] + [_f("P/B", pb, "x")]
        scores.append(_bank_valuation_score(facts, 4.0)["score"])

    assert scores == sorted(scores, reverse=True)          # แพงขึ้น = คะแนนลดลงเสมอ
    assert len(set(scores)) == len(scores)                 # ไล่ระดับจริง ไม่ใช่ค่าเดียวซ้ำ
    assert scores[0] == 3.0 and scores[-1] == 0.0


def test_bank_valuation_refuses_when_rotce_below_terminal_growth():
    """ROTCE ต่ำกว่าการเติบโตระยะยาว = สูตรให้ค่าติดลบ ต้องปฏิเสธ ไม่ใช่คืนตัวเลขไร้ความหมาย."""
    facts = [f for f in _jpm_facts() if f["label"] != "ROTCE"] + [_f("ROTCE", 1.0)]
    result = _bank_valuation_score(facts, 4.0)
    assert result["excluded"] is True and result["score"] is None


def test_bank_valuation_refuses_without_inputs():
    facts = [f for f in _jpm_facts() if f["label"] not in ("ROTCE", "P/B")]
    assert _bank_valuation_score(facts, 4.0)["excluded"] is True


# ──────────────────────────────────────────── GOOGL: anchor เด้งสองค่า ────

def _guard_inputs(da):
    """อินพุตแบบ GOOGL: ทุกอย่างเหมือนกันหมด ต่างแค่ D&A มี/ไม่มี."""
    return dict(fcf_base=7.0e10, nopat=1.0e11, revenue=4.0e11, capex=-5.0e10, da=da,
                nwc_change=-1.0e9, roic_pct=30.0, historical_cagr=12.51)


def test_missing_depreciation_is_flagged_not_silently_swapped():
    route_ok, flags_ok, sustainable_ok = valuation_guard(**_guard_inputs(da=2.1e10))
    route_missing, flags_missing, sustainable_missing = valuation_guard(**_guard_inputs(da=None))

    assert sustainable_ok is not None and route_ok == "standard"
    # ขาดข้อมูล = ต้องติดธงและเปลี่ยนเลนส์อย่างเปิดเผย ไม่ใช่อยู่เลนส์เดิมแล้วเปลี่ยน anchor เงียบๆ
    assert sustainable_missing is None
    assert "SUSTAINABLE_UNCOMPUTABLE" in flags_missing
    assert route_missing == "growth"


def test_reverse_dcf_does_not_relabel_historical_cagr_as_the_standard_lens():
    """เดิม: D&A หาย -> lens ยังเป็น 'standard' แต่ realistic_growth กลายเป็น historical_cagr
    (GOOGL เด้ง 15.7 <-> 12.51 สี่รอบติดโดยไม่มีธงอะไรบอกเลย)."""
    class Duck:
        market_cap = 2.0e12
        net_debt = 0.0
        free_cash_flow = 7.0e10
        fcf_series = [("FY2022", 6.0e10), ("FY2023", 6.5e10), ("FY2024", 7.0e10)]
        revenue_series = [("FY2023", 3.0e11), ("FY2024", 3.5e11), ("FY2025", 4.0e11)]
        revenue = 4.0e11
        revenue_cagr = 12.51
        fcf_margin = 17.5
        beta = 1.0
        capex = -5.0e10
        depreciation_amortization = None       # หายไปเหมือนที่เจอจริง
        nwc_change = -1.0e9
        nopat = 1.0e11
        roic = 30.0

    result = reverse_dcf(Duck(), risk_free_pct=4.0)
    assert result["lens"] == "growth"
    assert "SUSTAINABLE_UNCOMPUTABLE" in result["flags"]
    assert result["realistic_growth"] != 12.51   # ไม่ใช่ historical CAGR ที่แอบสวมรอย


def test_first_falls_through_to_the_next_alias_when_the_value_is_nan():
    """ต้นตอฝั่งข้อมูล: yfinance คืนชุดแถวไม่เหมือนกันทุกครั้ง — ชื่อแรกมีอยู่แต่เป็น NaN ได้."""
    df = pd.DataFrame(
        {"2025-12-31": [float("nan"), 21_136_000_000.0]},
        index=["Depreciation And Amortization", "Depreciation"],
    )
    assert _first(["Depreciation And Amortization", "Depreciation"], df) == 21_136_000_000.0
    assert _first(["Not There"], df) is None
