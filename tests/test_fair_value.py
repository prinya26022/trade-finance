"""ราคาที่คุ้มค่า — reverse-DCF เดินย้อนทาง (Phase 40). Offline ล้วน.

สิ่งที่ฟีเจอร์นี้ทำคือ **แปลงหน่วย** ของ gap ที่แสดงอยู่แล้ว ไม่ใช่สัญญาณใหม่: "gap +14.8pp"
เป็นตัวเลขที่รู้สึกไม่ได้ ส่วน "ตลาดขอราคาสูงกว่าที่ประมาณการเรารองรับ 67%" คือเรื่องเดียวกัน
ในหน่วยที่เจ้าของใช้ซื้อขายจริง

อันตรายของมันคือการอ่านเป็นคำทำนายราคา ซึ่งโปรเจกต์นี้ไม่ทำโดยตั้งใจ. สิ่งที่กันไว้คือ **แถบ
ความไว**: DCF 10 ปีขยายความต่างของ growth เป็นทวีคูณ — DUOL ขยับ 15.2% ต่อ growth 1pp ส่วน
AAPL 2.5% เลขสองตัวนี้จึงเชื่อได้ไม่เท่ากันเลย และเทสต์ชุดนี้บังคับว่าต้องบอกออกไปทุกครั้ง
"""
import pytest

from src.agent.valuation import (
    FAIR_BAND_PP,
    fair_market_cap,
    fair_value,
    implied_growth_rate,
    intrinsic_value,
)

# ค่าที่รูปร่างเหมือน dict ที่เก็บลง analyses.valuation_json จริง (หน่วยเป็น % ทั้งหมด)
DCF = {"realistic_growth": 8.0, "ev": 1.0e12, "fcf_base": 4.0e10,
       "wacc": 10.0, "terminal_growth": 2.5, "years": 10}
MCAP = 9.0e11        # net debt = ev - mcap = 1.0e11


# ---------- ต้องเป็นการย้อนทางของขาไปจริงๆ ----------

def test_the_fair_price_is_exactly_where_the_market_would_agree_with_us():
    """นิยามของทั้งฟีเจอร์: ที่ market cap นี้ implied growth ต้องเท่ากับ realistic growth พอดี
    ถ้าไม่ใช่ ตัวเลขที่โชว์ก็ไม่ได้แปลว่าอะไรเลย."""
    mcap = fair_market_cap(DCF["fcf_base"], 8.0, 10.0, 2.5, 10, net_debt=1.0e11)
    ev_at_fair = mcap + 1.0e11

    back = implied_growth_rate(ev_at_fair, DCF["fcf_base"], 0.10, 0.025, 10)

    assert back == pytest.approx(8.0, abs=0.05)


def test_it_uses_the_same_model_as_the_score_not_a_second_formula():
    """ลอกสูตรไว้สองที่ = วันหลัง valuation.py ขยับแล้วราคาที่คุ้มค่าจะเพี้ยนเงียบๆ
    (บั๊กประจำของโปรเจกต์: 33.3, 34, 39)."""
    expected = intrinsic_value(DCF["fcf_base"], 0.08, 0.10, 0.025, 10) - 1.0e11

    assert fair_market_cap(DCF["fcf_base"], 8.0, 10.0, 2.5, 10, net_debt=1.0e11) == expected


def _at_price(market_cap: float, net_debt: float = 1.0e11) -> dict:
    """dcf ที่ราคาต่างกันโดย **หนี้สุทธิคงเดิม** — ev ต้องขยับตาม ไม่งั้นการเปลี่ยน market cap
    เฉยๆ จะกลายเป็นการเปลี่ยนโครงสร้างหนี้ของบริษัทไปพร้อมกัน (คนละคำถาม)."""
    return {**DCF, "ev": market_cap + net_debt}


def test_a_cheaper_price_today_means_a_bigger_upside():
    cheap = fair_value(_at_price(5.0e11), market_cap=5.0e11)
    rich = fair_value(_at_price(1.5e12), market_cap=1.5e12)

    assert cheap["discount_pct"] > 0 > rich["discount_pct"]


def test_more_debt_at_the_same_price_lowers_what_the_equity_is_worth():
    """หนี้สุทธิเข้าสมการจริง ไม่ได้ถูกมองข้าม — มูลค่ากิจการเท่าเดิมแต่เจ้าหนี้กินไปมากขึ้น."""
    light = fair_value(_at_price(9.0e11, net_debt=0.0), market_cap=9.0e11)
    heavy = fair_value(_at_price(9.0e11, net_debt=3.0e11), market_cap=9.0e11)

    assert light["discount_pct"] > heavy["discount_pct"]


def test_a_gap_of_zero_prices_the_stock_at_exactly_fair():
    """ตรวจว่าไม่มี bias ค้างอยู่ในสูตร: ถ้าตลาดคาดเท่าที่เราคาดอยู่แล้ว ส่วนต่างต้องเป็น 0."""
    fair_mcap = fair_market_cap(DCF["fcf_base"], 8.0, 10.0, 2.5, 10, net_debt=1.0e11)

    out = fair_value({**DCF, "ev": fair_mcap + 1.0e11}, market_cap=fair_mcap)

    assert out["discount_pct"] == pytest.approx(0.0, abs=0.1)


# ---------- ความไว: สิ่งที่กันไม่ให้เลขนี้ถูกอ่านเป็นคำทำนาย ----------

def test_the_band_is_always_there_and_straddles_our_estimate():
    out = fair_value(DCF, MCAP)

    assert [r["growth"] for r in out["band"]] == [8.0 - FAIR_BAND_PP, 8.0, 8.0 + FAIR_BAND_PP]
    assert out["band"][0]["discount_pct"] < out["band"][1]["discount_pct"] < out["band"][2]["discount_pct"]


