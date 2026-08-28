"""เช็คกับความเป็นจริง (Phase 44). Offline ล้วน.

"ตลาด price ไว้ที่ FCF โต 33.8%/ปี" เป็นข้อความที่เถียงไม่ได้เพราะไม่มีอะไรให้เทียบ
ส่วน "ราคานี้ขอให้รายได้โต 8.9 เท่าใน 10 ปี" เถียงได้ทันทีด้วยความรู้เรื่องอุตสาหกรรม —
นั่นคือทั้งหมดที่โมดูลนี้ทำ: แปลงข้อเรียกร้องให้ไปชนกับเพดานทางกายภาพได้
"""
import pytest

from src.agent.reality import FCF_MARGIN_CEILING_PCT, reality_check, required_scale


# ---------- แกนหลัก ----------

def test_it_walks_the_implied_growth_forward_and_asks_how_big_the_company_must_be():
    """NVDA ของจริง: FCF ฐาน 61.5B โต 33.8%/ปี 10 ปี -> 1.13T ซึ่งที่ margin 50% แปลว่า
    ต้องมีรายได้ 2.26T = ราวสามเท่าของตลาดเซมิคอนดักเตอร์ทั้งโลกวันนี้."""
    r = required_scale(61.5e9, 33.8, 10, revenue=253.5e9, fcf_margin_pct=18.3)

    assert r["fcf_needed"] == pytest.approx(1.131e12, rel=0.01)
    assert r["revenue_multiple"] == pytest.approx(8.9, abs=0.1)
    assert r["revenue_cagr_needed_pct"] == pytest.approx(24.5, abs=0.1)


def test_the_required_revenue_growth_is_a_cagr_over_the_same_window_as_the_model():
    """ต้องเป็นอัตราต่อปีบนหน้าต่างเดียวกับที่ reverse-DCF ใช้ ไม่งั้นเอาไปเทียบกับ
    revenue CAGR จริงของบริษัทไม่ได้ ซึ่งคือประโยชน์ทั้งหมดของมัน."""
    r = required_scale(1.0e9, 20.0, 10, revenue=1.0e10, fcf_margin_pct=10.0)

    grown = r["revenue_now"] * (1 + r["revenue_cagr_needed_pct"] / 100) ** r["years"]

    assert grown == pytest.approx(r["revenue_needed"], rel=0.001)


# ---------- การแยกส่วนที่เป็นหัวใจของเฟสนี้ ----------

def test_a_squeezed_margin_can_satisfy_the_price_with_no_revenue_growth_at_all():
    """AMZN ของจริง: margin 0.4% เพราะ capex — FCF โตได้หลายเท่าโดยรายได้ไม่ต้องขยับเลย
    'FCF ต้องโต 22 เท่า' จึงเป็นข้อเรียกร้องคนละน้ำหนักกับบริษัทที่ margin ตันแล้ว."""
    r = required_scale(1.0e9, 20.0, 10, revenue=1.0e12, fcf_margin_pct=0.4)

    assert r["margin_alone_enough"] is True
    assert r["revenue_cagr_needed_pct"] == 0.0


def test_a_company_already_at_the_ceiling_must_get_every_point_from_revenue():
    """MA ของจริง: margin 47.6% ไม่เหลือที่ให้ขยาย ทุก % ของ FCF ต้องมาจากรายได้ล้วนๆ."""
    r = required_scale(13.6e9, 10.9, 10, revenue=33.9e9, fcf_margin_pct=47.6)

    assert r["margin_alone_enough"] is False
    assert r["revenue_multiple"] > 2


def test_the_same_fcf_growth_is_a_different_demand_depending_on_margin_headroom():
    """ข้อค้นพบที่ทำให้เฟสนี้มีอยู่ — growth เท่ากันเป๊ะ แต่ข้อเรียกร้องต่อรายได้ต่างกันคนละโลก."""
    squeezed = required_scale(1.0e9, 25.0, 10, revenue=5.0e11, fcf_margin_pct=0.2)
    maxed = required_scale(1.0e9, 25.0, 10, revenue=2.0e9, fcf_margin_pct=50.0)

    assert squeezed["revenue_cagr_needed_pct"] == 0.0
    assert maxed["revenue_cagr_needed_pct"] > 15


# ---------- เพดาน margin ----------

