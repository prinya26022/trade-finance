"""ความมั่นใจในราคาที่คุ้มค่า (Phase 41). Offline ล้วน.

Phase 40 โชว์ `pct_per_pp` ("ราคาขยับกี่ % ถ้า growth พลาด 1pp") ในฐานะตัววัดว่า "ควรเชื่อ
ส่วนลดข้างหน้าแค่ไหน". วัดจริงกับ watchlist ทั้งชุดแล้วพบว่า **มันวัดไม่ได้**: ความยืดหยุ่นของ
EV ต่อ growth แทบคงที่ทุกบริษัท ดังนั้น pct_per_pp ≈ 7 × (ราคาที่คุ้มค่า ÷ ราคาตลาด) = เลข
เดียวกับส่วนลดที่พิมพ์อยู่ข้างๆ มันเอง. "DUOL ไวกว่า AAPL 6 เท่า" จึงเป็นความจริงเชิงกลไก
ไม่ใช่ข้อความเรื่องความยากในการประเมินสองธุรกิจนั้น

ความเปราะจริงคือ **การเลือก anchor** — เรามีวิธีวัดการเติบโตหลายทางที่มีเหตุผลพอกัน ถ้าทุกทาง
ตอบใกล้กันคำตอบมั่นคง ถ้าตอบคนละเรื่องคำตอบคือเหรียญที่โยนไปแล้วหนึ่งครั้ง
"""
import pytest

from src.agent.valuation import (
    ANCHOR_LABELS,
    anchor_agreement,
    anchor_realistic,
    fair_value,
    growth_lens_realistic,
    intrinsic_value,
)

DCF = {"realistic_growth": 8.0, "ev": 1.0e12, "fcf_base": 4.0e10,
       "wacc": 10.0, "terminal_growth": 2.5, "years": 10, "flags": []}
MCAP = 9.0e11        # net debt = ev - mcap = 1.0e11


# ---------- เหตุผลที่ฟีเจอร์นี้มีอยู่: pct_per_pp วัดความเปราะไม่ได้ ----------

def test_sensitivity_is_almost_entirely_explained_by_the_discount_next_to_it():
    """ข้อค้นพบที่ทำให้ต้องสร้าง Phase 41 — ปักหมุดไว้เป็นเทสต์เพราะถ้าวันหลังมันไม่จริงแล้ว
    (เช่นเปลี่ยน horizon/terminal growth จนความยืดหยุ่นกระจายตัว) เหตุผลของฟีเจอร์นี้เปลี่ยน
    ตามไปด้วย และเราควรรู้ตอนนั้น ไม่ใช่รู้ตอนอ่านหน้าเว็บผิดไปแล้วครึ่งปี."""
    for growth, mcap in ((2.0, 4.0e11), (8.0, 9.0e11), (20.0, 2.0e12), (30.0, 3.0e12)):
        fv = fair_value({**DCF, "realistic_growth": growth, "ev": mcap + 1.0e11}, mcap)
        predicted = 7.0 * (fv["market_cap"] / mcap)

        assert predicted == pytest.approx(fv["pct_per_pp"], rel=0.25)


# ---------- ตัวที่วัดได้จริง ----------

def test_anchors_that_all_say_the_same_thing_give_a_narrow_answer():
    ag = anchor_agreement(DCF, MCAP, {"sustainable": 8.5, "fcf": 8.2, "revenue_cagr": 7.9}, "sustainable")

    assert ag["level"] == "narrow"
    assert ag["discount_spread_pp"] < 25.0


def test_anchors_that_contradict_each_other_give_a_wide_answer():
    """MSFT ของจริง: โครงสร้างบอก 17.2%/ปี ประวัติ FCF บอก 3-5%/ปี — ส่วนลดวิ่ง -27% ถึง -74%
    ทั้งที่หน้าเว็บโชว์ตัวเลขเดียวอย่างมั่นใจ."""
    ag = anchor_agreement(DCF, MCAP, {"sustainable": 20.0, "fcf": 2.0, "revenue_cagr": 3.0}, "sustainable")

    assert ag["level"] == "wide"
    assert ag["discount_hi"] - ag["discount_lo"] > 60.0


def test_the_range_is_the_range_of_prices_not_of_growth_rates():
    """ประโยชน์ทั้งหมดอยู่ตรงที่มันอยู่ในหน่วยราคา — growth spread 15pp ไม่บอกอะไรกับใคร."""
    raw = {"sustainable": 18.0, "fcf": 3.0}
    ag = anchor_agreement(DCF, MCAP, raw, "sustainable")

    both = [fair_value({**DCF, "realistic_growth": anchor_realistic(k, v, 0.025, 10)}, MCAP)["discount_pct"]
            for k, v in raw.items()]

    assert ag["discount_lo"] == min(both)
    assert ag["discount_hi"] == max(both)


