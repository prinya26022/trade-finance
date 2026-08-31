"""กระดานสรุปหน้าแรก (Phase 43). Offline ล้วน — ฉีด rows เข้าไป ไม่แตะ DB จริง/network.

หน้าที่ของมันคือ **แปลงหน่วย** ให้อ่านแล้วตัดสินใจได้: "ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร"
แทน "ส่วนลด −27%" และเกณฑ์เดียวที่คนอ่านต้องจำคือ **ช่วงคร่อม 100 หรือเปล่า**
"""
import pytest

from datetime import datetime, timedelta

from src.agent.board import (
    STALE_AFTER_DAYS, _age_days, _at_100, _close_call, _verdict, build_board, build_row,
    summary,
)


def _cand(at, *, used=False, rejected=False, capped=False, label=None):
    """candidate ในรูปที่ anchor_agreement คืนมา — `at` คือส่วนลด % (0 = เท่าราคาตลาดพอดี)."""
    return {"label": label or f"วิธี {at}", "growth": 10.0, "discount_pct": at,
            "used": used, "rejected": rejected, "capped": capped}


def _agree(cands, **kw):
    return {"candidates": cands, "narrow_by_cap": False, **kw}


# ---------- การแปลงหน่วย ----------

def test_a_discount_becomes_a_price_out_of_one_hundred():
    """ทั้งฟีเจอร์อยู่ตรงนี้: −27% อ่านไม่ออกว่าแปลว่าอะไร ส่วน 73 อ่านออกทันที."""
    assert _at_100(-27.0) == 73
    assert _at_100(0.0) == 100
    assert _at_100(121.3) == 221
    assert _at_100(None) is None


def test_no_fake_precision_in_the_price():
    """เลขนี้แขวนอยู่บนประมาณการการเติบโต — ทศนิยมคือความแม่นยำปลอม."""
    assert _at_100(-26.8) == 73
    assert isinstance(_at_100(-26.8), int)


# ---------- เกณฑ์ 'คร่อม 100 ไหม' ----------

def test_a_range_entirely_below_the_market_price_reads_as_expensive():
    verdict, note = _verdict(_agree([_cand(-70), _cand(-27, used=True)]), 73)

    assert verdict == "expensive"
    assert "สูงกว่า" in note


def test_a_range_entirely_above_the_market_price_reads_as_cheap():
    verdict, _ = _verdict(_agree([_cand(11), _cand(18, used=True)]), 118)

    assert verdict == "cheap"


def test_a_range_that_crosses_the_market_price_cannot_decide_anything():
    """META ของจริง: ดูรายได้ได้ 68 ดูเงินสดได้ 116 — คำตอบพลิกจากแพงเป็นถูก
    ตามวิธีที่เลือก ตัวเลขแบบนี้ต้องไม่ถูกนำเสนอเป็นข้อสรุป."""
    verdict, note = _verdict(_agree([_cand(-32), _cand(16, used=True)]), 116)

    assert verdict == "straddles"
    assert "ตัดสินใจแทนไม่ได้" in note


# ---------- ตัวที่ดูแน่นแต่แน่นเทียม ----------

def test_anchors_flattened_by_the_growth_cap_are_not_called_agreement():
    """NVDA ของจริง: สามวิธีบอก 194/65/100% ต่อปี แต่ชนเพดานเท่ากันหมดจนออกมาเลขเดียว —
    ถ้าปล่อยให้อ่านว่า 'ทุกวิธีเห็นตรงกัน' หน้าเว็บจะมั่นใจที่สุดตอนที่ควรระวังที่สุด."""
    ag = _agree([_cand(-69, used=True, capped=True), _cand(-69, capped=True)], narrow_by_cap=True)

    verdict, _ = _verdict(ag, 31)

    assert verdict == "capped"