def test_sensitivity_is_reported_as_one_number_per_point_of_growth():
    """เลขตัวเดียวที่บอกว่า 'ควรเชื่อแค่ไหน' — DUOL ของจริง 15.2%/pp ส่วน AAPL 2.5%/pp
    ต่างกัน 6 เท่า ทั้งที่หน้าตาของตัวเลขราคาเหมือนกันเป๊ะ."""
    out = fair_value(DCF, MCAP)

    lo, hi = out["band"][0]["discount_pct"], out["band"][2]["discount_pct"]
    assert out["pct_per_pp"] == pytest.approx((hi - lo) / (2 * FAIR_BAND_PP), abs=0.1)
    assert out["pct_per_pp"] > 0


def test_a_longer_horizon_amplifies_the_same_disagreement():
    """เหตุผลที่ต้องเตือนเรื่องความไว: DCF ขยายความต่างของ growth เป็นทวีคูณตามจำนวนปี —
    gap เท่ากันเป๊ะแต่ราคาต่างกันคนละเรื่อง."""
    short = fair_value({**DCF, "years": 5}, MCAP)
    long = fair_value({**DCF, "years": 15}, MCAP)

    assert long["pct_per_pp"] > short["pct_per_pp"]


# ---------- ต้องไม่ตอบเมื่อไม่ควรตอบ ----------

def test_it_says_nothing_when_the_company_burns_cash():
    """FCF ฐานติดลบ = reverse-DCF ใช้ไม่ได้ตั้งแต่ต้น (ORCL/SPCX) — ราคาที่คุ้มค่าก็ต้องไม่มี
    ไม่ใช่เสกเลขออกมาจากสูตรที่ใช้ไม่ได้."""
    assert fair_market_cap(-1.0e9, 8.0, 10.0, 2.5, 10, net_debt=0.0) is None
    assert fair_value({**DCF, "fcf_base": -1.0e9}, MCAP) is None


def test_it_says_nothing_when_debt_swallows_the_whole_enterprise():
    """ส่วนของผู้ถือหุ้นไม่เหลืออะไรตามโมเดล = ข้อความที่แรงเกินกว่าจะพูดจาก DCF ธรรมดา
    ตอบเลขติดลบที่ดูเหมือนคำนวณมาอย่างดีแย่กว่าไม่ตอบ."""
    assert fair_market_cap(1.0e8, 2.0, 10.0, 2.5, 10, net_debt=1.0e13) is None


def test_it_says_nothing_when_the_gordon_model_is_invalid():
    """WACC <= terminal growth -> ตัวหารติดลบ มูลค่าจะออกมาเป็นบวกมหาศาลแบบไร้ความหมาย."""
    assert fair_market_cap(1.0e10, 5.0, 2.0, 2.5, 10, net_debt=0.0) is None


def test_it_says_nothing_without_a_realistic_growth_to_anchor_on():
    """แถวที่ตีมูลค่าไม่ได้ (currency mismatch, ข้อมูลขาด) ต้องไม่มีราคาที่คุ้มค่าโผล่มา."""
    assert fair_value({**DCF, "realistic_growth": None}, MCAP) is None
    assert fair_value(None, MCAP) is None
    assert fair_value(DCF, None) is None


# ---------- ต่อสายเข้าผลจริง ----------

def test_reverse_dcf_carries_the_fair_value_with_it():
    """คำนวณที่เดียวแล้วติดไปกับผล — หน้าเว็บ/ประวัติ/คะแนนจึงอ่านเลขตัวเดียวกันเสมอ."""
    from types import SimpleNamespace

    from src.agent.valuation import reverse_dcf

    duck = SimpleNamespace(
        market_cap=9.0e11, free_cash_flow=4.0e10, net_debt=1.0e11, beta=1.0,
        fcf_series=[("FY2023", 3.6e10), ("FY2024", 3.8e10), ("FY2025", 4.0e10)],
        revenue=2.0e11, revenue_cagr=8.0,
        revenue_series=[("FY2024", 1.85e11), ("FY2025", 2.0e11)],
        capex=None, depreciation_amortization=None, nwc_change=None, nopat=None, roic=None,
        fcf_margin=20.0, fcf_cagr_long=None, fcf_long_window=None, fcf_long_years=None,
    )

    out = reverse_dcf(duck, risk_free_pct=4.0)

    assert out["fair"] is not None
    assert out["fair"]["at_growth"] == out["realistic_growth"]
    assert len(out["fair"]["band"]) == 3


def test_the_bank_lens_has_its_own_fair_value_instead_of_a_hole():
    """แบงก์ใช้ justified P/B ไม่ใช่ DCF — เคยหายจาก screener ทั้งกลุ่มมาแล้วเพราะ 'เลนส์นี้
    ไม่มีของนั้น' (33.3). ความไวของแบงก์วัดต่อ ROTCE 1pp ซึ่งเป็นหน่วยที่มีความหมายกับมัน."""
    from src.agent.health import _bank_valuation_score

    facts = [
        {"label": "ROTCE", "value": 20.0, "unit": "%", "period": "FY2025"},
        {"label": "P/B", "value": 2.0, "unit": "x", "period": "TTM"},
        {"label": "Beta", "value": 1.0, "unit": "x", "period": "TTM"},
    ]

    fair = _bank_valuation_score(facts, risk_free_pct=4.0)["fair"]

    assert fair["lens"] == "bank_pb"
    assert fair["at_rotce"] == 20.0 and fair["market_cap"] is None
    assert [r["rotce"] for r in fair["band"]] == [19.0, 20.0, 21.0]
    assert fair["pct_per_pp"] > 0