def test_each_anchor_is_faded_by_its_own_familys_rules_before_comparing():
    """เทียบ anchor ที่ผ่าน fade แล้วกับ anchor ดิบ = เทียบคนละหน่วยความหมาย. sustainable โดน
    cap ที่ 20% ส่วนฝั่งประวัติโดน growth_lens_realistic เหมือนตอน reverse_dcf เลือกจริง."""
    assert anchor_realistic("sustainable", 45.0, 0.025, 10) == 20.0
    assert anchor_realistic("fcf", 45.0, 0.025, 10) == growth_lens_realistic(45.0, 0.025, 10)


def test_the_anchor_actually_used_is_marked_so_you_can_see_where_you_stand_in_the_range():
    ag = anchor_agreement(DCF, MCAP, {"sustainable": 18.0, "fcf": 3.0}, "sustainable")

    used = [c for c in ag["candidates"] if c["used"]]

    assert [c["source"] for c in used] == ["sustainable"]
    assert ag["used_discount_pct"] == ag["discount_hi"]


def test_it_says_out_loud_when_the_anchor_we_picked_is_the_most_generous_one():
    """วัดจริง 11/13 ตัวใน watchlist เป็นแบบนี้ — ส่วนลดที่เห็นจึงเป็น 'ขอบที่ดีที่สุด' ของช่วง
    ไม่ใช่จุดกึ่งกลาง ซึ่งเป็นคนละเรื่องกันมากเวลาอ่าน."""
    generous = anchor_agreement(DCF, MCAP, {"sustainable": 18.0, "fcf": 3.0}, "sustainable")
    conservative = anchor_agreement(DCF, MCAP, {"sustainable": 18.0, "fcf": 3.0}, "fcf")

    assert generous["used_is_most_generous"] is True
    assert conservative["used_is_most_generous"] is False


def test_the_gap_between_business_structure_and_measured_history_is_reported_separately():
    """ต้นตอของช่วงกว้างเกือบทุกเคสที่วัดมา — สองครอบครัวนี้ตอบคนละคำถาม การไม่ตรงกันคือข้อมูล."""
    ag = anchor_agreement(DCF, MCAP, {"sustainable": 18.0, "fcf": 4.0, "revenue_cagr": 6.0}, "sustainable")

    hist = [c["growth"] for c in ag["candidates"] if c["family"] == "history"]
    st = next(c["growth"] for c in ag["candidates"] if c["family"] == "structure")

    assert ag["structure_vs_history_pp"] == pytest.approx(st - sum(hist) / len(hist), abs=0.01)


def test_an_anchor_the_guard_threw_out_is_still_listed_but_marked_as_thrown_out():
    """ซ่อน anchor ที่เราไม่ชอบใจออกจากช่วง = ทำให้เลขดูมั่นคงกว่าที่เป็น. DUOL ของจริง:
    sustainable ติดลบเพราะ deferred revenue ทำให้ reinvestment ติดลบ ซึ่ง Phase 18 พิสูจน์แล้ว
    ว่าเป็นสูตรที่พังกับธุรกิจแบบนี้ — ต้องเห็นว่ามีอยู่ และเห็นว่าทำไมถึงไม่ถูกเลือก."""
    dcf = {**DCF, "flags": ["NEGATIVE_REINVESTMENT"]}
    ag = anchor_agreement(dcf, MCAP, {"sustainable": -9.0, "fcf": 18.0}, "fcf")

    rejected = [c for c in ag["candidates"] if c["rejected"]]

    assert [c["source"] for c in rejected] == ["sustainable"]
    assert ag["discount_lo"] == min(c["discount_pct"] for c in ag["candidates"])


def test_history_anchors_are_never_marked_rejected_even_when_flags_are_set():
    """ธงทุกตัวใน valuation_guard พูดถึง sustainable ล้วน — ติดธง rejected ให้ฝั่งประวัติด้วย
    จะกลายเป็น 'ทุก anchor ถูกปฏิเสธ' ซึ่งไม่จริงและอ่านไม่ได้ความ."""
    dcf = {**DCF, "flags": ["SUSTAINABLE_DIVERGES"]}
    ag = anchor_agreement(dcf, MCAP, {"sustainable": 2.0, "fcf": 18.0, "revenue_cagr": 17.0}, "fcf")

    assert [c["rejected"] for c in ag["candidates"] if c["family"] == "history"] == [False, False]


# ---------- ช่วงแคบเทียมจากเพดาน ----------