def test_identical_answers_from_every_method_are_treated_as_capped_too():
    """DUOL: สามวิธีให้เลขเดียวกันเป๊ะเพราะโดนกดลงมาชนกัน — ไม่มีอะไรมาตรวจสอบกันเอง."""
    ag = _agree([_cand(121.3, used=True), _cand(121.3), _cand(121.3)])

    verdict, _ = _verdict(ag, 221)

    assert verdict == "capped"


def test_a_single_usable_method_admits_it_has_nothing_to_check_against():
    assert _verdict(None, 90)[0] == "single"
    assert _verdict(_agree([_cand(-20, rejected=True)]), 80)[0] == "single"


# ---------- anchor ที่ถูกตัดทิ้งต้องไม่ถ่วงคำตัดสิน ----------

def test_a_rejected_method_does_not_drag_the_verdict():
    """AAPL ของจริง: มีวิธีเดียวที่ให้ 98 (เกือบเท่าราคาตลาด) และมันคือวิธีที่ guard ตัดทิ้ง
    เพราะขัดกับรายได้ที่โต 1.8%/ปี — ถ้านับมันด้วย AAPL จะกลายเป็น 'พลิกได้ทั้งสองทาง'
    ทั้งที่ทุกวิธีที่ยังใช้ได้เห็นตรงกันหมด."""
    ag = _agree([_cand(-78), _cand(-67, used=True), _cand(-2, rejected=True)])

    verdict, _ = _verdict(ag, 33)

    assert verdict == "expensive"


def test_a_rejected_method_is_still_reported_so_it_can_be_seen():
    """ตัดออกจากคำตัดสิน ไม่ใช่ตัดออกจากสายตา — ซ่อนวิธีที่ไม่ชอบใจคือการทำให้เลขดูมั่นคง
    กว่าที่เป็น (หลักเดียวกับ Phase 41). facts ชุดนี้จำลองทรง DUOL/ADBE: ลูกค้าจ่ายล่วงหน้า
    ทำให้ ΔNWC เป็นบวกมากจน reinvestment ติดลบ -> guard ตัด sustainable ทิ้ง."""
    row = build_row(_row_with(facts=_facts(extra=[
        {"label": "NOPAT", "value": 3.0e10, "unit": "USD", "period": "FY2025"},
        {"label": "ROIC", "value": 20.0, "unit": "%", "period": "TTM"},
        {"label": "Capex", "value": -1.0e9, "unit": "USD", "period": "FY2025"},
        {"label": "D&A", "value": 5.0e9, "unit": "USD", "period": "FY2025"},
        {"label": "NWC Change", "value": 3.0e9, "unit": "USD", "period": "FY2025"},
    ])))

    rejected = [c for c in row["candidates"] if c["rejected"]]

    assert len(rejected) == 1
    assert "โครงสร้าง" in rejected[0]["label"]


# ---------- แถวที่ประกอบไม่ได้ต้องไม่หายไป ----------

def _facts(extra=None):
    """facts ขั้นต่ำที่ reverse_dcf ทำงานได้ — ค่าเลียนแบบบริษัทจริงคร่าวๆ."""
    return [
        {"label": "Market Cap", "value": 1.0e12, "unit": "USD", "period": "TTM"},
        {"label": "FCF Yield", "value": 4.0, "unit": "%", "period": "TTM"},
        {"label": "Revenue", "value": 2.0e11, "unit": "USD", "period": "FY2025"},
        {"label": "Revenue CAGR", "value": 9.0, "unit": "%", "period": "FY2022-FY2025"},
        {"label": "Free Cash Flow", "value": 4.0e10, "unit": "USD", "period": "FY2025"},
        {"label": "Net Debt", "value": 0.0, "unit": "USD", "period": "TTM"},
        {"label": "Beta", "value": 1.0, "unit": "x", "period": "TTM"},
    ] + (extra or [])


