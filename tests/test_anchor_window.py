"""หน้าต่างข้อมูลที่ anchor มาจาก (Phase 35). Offline ล้วน — ป้อน series เอง ไม่แตะ SEC/yfinance.

เจอจาก CVX จริง: yfinance คืน 4 ปี และปีแรกคือ FY2022 = ยอดพีคราคาน้ำมันรอบสิบปี ทุกปีหลังจาก
นั้นจึงเป็น "ขาลง" โดยอัตโนมัติ -> realistic growth −11.09% -> ขาราคา 0/3. ประวัติจริง 8 ปี
จาก SEC XBRL บอกว่านั่นคือ *รอบ* ไม่ใช่ธุรกิจถดถอย งานชุดนี้คือการทำให้ความต่างนั้นมองเห็นได้
โดยยังไม่ขยับคะแนนใคร
"""
from src.agent.valuation import _anchor_window
from src.evals.check_anchor_window import check_one, concerning

# ตัวเลขจริงของ CVX (พันล้าน USD)
CVX_LONG = [("FY2018", 159.0), ("FY2019", 140.0), ("FY2020", 94.0), ("FY2021", 156.0),
            ("FY2022", 236.0), ("FY2023", 197.0), ("FY2024", 193.0), ("FY2025", 184.4)]
CVX_SHORT = CVX_LONG[4:]


# ---------- metadata ฝั่ง valuation (ไม่แตะเน็ต ไม่แตะคะแนน) ----------

def test_window_reports_the_years_it_actually_used():
    w = _anchor_window(CVX_SHORT, "fcf")
    assert w["years"] == 4 and w["start"] == "FY2022" and w["end"] == "FY2025"
    assert w["source"] == "fcf"


def test_a_window_that_starts_at_its_own_peak_is_flagged():
    """ทุกปีหลังปีแรกเป็นขาลงโดยอัตโนมัติ = สิ่งที่วัดได้คือระยะห่างจากปีนั้น ไม่ใช่เทรนด์."""
    w = _anchor_window(CVX_SHORT, "fcf")
    assert w["starts_at_max"] is True
    assert "STARTS_AT_WINDOW_HIGH" in w["flags"]


def test_a_window_that_starts_at_its_own_trough_is_flagged_too():
    """อคติเดียวกันแค่กลับทิศ — เริ่มที่ก้นเหวทำให้การเติบโตดูดีเกินจริง."""
    w = _anchor_window([("FY2022", 10.0), ("FY2023", 40.0), ("FY2024", 90.0)], "fcf")
    assert w["starts_at_min"] is True
    assert "STARTS_AT_WINDOW_LOW" in w["flags"]


def test_series_ordering_does_not_change_the_answer():
    """fcf_series มาถึงทั้งเรียงเก่า->ใหม่ และใหม่->เก่า แล้วแต่พาธ (บั๊กซ้ำซากของโปรเจกต์นี้)."""
    assert _anchor_window(CVX_SHORT, "fcf") == _anchor_window(list(reversed(CVX_SHORT)), "fcf")


def test_an_empty_or_single_point_series_reports_nothing_instead_of_guessing():
    w = _anchor_window([("FY2025", 1.0)], "fcf")
    assert w["years"] == 1 and w["flags"] == [] and w["start"] is None


# ---------- eval ที่เทียบกับประวัติยาว ----------

def test_the_cvx_case_end_to_end():
    r = check_one("CVX", short_series=CVX_SHORT, long_series=CVX_LONG)
    assert r["short"]["cagr"] < 0                       # หน้าต่างสั้นบอกว่าถดถอย
    assert r["long"]["cagr"] > 0                        # ประวัติเต็มบอกว่าโต
    assert "TREND_SIGN_FLIPS_ON_LONGER_WINDOW" in r["flags"]
    assert "WINDOW_STARTS_AT_CYCLE_HIGH" in r["flags"]
    assert concerning(r)


def test_histories_that_never_overlap_are_refused_not_compared():
    """บั๊กที่ eval นี้เคยมีเอง: NVDA มี XBRL ถึง FY2022 แต่ yfinance เริ่ม FY2023 = ไม่เคยทับกัน
    แล้วมันรายงานว่า '4 ปี +100% เทียบ 6 ปี +31%' ราวกับเป็นเทรนด์เดียวกันวัดยาวขึ้น.
    ไม่มีปีทับกัน = ยืนยันไม่ได้ว่าสองแหล่งพูดถึงอนุกรมเดียวกัน (กติกาเดียวกับฝั่ง anchor)"""
    old = [("FY2017", 6.9), ("FY2018", 9.7), ("FY2019", 11.7)]
    new = [("FY2023", 27.0), ("FY2024", 60.9), ("FY2025", 130.5)]
    r = check_one("NVDA", short_series=new, long_series=old)

    assert "NO_OVERLAP_TO_VERIFY" in r["flags"]
    assert r["long"] is None                            # ไม่คำนวณ CAGR ที่เทียบไม่ได้ออกมาเลย
    assert r["cagr_gap_pp"] is None


