"""หลักฐานที่ SUSTAINABLE_DIVERGES ใช้ตรวจ (Phase 42). Offline ล้วน.

guard เดิมเทียบ sustainable_growth กับ **revenue CAGR** อย่างเดียว ทั้งที่ตั้งแต่ Phase 19.4
โมเดลตัดสินไปแล้วว่า FCF CAGR คือหน่วยที่ถูกต้องในการเทียบกับ implied_growth — ตัวตรวจความ
น่าเชื่อถือจึงทำงานกับปริมาณที่โมเดลเองบอกว่าใช้หน่วยผิด

แต่ **สลับไปใช้ FCF อย่างเดียวก็ผิดคนละทาง** และเทสต์ชุดนี้ล็อกทั้งสองด้านไว้ เพราะ A/B กับ
ข้อมูลจริงพบว่าโหมด 'fcf' จะยก AAPL จาก 0.0/3 เป็น 2.42/3 ทั้งที่รายได้โต 1.81%/ปี
"""
import pytest

from src.agent.valuation import (
    BORDERLINE_PP, DIVERGENCE_TRIGGER_PP, _diverges, divergence_detail, valuation_guard,
)

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


# ---------- เส้น 15pp เฉียดแค่ไหน (Phase 48) ----------
#
# A/B ทั้ง 459 แถวที่คำนวณระยะได้ สรุปว่า **ไม่ควรขยับเลข 15**: ลดเหลือ 8 เพื่อให้ MSFT
# (ห่าง 9.78) ติดธง จะลาก SBUX/MA/TSLA (8.26–8.42) ติดไปด้วยทั้งที่ไม่มีหลักฐานว่าพัง และ
# กดคะแนนขาราคาเฉลี่ยทั้งกระดานจาก 1.344 เหลือ 1.173; เพิ่มเป็น 18 จะปลดธง AAPL แล้วยกจาก
# 0.0 เป็น 2.81 ซึ่งคือเคสที่ Phase 42 กันไว้ตั้งแต่แรก
#
# ที่แก้ได้จริงคือ **cliff ตัวนี้มองไม่เห็น**: META เดินที่ 14.12pp มา 24 วันแล้วขยับเป็น
# 17.53pp ข้ามเส้น ระบบสลับ lens ทั้งวิธีโดยหน้าจอไม่บอกว่านี่คือการตัดสินที่เฉียดฉิว


def test_the_margin_says_both_the_verdict_and_how_close_it_was():
    """margin_pp บวก = ติดธง, ลบ = รอด, และขนาดของมันคือ 'เฉียดแค่ไหน' — เลขตัวเดียวตอบสองคำถาม
    เพราะถ้าแยกเป็นสองฟิลด์ คนอ่านจะเห็นแค่ผลลัพธ์แล้วไม่กดดูระยะ (ซึ่งเป็นสิ่งที่เกิดขึ้นจริง)"""
    over = divergence_detail(19.0, revenue_cagr=1.0, fcf_cagr=18.0)   # ห่างสุด 18.0
    under = divergence_detail(19.0, revenue_cagr=12.0, fcf_cagr=18.0)  # ห่างสุด 7.0

    assert (over["worst_distance_pp"], over["margin_pp"], over["diverges"]) == (18.0, 3.0, True)
    assert (under["worst_distance_pp"], under["margin_pp"], under["diverges"]) == (7.0, -8.0, False)


def test_the_reference_that_decided_it_is_named_not_just_the_distance():
    """'ห่าง 18pp' ตอบไม่ได้ว่าอะไรค้าน — รายได้ค้านกับ FCF ค้านนำไปสู่คำถามคนละข้อ."""
    d = divergence_detail(19.0, revenue_cagr=1.0, fcf_cagr=18.0)

    assert d["worst_ref"] == "revenue"
    assert [r["key"] for r in d["refs"]] == ["revenue", "fcf"]
    assert {r["key"]: r["distance_pp"] for r in d["refs"]} == {"revenue": 18.0, "fcf": 1.0}


@pytest.mark.parametrize("worst_ref_value, expect_borderline", [
    (19.0 - (DIVERGENCE_TRIGGER_PP + BORDERLINE_PP - 0.5), True),   # เกินเส้นนิดเดียว
    (19.0 - (DIVERGENCE_TRIGGER_PP - BORDERLINE_PP + 0.5), True),   # เกือบถึงเส้น
    (19.0 - (DIVERGENCE_TRIGGER_PP + BORDERLINE_PP + 2.0), False),  # เกินไปไกล
    (19.0 - (DIVERGENCE_TRIGGER_PP - BORDERLINE_PP - 2.0), False),  # ห่างเส้นสบายๆ
])
def test_borderline_covers_both_sides_of_the_line_not_just_the_flagged_side(
        worst_ref_value, expect_borderline):
    """เฉียดแล้วรอด อันตรายพอๆ กับเฉียดแล้วติด — ทั้งคู่แปลว่าคำตอบแขวนอยู่บนเลข 15 ที่เราตั้งเอง
    ไม่ใช่บนความจริงของธุรกิจ (AAPL +2.26 ติดธงแล้วได้ 0.0/3 คือฝั่งหนึ่ง, MSFT −5.22 คืออีกฝั่ง)"""
    d = divergence_detail(19.0, revenue_cagr=worst_ref_value, fcf_cagr=19.0)

    assert d["borderline"] is expect_borderline


def test_a_direction_conflict_is_never_called_a_close_call():
    """sustainable ติดลบขณะอดีตโตสองหลัก = ขัดกันเชิงทิศทาง เป็นเกณฑ์เชิงประเภท ไม่ใช่เชิงระยะ
    — เรียกว่า 'เฉียด' ไม่ได้ ต่อให้ตัวเลขระยะบังเอิญตกใกล้เส้น 15 พอดี"""
    d = divergence_detail(-1.0, revenue_cagr=13.0, fcf_cagr=None)   # ห่าง 14.0 = ใกล้เส้นมาก

    assert d["direction_conflict"] is True
    assert d["diverges"] is True          # ติดธงเพราะทิศทาง ไม่ใช่เพราะระยะ (14.0 < 15)
    assert d["borderline"] is False


def test_the_reported_verdict_never_disagrees_with_the_flag_that_was_actually_raised():
    """divergence_detail คำนวณซ้ำจากอินพุตชุดเดียวกับ guard — ถ้าวันไหนสองอันนี้ตอบไม่ตรงกัน
    แปลว่าหน้าจอกำลังอธิบายการตัดสินใจที่ระบบไม่ได้ทำ ซึ่งแย่กว่าไม่อธิบายเลย"""
    cases = [
        (19.0, 1.0, 18.0), (19.0, 18.0, 1.0), (19.0, 18.0, 17.0),
        (-1.0, 13.0, None), (5.0, None, 5.5), (30.0, 2.0, 100.0),
    ]
    for sus, rev, fcf in cases:
        detail = divergence_detail(sus, rev, fcf)
        assert detail["diverges"] is _diverges(sus, rev, fcf), (sus, rev, fcf)


def test_no_reference_to_argue_with_means_no_report_rather_than_a_false_all_clear():
    assert divergence_detail(None, revenue_cagr=10.0, fcf_cagr=10.0) is None
    assert divergence_detail(19.0, revenue_cagr=None, fcf_cagr=None) is None