def _row_with(**kw):
    """แถว analyses ปลอมหนึ่งแถว."""
    return {"ticker": kw.get("ticker", "TEST"), "run_at": "2026-08-17T10:00:00",
            "health": kw.get("health", {"score": 7.0, "max": 11.0, "tier": "ok", "partial": False}),
            "facts": kw.get("facts", _facts())}


def test_a_row_with_no_stored_facts_still_appears_with_a_reason():
    """หายไปเงียบๆ คือสิ่งที่ Phase 29 กับ 34 แก้มาแล้วสองรอบ — ห้ามเกิดอีกที่นี่."""
    row = build_row({"ticker": "OLD", "run_at": "2026-01-01", "health": {}, "facts": []})

    assert row["ticker"] == "OLD"
    assert row["at_100"] is None
    assert row["note"]


def test_rows_that_cannot_be_priced_sort_to_the_end_but_stay_on_the_board():
    board = build_board(rows=[
        {"ticker": "NOSCORE", "run_at": "2026-08-17", "health": {}, "facts": []},
        _row_with(ticker="GOOD", health={"score": 9.0, "max": 11.0, "tier": "strong", "partial": False}),
    ])

    assert [r["ticker"] for r in board] == ["GOOD", "NOSCORE"]
    assert len(board) == 2


def test_the_board_is_ordered_by_quality_not_by_cheapness():
    """เรียงตามความถูกเมื่อไหร่ ตารางนี้กลายเป็นรายการแนะนำซื้อ — หลักเดียวกับที่ screener
    จงใจไม่เรียงตาม fair_discount_pct ตั้งแต่ Phase 40."""
    board = build_board(rows=[
        _row_with(ticker="LOWQ", health={"score": 4.0, "max": 11.0, "tier": "weak", "partial": False}),
        _row_with(ticker="HIGHQ", health={"score": 10.0, "max": 11.0, "tier": "strong", "partial": False}),
    ])

    assert [r["ticker"] for r in board] == ["HIGHQ", "LOWQ"]


def test_the_score_is_read_from_the_stored_row_not_recomputed():
    """คะแนนต้องเป็นเลขตัวเดียวกับที่ dashboard/ticker/screener โชว์อยู่แล้วเป๊ะ —
    คำนวณใหม่ตรงนี้ = หน้าแรกเถียงกับตัวเองสำหรับแถวที่บันทึกก่อนเอนจิ้นรุ่นปัจจุบัน."""
    row = build_row(_row_with(health={"score": 6.66, "max": 8.0, "tier": "ok", "partial": True}))

    assert (row["score"], row["max"], row["partial"]) == (6.66, 8.0, True)


def test_the_as_of_date_travels_with_the_row():
    """ตัวที่แช่แข็ง/รอบเดือนจะเก่ากว่าตัวอื่นหลายสัปดาห์ — ถ้าไม่บอกวันที่ กระดานจะดูเหมือน
    ทุกตัวสดเท่ากัน ซึ่งไม่จริง."""
    assert build_row(_row_with())["run_at"] == "2026-08-17T10:00:00"


# ---------- สรุปหัวกระดาน ----------

def test_the_summary_counts_how_many_numbers_are_actually_usable():
    board = [
        {"at_100": 118, "verdict": "cheap", "stale": False},
        {"at_100": 73, "verdict": "expensive", "stale": False},
        {"at_100": 116, "verdict": "straddles", "stale": False},
        {"at_100": 31, "verdict": "capped", "stale": False},
        {"at_100": None, "verdict": "none", "stale": False},
    ]

    s = summary(board)

    assert (s["total"], s["priced"], s["usable"], s["cheap"], s["unreliable"]) == (5, 4, 2, 1, 2)