def test_anchors_flattened_by_the_growth_cap_do_not_count_as_agreement():
    """NVDA ของจริง: ประวัติ FCF บอก 193.9%/ปี รายได้ปีล่าสุดบอก 65.5% รายได้ CAGR บอก 100.1%
    — คนละโลกกันทั้งสามตัว แต่ทุกตัวชนเพดาน 35% แล้ว fade ออกมาเป็น 18.29% เท่ากันเป๊ะ ช่วงจึง
    แคบเหลือ 10.7pp และดูเหมือน 'ทุกวิธีเห็นตรงกัน'. ความแคบนั้นเป็นสมบัติของกติกาเรา ไม่ใช่
    หลักฐานเรื่องบริษัท — ถ้าไม่บอก มันจะเป็นตัวเลขที่ยิ่งมั่นใจตอนที่ยิ่งควรระวัง."""
    ag = anchor_agreement(
        DCF, MCAP, {"fcf": 193.9, "revenue_recent": 65.5, "revenue_cagr": 100.1}, "fcf")

    assert ag["level"] == "narrow"
    assert ag["capped_count"] == 3
    assert ag["narrow_by_cap"] is True


def test_genuine_agreement_is_not_flagged_as_capped():
    ag = anchor_agreement(DCF, MCAP, {"fcf": 8.2, "revenue_cagr": 7.9, "revenue_recent": 8.0}, "fcf")

    assert ag["capped_count"] == 0
    assert ag["narrow_by_cap"] is False


def test_a_wide_range_is_never_called_narrow_by_cap_even_with_capped_anchors():
    """DUOL: ประวัติสามตัวชนเพดานหมดเหมือน NVDA แต่ sustainable ติดลบดึงช่วงให้กว้างจริง —
    ความกว้างตรงนั้นเป็นของจริง ไม่ต้องมีคำเตือนเรื่องเพดานมาแย่งความสนใจ."""
    ag = anchor_agreement(DCF, MCAP, {"sustainable": -8.9, "fcf": 102.3, "revenue_cagr": 41.1}, "fcf")

    assert ag["level"] == "wide"
    assert ag["capped_count"] == 2
    assert ag["narrow_by_cap"] is False


# ---------- ไม่มีสิทธิ์พูดเรื่องความมั่นใจตอนที่ไม่มีอะไรให้เทียบ ----------

def test_one_anchor_alone_means_no_opinion_about_confidence():
    assert anchor_agreement(DCF, MCAP, {"fcf": 8.0}, "fcf") is None
    assert anchor_agreement(DCF, MCAP, {"fcf": 8.0, "revenue_cagr": None}, "fcf") is None


def test_no_price_means_no_range():
    assert anchor_agreement(DCF, None, {"sustainable": 8.0, "fcf": 3.0}, "fcf") is None
    assert anchor_agreement(DCF, 0.0, {"sustainable": 8.0, "fcf": 3.0}, "fcf") is None


def test_a_dcf_without_the_model_constants_gets_no_range_rather_than_a_guessed_one():
    assert anchor_agreement({**DCF, "years": None}, MCAP, {"sustainable": 8.0, "fcf": 3.0}, "fcf") is None
    assert anchor_agreement({}, MCAP, {"sustainable": 8.0, "fcf": 3.0}, "fcf") is None


def test_every_anchor_source_has_a_thai_label():
    """ไม่มีป้ายไทย = หน้าเว็บโชว์ชื่อ field ดิบ ซึ่งอ่านไม่ออกว่าตัวเลขมาจากไหน."""
    ag = anchor_agreement(
        DCF, MCAP,
        {"sustainable": 9.0, "fcf_long": 8.0, "fcf": 7.0, "revenue_recent": 6.0, "revenue_cagr": 5.0},
        "sustainable",
    )

    assert {c["source"] for c in ag["candidates"]} == set(ANCHOR_LABELS)
    assert all(c["label"] != c["source"] for c in ag["candidates"])


def test_the_candidates_use_the_same_model_as_the_score_not_a_second_formula():
    """บั๊กประจำของโปรเจกต์: ตรรกะเดียวกันถูกเขียนสองที่แล้วตอบไม่ตรงกัน (33.3, 34, 39)."""
    ag = anchor_agreement(DCF, MCAP, {"sustainable": 12.0, "fcf": 4.0}, "sustainable")
    row = next(c for c in ag["candidates"] if c["source"] == "sustainable")

    expected_mcap = intrinsic_value(DCF["fcf_base"], 0.12, 0.10, 0.025, 10) - 1.0e11

    assert row["discount_pct"] == pytest.approx((expected_mcap / MCAP - 1) * 100, abs=0.1)