def test_the_ceiling_is_generous_on_purpose_so_a_heavy_demand_is_really_heavy():
    """ถ้าให้ margin ดีที่สุดเท่าที่เป็นไปได้แล้วยังต้องโตรายได้หลายเท่า ข้อเรียกร้องนั้น
    หนักจริง ไม่ใช่หนักเพราะเราตั้งสมมติฐานแคบ."""
    r = required_scale(1.0e9, 15.0, 10, revenue=1.0e10, fcf_margin_pct=5.0)

    assert r["margin_ceiling_pct"] == FCF_MARGIN_CEILING_PCT


def test_a_company_beating_the_ceiling_keeps_its_own_number():
    """MA ทำ 47.6% วันนี้ ถ้าบริษัทไหนทำได้เกิน 50% จริง การกดมันลงมาเข้าสูตรเรา
    = บังคับให้มันแย่กว่าความจริงเพื่อให้ผลออกมาน่ากลัวขึ้น."""
    r = required_scale(1.0e9, 10.0, 10, revenue=1.0e10, fcf_margin_pct=62.0)

    assert r["margin_ceiling_pct"] == 62.0


# ---------- ไม่มีข้อมูล = ไม่ตอบ ----------

@pytest.mark.parametrize("kwargs", [
    {"fcf_base": None, "growth_pct": 10.0, "years": 10, "revenue": 1e10, "fcf_margin_pct": 10.0},
    {"fcf_base": 1e9, "growth_pct": None, "years": 10, "revenue": 1e10, "fcf_margin_pct": 10.0},
    {"fcf_base": 1e9, "growth_pct": 10.0, "years": None, "revenue": 1e10, "fcf_margin_pct": 10.0},
    {"fcf_base": 1e9, "growth_pct": 10.0, "years": 10, "revenue": None, "fcf_margin_pct": 10.0},
    {"fcf_base": -1e9, "growth_pct": 10.0, "years": 10, "revenue": 1e10, "fcf_margin_pct": 10.0},
    {"fcf_base": 1e9, "growth_pct": 10.0, "years": 10, "revenue": 0.0, "fcf_margin_pct": 10.0},
])
def test_missing_or_impossible_inputs_get_no_answer_rather_than_a_guess(kwargs):
    assert required_scale(**kwargs) is None


def test_a_missing_margin_still_works_because_the_ceiling_carries_it():
    """margin วันนี้ไม่มี (ข้อมูลขาด) ไม่ควรทำให้ทั้ง check หายไป — เพดานคือสิ่งที่ใช้คำนวณจริง."""
    r = required_scale(1.0e9, 10.0, 10, revenue=1.0e10, fcf_margin_pct=None)

    assert r is not None
    assert r["margin_today_pct"] is None
    assert r["margin_ceiling_pct"] == FCF_MARGIN_CEILING_PCT


# ---------- สองข้อเรียกร้องข้างกัน ----------

DCF = {"implied_growth": 33.8, "realistic_growth": 18.3, "years": 10, "fcf_base": 61.5e9}


def test_it_reports_what_the_market_asks_and_what_we_ask_side_by_side():
    """gap เดิมทั้งดุ้น แต่ในหน่วยที่เถียงได้: 'ต่างกัน 15.5pp' vs 'ตลาดขอ 8.9 เท่า เราขอ 2.6 เท่า'."""
    out = reality_check(DCF, revenue=253.5e9, fcf_margin_pct=18.3)

    assert out["market"]["revenue_multiple"] > out["ours"]["revenue_multiple"]


def test_when_we_ask_more_than_the_market_that_is_the_cheap_case():
    """ADBE/META/DUOL ของจริง — ข้อเรียกร้องของเราหนักกว่าที่ราคาขอ = ราคาไม่ได้เรียกร้องอะไรมาก
    ต้องออกมาทางเดียวกับที่กระดานบอกว่า 'ถูก' เสมอ (เลขชุดเดียวกัน คนละหน่วย)."""
    cheap = {**DCF, "implied_growth": 4.0, "realistic_growth": 7.1}

    out = reality_check(cheap, revenue=253.5e9, fcf_margin_pct=18.3)

    assert out["ours"]["fcf_needed"] > out["market"]["fcf_needed"]


def test_no_dcf_means_no_reality_check():
    assert reality_check({}, 1e10, 10.0) is None
    assert reality_check({"years": 10, "fcf_base": None}, 1e10, 10.0) is None
