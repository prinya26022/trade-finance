"""หลักฐานที่ SUSTAINABLE_DIVERGES ใช้ตรวจ (Phase 42). Offline ล้วน.

guard เดิมเทียบ sustainable_growth กับ **revenue CAGR** อย่างเดียว ทั้งที่ตั้งแต่ Phase 19.4
โมเดลตัดสินไปแล้วว่า FCF CAGR คือหน่วยที่ถูกต้องในการเทียบกับ implied_growth — ตัวตรวจความ
น่าเชื่อถือจึงทำงานกับปริมาณที่โมเดลเองบอกว่าใช้หน่วยผิด

แต่ **สลับไปใช้ FCF อย่างเดียวก็ผิดคนละทาง** และเทสต์ชุดนี้ล็อกทั้งสองด้านไว้ เพราะ A/B กับ
ข้อมูลจริงพบว่าโหมด 'fcf' จะยก AAPL จาก 0.0/3 เป็น 2.42/3 ทั้งที่รายได้โต 1.81%/ปี
"""
import pytest

from src.agent.valuation import DIVERGENCE_TRIGGER_PP, _diverges, valuation_guard

# ค่าที่ทำให้ sustainable คำนวณได้เป็นบวกและไม่ติดธงอื่น (nopat margin สูงพอ, reinvestment บวก)
OK_INPUTS = dict(fcf_base=1.0e9, nopat=2.0e9, revenue=1.0e10,
                 capex=-3.0e9, da=1.0e9, nwc_change=0.0, roic_pct=20.0)


def test_one_piece_of_contrary_evidence_is_enough():
    """ถ้าการวัดอดีตแบบใดแบบหนึ่งขัดกับ sustainable เกินเกณฑ์ = ไม่ควรเชื่อ sustainable.
    'ต้องขัดทั้งคู่ถึงจะนับ' คือการให้ประโยชน์แห่งความสงสัยกับตัวเลขที่เราคำนวณเอง."""
    assert _diverges(19.0, revenue_cagr=2.0, fcf_cagr=17.0) is True    # รายได้ค้าน
    assert _diverges(19.0, revenue_cagr=18.0, fcf_cagr=1.0) is True    # FCF ค้าน
    assert _diverges(19.0, revenue_cagr=18.0, fcf_cagr=17.0) is False  # ไม่มีใครค้าน


def test_the_msft_shape_fcf_contradicts_while_revenue_agrees():
    """MSFT ของจริง: sustainable 17.21 กับ revenue CAGR 16.12 ห่างแค่ 1.1pp จึงลอดตัวตรวจเดิม
    ทั้งที่ FCF ลดลงสามปีติดขณะรายได้โต 35%. ที่ค่าจริงของ MSFT ยังลอดอยู่ดี (ห่าง 9.8pp <
    เกณฑ์ 15pp) — เทสต์นี้จึงล็อก *กลไก* ว่า FCF ค้านได้ ไม่ได้อ้างว่าแก้เคส MSFT แล้ว."""
    assert _diverges(17.21, revenue_cagr=16.12, fcf_cagr=7.43) is False   # ค่าจริง: ยังลอด
    assert _diverges(17.21, revenue_cagr=16.12, fcf_cagr=1.0) is True     # ถ้า FCF แย่กว่านี้ จับได้


def test_switching_to_fcf_only_would_let_the_apple_case_through():
    """เหตุผลที่ไม่เลือกโหมด 'fcf': AAPL sustainable 19.07 กับ FCF ยาว 6.67 ห่าง 12.4pp
    ลอดใต้เกณฑ์ ทั้งที่รายได้โต 1.81%/ปี ซึ่งขัดกับ 'ทบต้นได้ 19%/ปี' อย่างชัดเจน
    (A/B จริง: คะแนนขาราคา AAPL จะกระโดด 0.0 -> 2.42)."""
    assert _diverges(19.07, revenue_cagr=1.81, fcf_cagr=6.67, mode="fcf") is False
    assert _diverges(19.07, revenue_cagr=1.81, fcf_cagr=6.67, mode="either") is True


def test_a_negative_sustainable_against_double_digit_history_is_a_contradiction_not_a_distance():
    """ติดลบทั้งที่อดีตโตสองหลัก = ขัดแย้งเชิงทิศทาง ต้องจับได้แม้ระยะห่างจะไม่ถึงเกณฑ์."""
    assert _diverges(-1.0, revenue_cagr=11.0, fcf_cagr=None) is True
    assert _diverges(-1.0, revenue_cagr=None, fcf_cagr=11.0) is True


def test_the_threshold_itself_did_not_move():
    """Phase 42 เปลี่ยน *หลักฐาน* ไม่ใช่ *เกณฑ์* — ขยับเกณฑ์คือการขยับคะแนนทั้งกระดาน
    ซึ่งเป็นคนละงานและต้อง A/B ของตัวเอง."""
    assert _diverges(20.0, revenue_cagr=20.0 - DIVERGENCE_TRIGGER_PP + 0.1, fcf_cagr=None) is False
    assert _diverges(20.0, revenue_cagr=20.0 - DIVERGENCE_TRIGGER_PP - 0.1, fcf_cagr=None) is True


def test_no_history_at_all_means_no_accusation():
    """ไม่มีอะไรให้เทียบ = ไม่มีสิทธิ์กล่าวหาว่า sustainable เชื่อไม่ได้ (ธง UNCOMPUTABLE
    ต่างหากที่ดูแลกรณีคำนวณ sustainable ไม่ได้)."""
    assert _diverges(19.0, revenue_cagr=None, fcf_cagr=None) is False


def test_the_guard_actually_passes_fcf_evidence_through():
    """ต่อสายจริงหรือเปล่า — เทสต์ที่เรียก _diverges ตรงๆ อย่างเดียวไม่พิสูจน์ว่า guard ใช้มัน."""
    _, agree, _ = valuation_guard(**OK_INPUTS, historical_cagr=20.0, fcf_cagr=19.0)
    _, contra, _ = valuation_guard(**OK_INPUTS, historical_cagr=20.0, fcf_cagr=1.0)

    assert "SUSTAINABLE_DIVERGES" not in agree
    assert "SUSTAINABLE_DIVERGES" in contra


def test_fcf_evidence_is_optional_so_old_callers_behave_exactly_as_before():
    """`fcf_cagr` มีค่าเริ่มต้น None — พาธที่ยังไม่ส่งมาต้องได้พฤติกรรมเดิมเป๊ะ."""
    route_a, flags_a, sus_a = valuation_guard(**OK_INPUTS, historical_cagr=1.0)
    route_b, flags_b, sus_b = valuation_guard(**OK_INPUTS, historical_cagr=1.0, fcf_cagr=None)

    assert (route_a, flags_a, sus_a) == (route_b, flags_b, sus_b)
    assert "SUSTAINABLE_DIVERGES" in flags_a