def test_a_bank_is_flagged_as_a_different_ruler_rather_than_compared_head_to_head():
    """JPM −10% กับ MSFT −27% มาจากสูตรคนละตัว วางเทียบกันตรงๆ คืออ่านผิด."""
    verdict, note = _verdict(None, 90)

    assert verdict == "single"   # เลนส์แบงก์ตั้งค่า verdict='bank' เองใน build_row
    bank_row = build_row({"ticker": "JPM", "run_at": "2026-08-17", "health": {}, "facts": [
        {"label": "Market Cap", "value": 9.6e11, "unit": "USD", "period": "TTM"},
        {"label": "Net Interest Income", "value": 9.0e10, "unit": "USD", "period": "FY2025"},
        {"label": "Revenue", "value": 1.8e11, "unit": "USD", "period": "FY2025"},
        {"label": "ROTCE", "value": 20.5, "unit": "%", "period": "TTM"},
        {"label": "P/B", "value": 2.74, "unit": "x", "period": "TTM"},
        {"label": "Beta", "value": 1.0, "unit": "x", "period": "TTM"},
    ]})

    assert bank_row["verdict"] == "bank"
    assert "คนละไม้บรรทัด" in bank_row["note"]


# ---------- Phase 44: "ราคานี้ขออะไร" บนกระดาน ----------

def test_the_board_carries_what_the_price_demands_in_company_size():
    row = build_row(_row_with())

    assert row["asks"] is not None
    assert row["asks"]["revenue_multiple"] > 0
    assert row["asks"]["years"] == 10


def test_the_fcf_multiple_is_kept_even_when_margin_alone_suffices():
    """สองตัวที่ขึ้นว่า 'margin พอแล้ว' เหมือนกันต้องแยกกันออก — SBUX ขอ FCF 4.5 เท่า
    ADBE ขอ 1.5 เท่า คนละน้ำหนักกันมาก ถ้าตัดตัวคูณทิ้งกระดานจะบอกว่าสองตัวนี้เท่ากัน."""
    row = build_row(_row_with(facts=_facts(extra=[
        {"label": "FCF Margin", "value": 0.5, "unit": "%", "period": "TTM"},
    ])))

    assert row["asks"]["margin_alone_enough"] is True
    assert row["asks"]["fcf_multiple"] > 1


def test_a_row_with_no_price_has_no_demand_either():
    row = build_row({"ticker": "OLD", "run_at": "2026-01-01", "health": {}, "facts": []})

    assert row["asks"] is None


# ---------- ข้อมูลเก่า (Phase 47) ----------
#
# ทำไมต้องมีชุดนี้: ticker สถานะ frozen วิเคราะห์แค่ทุก 30 วันโดยตั้งใจ (ประหยัดโควตา Gemini)
# แต่กระดานเคยวาดแถวที่คำนวณจากราคาเมื่อ 27 วันก่อนด้วยน้ำหนักเท่าแถวเมื่อวานเป๊ะ — ตัวเลข
# ที่ถูกต้องแต่เก่า ถูกนำเสนอเป็นตัวเลขที่ถูกต้องและสด ซึ่งเป็นคนละคำกล่าวอ้าง

NOW = datetime(2026, 8, 30, 12, 0, 0)