def test_a_missing_year_in_the_middle_is_reported_but_still_compared():
    """AAPL ไม่มี FY2014 (แท็กบัญชีเปลี่ยนปีนั้น) — CAGR คิดจากช่วงปีจริงจึงยังถูก ไม่ต้องทิ้งทั้งชุด."""
    long = [("FY2012", 40.0), ("FY2013", 45.0), ("FY2015", 70.0), ("FY2016", 53.0),
            ("FY2017", 51.0), ("FY2018", 64.0), ("FY2019", 59.0)]
    short = [("FY2017", 51.0), ("FY2018", 64.0), ("FY2019", 59.0)]
    r = check_one("AAPL", short_series=short, long_series=long)

    assert "HISTORY_HAS_GAP" in r["flags"]
    assert r["long"]["cagr"] is not None                # ยังเทียบได้ ไม่ปฏิเสธทิ้ง
    assert r["long"]["years"] == 7


def test_newer_years_missing_from_xbrl_are_merged_in_not_dropped():
    """XBRL ตามหลังเสมอ (ยื่นปีละครั้ง) — ประวัติเต็มต้อง = ยาว + ปีใหม่ที่ provider มี."""
    long = CVX_LONG[:-1]                                 # XBRL ยังไม่มี FY2025
    r = check_one("CVX", short_series=CVX_SHORT, long_series=long)
    assert r["long"]["end"] == "FY2025" and r["long"]["years"] == 8


def test_a_company_whose_longer_window_agrees_is_not_flagged():
    """ธงที่ติดทุกตัวคือธงที่ไม่มีความหมาย — MSFT/META ต้องเงียบ."""
    long = [(f"FY{y}", 100.0 * (1.14 ** (y - 2016))) for y in range(2016, 2027)]
    r = check_one("MSFT", short_series=long[-4:], long_series=long)
    assert not concerning(r)
    assert "SHORT_WINDOW" in r["flags"]                  # ยังบอกความจริง แค่ไม่ตีเป็นสัญญาณ


def test_no_long_history_says_so_rather_than_implying_agreement():
    """XOM เจอจริง — เงียบแล้วดูปกติคือสิ่งที่โปรเจกต์นี้ไล่แก้มาทั้งชุด."""
    r = check_one("XOM", short_series=CVX_SHORT, long_series=[])
    assert "NO_LONG_HISTORY" in r["flags"]
    assert r["note"] and r["long"] is None


def test_the_check_detects_the_opposite_bias_too():
    """หน้าต่างที่เริ่มก้นเหวทำให้โตเกินจริง — ต้องจับได้เหมือนกัน ไม่ใช่จับแค่ขาลง."""
    long = [("FY2019", 100.0), ("FY2020", 95.0), ("FY2021", 40.0),
            ("FY2022", 45.0), ("FY2023", 90.0), ("FY2024", 140.0)]
    r = check_one("X", short_series=long[2:], long_series=long)
    assert "WINDOW_STARTS_AT_CYCLE_LOW" in r["flags"]
    assert r["short"]["cagr"] > r["long"]["cagr"]
    assert concerning(r)


def test_adjoining_but_never_overlapping_is_still_refused():
    """ต่อกันสนิทไม่พอ — ถ้าไม่เคยมีปีที่ทับกันเลย ก็ยังยืนยันไม่ได้ว่าสองแหล่งวัดของสิ่งเดียวกัน
    (ตัวเลขอาจคนละนิยาม แล้วรอยต่อจะกลายเป็น 'การเติบโต' ที่ไม่มีจริง)"""
    old = [("FY2019", 60.0), ("FY2020", 70.0), ("FY2021", 85.0), ("FY2022", 100.0)]
    new = [("FY2023", 110.0), ("FY2024", 125.0), ("FY2025", 140.0)]
    r = check_one("OK", short_series=new, long_series=old)
    assert "NO_OVERLAP_TO_VERIFY" in r["flags"]


def test_one_overlapping_year_is_enough_to_verify_and_compare():
    """ทับกันปีเดียวก็พิสูจน์ได้ว่าเป็นอนุกรมเดียวกัน — ไม่ต้องเข้มเกินจนใช้งานไม่ได้."""
    old = [("FY2019", 60.0), ("FY2020", 70.0), ("FY2021", 85.0), ("FY2022", 100.0)]
    new = [("FY2022", 100.0), ("FY2023", 110.0), ("FY2024", 125.0), ("FY2025", 140.0)]
    r = check_one("OK", short_series=new, long_series=old)
    assert "NO_OVERLAP_TO_VERIFY" not in r["flags"]
    assert r["long"]["years"] == 7 and r["long"]["cagr"] is not None