def _aged(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def test_age_is_counted_in_whole_days_and_never_goes_negative():
    assert _age_days(_aged(0), NOW) == 0
    assert _age_days(_aged(27), NOW) == 27
    # แถวที่บันทึกด้วยนาฬิกาที่เร็วกว่าเครื่องที่อ่าน ไม่ควรกลายเป็นอายุติดลบ
    assert _age_days((NOW + timedelta(hours=6)).isoformat(), NOW) == 0


def test_a_row_with_no_usable_date_is_treated_as_old_not_as_fresh():
    """เดาว่าสดไว้ก่อนคือโหมดพังที่เงียบ — เตือนเกินจำเป็นเห็นได้ ส่วนความสดปลอมมองไม่เห็น."""
    assert _age_days(None, NOW) is None
    assert _age_days("ไม่ใช่วันที่", NOW) is None

    row = build_row({"ticker": "X", "run_at": None, "health": {}, "facts": []}, now=NOW)

    assert row["age_days"] is None
    assert row["stale"] is True


@pytest.mark.parametrize("days, expect_stale", [
    (0, False),
    (STALE_AFTER_DAYS - 1, False),
    (STALE_AFTER_DAYS, True),      # เส้นแบ่งอยู่ที่ ">= " ไม่ใช่ "> "
    (27, True),
])
def test_the_staleness_line_falls_where_the_daily_run_stops_covering_a_ticker(days, expect_stale):
    row = build_row({"ticker": "CVX", "run_at": _aged(days), "health": {}, "facts": []}, now=NOW)

    assert row["age_days"] == days
    assert row["stale"] is expect_stale


def test_an_old_row_is_labelled_but_never_dropped_from_the_usable_count():
    """Phase 29/34 แก้เรื่อง 'ซ่อนของที่ประเมินยาก' มาแล้วสองรอบ — ตรงนี้จึงติดป้าย ไม่ใช่กรองทิ้ง.
    usable ยังนับครบ 3 เหมือนเดิม ส่วน usable_fresh คือตัวที่พูดได้ว่าสดจริง"""
    board = [
        {"at_100": 113, "verdict": "cheap", "stale": False},
        {"at_100": 77, "verdict": "expensive", "stale": False},
        {"at_100": 22, "verdict": "expensive", "stale": True},    # CVX 27 วัน
        {"at_100": None, "verdict": "none", "stale": True},       # ไม่มีราคาให้หลอกใคร
    ]

    s = summary(board)

    assert s["usable"] == 3            # ไม่ถูกตัดออก
    assert s["usable_fresh"] == 2      # แต่แยกออกได้
    assert s["stale"] == 1             # นับเฉพาะแถวที่ *มีราคา* และเก่า
    assert s["stale_after_days"] == STALE_AFTER_DAYS


def test_the_board_stamps_every_row_with_its_age_so_the_ui_never_recomputes_it():
    """ถ้าหน้าเว็บคำนวณอายุเองจาก run_at แถวอาจขึ้น '6 วันก่อน' ขณะที่หัวกระดานนับเป็นเก่าแล้ว
    (คนละ timezone/นาฬิกา) — หน้าเดียวกันเถียงกันเอง จึงส่ง age_days มาจาก server ตัวเดียว"""
    board = build_board(rows=[
        {"ticker": "FRESH", "run_at": _aged(1), "health": {}, "facts": []},
        {"ticker": "OLD", "run_at": _aged(30), "health": {}, "facts": []},
    ], now=NOW)

    by_ticker = {r["ticker"]: r for r in board}
    assert (by_ticker["FRESH"]["age_days"], by_ticker["FRESH"]["stale"]) == (1, False)
    assert (by_ticker["OLD"]["age_days"], by_ticker["OLD"]["stale"]) == (30, True)


# ---------- เฉียดเส้น 15pp (Phase 48) ----------

def test_a_row_that_is_not_close_to_the_line_says_nothing_at_all():
    """เตือนทุกแถว = คำเตือนหมดความหมาย. GOOGL ห่างเส้น 11.8pp ไม่ต้องมีใครมาบอกอะไร."""
    assert _close_call(None) is None
    assert _close_call({"borderline": False, "margin_pp": -11.81}) is None


def test_a_close_call_carries_which_side_of_the_line_it_landed_on():
    """เฉียดแล้วติด กับ เฉียดแล้วรอด นำไปสู่การอ่านคนละแบบ — เก็บ flagged ไว้เสมอ."""
    cc = _close_call({"borderline": True, "margin_pp": 2.26, "worst_distance_pp": 17.26,
                      "trigger_pp": 15.0, "diverges": True, "worst_ref": "revenue"})

    assert cc == {"margin_pp": 2.26, "distance_pp": 17.26, "trigger_pp": 15.0,
                  "flagged": True, "ref": "revenue"}
