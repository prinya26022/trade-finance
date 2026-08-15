"""สมุดพกของเอเจนต์เอง (Phase 32) — ฉีดประวัติปลอม ไม่แตะ DB/yfinance/Gemini.

หัวใจที่ต้องพิสูจน์: การแยก 'คะแนนขยับเพราะธุรกิจ' ออกจาก 'คะแนนขยับเพราะข้อมูลฝั่งเรา' ต้องแม่น
เพราะทั้งฟีเจอร์มีค่าก็ต่อเมื่อมันกล้าชี้ว่าคะแนนของเราเองเชื่อไม่ได้ — ถ้าแยกพลาดไปทาง 'ธุรกิจ'
มันจะกลายเป็นเครื่องรับรองตัวเองที่บอกว่าทุกอย่างปกติดี ซึ่งแย่กว่าไม่มีเลย.
"""
from datetime import date, timedelta

from src.agent.scorecard import (
    NOISE_POINTS,
    attribute,
    forward_performance,
    readiness,
    snapshots,
    stability,
    stability_report,
)
from src.agent.valuation import _gap_to_score

FULL = [["ROIC>WACC", 1.0], ["Net Margin", 1.0], ["FCF+คุณภาพกำไร", 1.0]]


def _health(criteria, implied=None, realistic=None, lens="standard", max_=11.0, penalty=0.0,
            anchor=None):
    """health dict รูปแบบเดียวกับที่ health.py เขียนลง health_reasons_json จริง."""
    f = sum(v for _, v in criteria if v is not None)
    val = None
    vs = 0.0
    if implied is not None and realistic is not None:
        vs = _gap_to_score(implied - realistic)
        val = {"score": vs, "excluded": False, "implied_growth": implied,
               "realistic_growth": realistic, "lens": lens}
        if anchor:      # Phase 36: แหล่งของ anchor ('fcf' สั้น / 'fcf_long' จากงบที่ยื่น ก.ล.ต.)
            val["anchor_window"] = {"source": anchor}
    return {
        "score": round(f + vs - penalty, 2),
        "max": max_,
        "fundamental": {"criteria": criteria, "score": f,
                        "computable": sum(1 for _, v in criteria if v is not None)},
        "valuation": val,
    }


def _snap(ticker, day, health, price=100.0, engine=None):
    """snapshot รูปแบบหลัง snapshots() แปลงแล้ว (ที่ stability/readiness รับเข้าไป)."""
    return {"ticker": ticker, "date": day, "run_at": f"{day}T10:00:00", "price": price,
            "score": health["score"], "max": health["max"], "engine": engine, "health": health}


# ---------------------------------------------------------------- การแยกที่มา

def test_criterion_becoming_computable_is_data_not_business():
    """เคสจริงที่จุดชนวนฟีเจอร์นี้: MSFT 6.3 -> 9.1 ใน 26 วัน ส่วนหนึ่งเพราะเกณฑ์ FCF พลิกจาก
    null เป็น 1.0 — ธุรกิจไม่ได้เปลี่ยน แค่ข้อมูลฝั่งเรามาครบขึ้น. ถ้าอันนี้ถูกนับเป็น business
    สมุดพกจะรับรองว่าคะแนนน่าเชื่อถือทั้งที่มันเลื่อนเพราะตัวเอง."""
    prev = _health([["ROIC>WACC", 1.0], ["FCF+คุณภาพกำไร", None]])
    cur = _health([["ROIC>WACC", 1.0], ["FCF+คุณภาพกำไร", 1.0]])

    a = attribute(prev, cur)

    assert a["total"] == 1.0
    assert a["buckets"]["data"] == 1.0
    assert a["buckets"]["business"] == 0.0
    assert "เพิ่งคำนวณได้" in a["notes"][0]


def test_criterion_value_moving_is_business():
    prev = _health([["ROIC>WACC", 1.0], ["Margin ขยาย", 0.2]])
    cur = _health([["ROIC>WACC", 1.0], ["Margin ขยาย", 0.9]])

    a = attribute(prev, cur)

    assert a["buckets"]["business"] == 0.7
    assert a["buckets"]["data"] == 0.0


def test_criterion_going_uncomputable_is_data_too():
    """ASML ของจริงพลิกไปกลับวันเว้นวัน — ทิศลบก็ต้องเข้าถัง data เหมือนกัน ไม่ใช่ 'ธุรกิจแย่ลง'."""
    prev = _health([["FCF+คุณภาพกำไร", 1.0]])
    cur = _health([["FCF+คุณภาพกำไร", None]])

    assert attribute(prev, cur)["buckets"]["data"] == -1.0


def test_price_move_attributed_to_price_not_estimate():
    """ราคาขยับ -> implied growth ขยับ: ขา valuation ออกแบบมาให้ตอบสนองแบบนี้ ถือว่าปกติ."""
    prev = _health(FULL, implied=14.0, realistic=8.0)
    cur = _health(FULL, implied=9.0, realistic=8.0)      # gap แคบลงเพราะราคาลง

    a = attribute(prev, cur)

    assert a["buckets"]["price"] > 0
    assert a["buckets"]["estimate"] == 0.0
    assert a["buckets"]["business"] == 0.0


def test_estimate_revision_attributed_to_estimate():
    """gap แคบลงเท่ากันเป๊ะ แต่คราวนี้เพราะเราแก้ประมาณการตัวเอง ไม่ใช่ตลาดขยับ — ต้องคนละถัง."""
    prev = _health(FULL, implied=14.0, realistic=8.0)
    cur = _health(FULL, implied=14.0, realistic=13.0)

    a = attribute(prev, cur)

    assert a["buckets"]["estimate"] > 0
    assert a["buckets"]["price"] == 0.0
    assert any("realistic growth" in n for n in a["notes"])


def test_lens_change_goes_entirely_to_data():
    """เทียบ gap ข้าม lens = เทียบคะแนนสอบคนละข้อสอบ — ห้ามแกล้งแยกเป็นราคา/ประมาณการ."""
    prev = _health(FULL, implied=14.0, realistic=8.0, lens="growth")
    cur = _health(FULL, implied=14.0, realistic=13.0, lens="standard")

    a = attribute(prev, cur)

    assert a["buckets"]["data"] == a["total"] != 0
    assert a["buckets"]["price"] == a["buckets"]["estimate"] == 0.0
    assert any("lens" in n for n in a["notes"])


def test_buckets_always_sum_to_total():
    """invariant: ส่วนที่อธิบายไม่ได้ต้องโผล่ที่ 'other' ไม่ใช่หายไปเพื่อให้ตัวเลขลงตัว
    (ที่นี่คือ breach penalty ซึ่งไม่ได้อยู่ในทั้งขาพื้นฐานและขา valuation)."""
    prev = _health(FULL, implied=14.0, realistic=8.0)
    cur = _health(FULL, implied=9.0, realistic=13.0, penalty=0.5)

    a = attribute(prev, cur)

    assert round(sum(a["buckets"].values()), 2) == a["total"]
    assert a["buckets"]["other"] == -0.5


def test_basis_change_is_not_silently_bucketed():
    """/8 (partial) เทียบ /11 คนละฐาน — ต้องบอกว่าเทียบไม่ได้ ไม่ใช่รายงานว่าคะแนนตก 3 จุด."""
    prev = _health(FULL, implied=9.0, realistic=8.0)
    cur = _health(FULL, max_=8.0)

    a = attribute(prev, cur)

    assert a["basis_changed"] is True
    assert a["buckets"]["business"] == 0.0


# ---------------------------------------------------------------- ความนิ่ง

def test_oscillation_is_caught_even_when_start_equals_end():
    """กับดักหลักของการวัดแบบหัว-ท้าย: คะแนนวิ่งขึ้น 1 แล้วลงกลับ 1 คืออาการไม่นิ่งที่สุด
    แต่ net = 0 จะดูนิ่งที่สุดในตาราง — ต้องวัดสะสมทีละคู่."""
    snaps = [
        _snap("X", "2026-07-01", _health([["FCF", None], ["ROIC>WACC", 1.0]])),
        _snap("X", "2026-07-02", _health([["FCF", 1.0], ["ROIC>WACC", 1.0]])),
        _snap("X", "2026-07-03", _health([["FCF", None], ["ROIC>WACC", 1.0]])),
    ]
    s = stability(snaps)

    assert s["first_score"] == s["last_score"]
    assert s["net"]["data"] == 0.0
    assert s["gross"]["data"] == 2.0
    assert s["unexplained"] == 2.0
    assert s["trustworthy"] is False


def test_business_and_price_movement_stays_trustworthy():
    """ต้องไม่ตั้งธงมั่ว — ธุรกิจดีขึ้นและราคาขยับคือสิ่งที่คะแนน 'ควร' ตอบสนอง."""
    snaps = [
        _snap("Y", "2026-07-01", _health([["ROIC>WACC", 0.2]], implied=14.0, realistic=8.0)),
        _snap("Y", "2026-07-02", _health([["ROIC>WACC", 1.0]], implied=9.0, realistic=8.0)),
    ]
    s = stability(snaps)

    assert s["gross"]["business"] == 0.8
    assert s["gross"]["price"] > 0
    assert s["unexplained"] == 0.0
    assert s["trustworthy"] is True


def test_basis_flipping_is_untrustworthy_despite_zero_unexplained():
    """MA ของจริง: แกว่ง 2 จุดเพราะพลิก /8 <-> /11 แต่ delta ตกไปอยู่ถัง other ทั้งก้อน
    ถ้าดูแค่ unexplained ตัวที่พลิกฐานบ่อยสุดจะกลายเป็นตัวที่ 'นิ่งที่สุด'."""
    snaps = [
        _snap("MA", "2026-07-01", _health(FULL, implied=9.0, realistic=8.0)),
        _snap("MA", "2026-07-02", _health(FULL, max_=8.0)),
    ]
    s = stability(snaps)

    assert s["unexplained"] == 0.0
    assert s["basis_changes"] == 1
    assert s["trustworthy"] is False


def test_single_snapshot_has_nothing_to_compare():
    assert stability([_snap("Z", "2026-07-01", _health(FULL))]) is None


def test_report_ranks_worst_first_and_counts_flagged():
    noisy = [_snap("N", f"2026-07-0{i}", _health([["FCF", 1.0 if i % 2 else None]])) for i in (1, 2, 3)]
    calm = [_snap("C", f"2026-07-0{i}", _health([["ROIC>WACC", 1.0]])) for i in (1, 2)]

    rep = stability_report({"N": noisy, "C": calm})

    assert [r["ticker"] for r in rep["rows"]] == ["N", "C"]
    assert rep["flagged"] == 1 and rep["total"] == 2
    assert "N" in rep["headline"]


def test_same_day_reruns_collapse_to_one_point():
    """รันมือซ้ำในวันเดียวไม่ใช่ 'คะแนนขยับ' — ถ้านับทุกรอบ pair ที่ delta=0 จะถ่วงให้ดูนิ่งเกินจริง."""
    rows = [
        {"ticker": "A", "run_at": "2026-07-01T09:00:00", "price": 1, "health": _health([["ROIC>WACC", 0.1]])},
        {"ticker": "A", "run_at": "2026-07-01T20:00:00", "price": 1, "health": _health([["ROIC>WACC", 0.9]])},
    ]
    snaps = snapshots(rows)["A"]

    assert len(snaps) == 1
    assert snaps[0]["score"] == 0.9      # ใช้รอบล่าสุดของวัน


def test_rows_without_health_are_skipped():
    """แถวก่อน Phase 10 และตัวที่ excluded (คริปโต/แบงก์) ไม่มีอะไรให้เทียบ — ต้องไม่ระเบิด."""
    rows = [
        {"ticker": "BTC", "run_at": "2026-07-01T09:00:00", "price": 1, "health": None},
        {"ticker": "JPM", "run_at": "2026-07-01T09:00:00", "price": 1,
         "health": {"score": None, "max": 11.0, "fundamental": {}}},
        {"ticker": "A", "run_at": "2026-07-01T09:00:00", "price": 1, "health": _health(FULL)},
    ]
    assert set(snapshots(rows)) == {"A"}


# ---------------------------------------------------------------- ทำนายได้ไหม

def test_readiness_says_not_yet_and_counts_the_wait():
    """ประวัติ 26 วันตอบคำถาม 90 วันไม่ได้ — ต้องบอกว่ารออีกกี่วัน ไม่ใช่คืนสถิติจาก 0 ตัวอย่าง."""
    today = date(2026, 8, 2)
    snaps = {"A": [_snap("A", "2026-07-06", _health(FULL))]}

    r = readiness(snaps, today=today)

    assert r["ready"] is False
    h90 = next(h for h in r["horizons"] if h["days"] == 90)
    assert h90["eligible"] == 0
    assert h90["days_to_first"] == 63
    assert h90["first_at"] == "2026-10-04"


def test_readiness_turns_ready_once_a_snapshot_is_old_enough():
    today = date(2026, 8, 2)
    snaps = {"A": [_snap("A", "2026-01-01", _health(FULL))]}

    h90 = next(h for h in readiness(snaps, today=today)["horizons"] if h["days"] == 90)

    assert h90["ready"] is True and h90["eligible"] == 1


def test_forward_performance_measures_excess_over_benchmark():
    """ตลาดขาขึ้นทำให้ทุกกลุ่มดูดีเท่ากัน — ต้องหักด้วย benchmark ถึงจะตอบว่าคะแนน 'แยกของ' ได้ไหม.
    ที่นี่หุ้น +20% แต่ benchmark +15% -> ส่วนต่างจริงคือ +5 ไม่ใช่ +20."""
    today = date(2026, 8, 2)
    strong = _health([["a", 1.0], ["b", 1.0], ["c", 1.0], ["d", 1.0], ["e", 1.0], ["f", 1.0],
                      ["g", 1.0], ["h", 1.0]], implied=1.0, realistic=8.0)
    assert strong["score"] >= 9.0

    snaps = {"A": [_snap("A", "2026-01-01", strong)]}
    prices = {"A": [("2026-01-01", 100.0), ("2026-04-01", 120.0)],
              "VT": [("2026-01-01", 100.0), ("2026-04-01", 115.0)]}

    out = forward_performance(snaps, prices, today=today)
    h90 = next(h for h in out if h["days"] == 90)

    assert h90["n"] == 1
    assert h90["bands"][0]["excess"] == 5.0
    assert "9-11" in h90["bands"][0]["band"]


def test_forward_performance_ignores_snapshots_inside_the_horizon():
    """กับดัก look-ahead: จุดที่เพิ่งเกิดเมื่อวานจะได้ผลตอบแทน ~0 เสมอ ถ้านับด้วยสถิติจะถูกถ่วง
    เข้าหาศูนย์จนสรุปว่า 'คะแนนไม่มีความหมาย' ทั้งที่จริงคือเรายังไม่ได้รอ."""
    today = date(2026, 8, 2)
    snaps = {"A": [_snap("A", "2026-08-01", _health(FULL, implied=1.0, realistic=8.0))]}
    prices = {"A": [("2026-08-01", 100.0), ("2026-08-02", 101.0)],
              "VT": [("2026-08-01", 100.0), ("2026-08-02", 100.0)]}

    assert all(h["n"] == 0 for h in forward_performance(snaps, prices, today=today))


def test_forward_performance_excludes_partial_scores():
    """/8 กับ /11 คนละฐาน — ปนกลุ่มแล้วหุ้น burn cash จะไปกองอยู่ band 'อ่อน' โดยอัตโนมัติ."""
    today = date(2026, 8, 2)
    snaps = {"A": [_snap("A", "2026-01-01", _health(FULL, max_=8.0))]}
    prices = {"A": [("2026-01-01", 100.0), ("2026-04-01", 120.0)],
              "VT": [("2026-01-01", 100.0), ("2026-04-01", 115.0)]}

    assert all(h["n"] == 0 for h in forward_performance(snaps, prices, today=today))


def test_noise_threshold_is_the_documented_one():
    """กันเผลอขยับ threshold แล้วธงหายไปเงียบๆ."""
    snaps = [
        _snap("X", "2026-07-01", _health([["FCF", None]])),
        _snap("X", "2026-07-02", _health([["FCF", NOISE_POINTS]])),
    ]
    assert stability(snaps)["trustworthy"] is False

# ------------------------------------------------- Phase 37: เราแก้กติกาเอง vs บริษัทเปลี่ยน

def test_an_engine_version_change_is_not_called_an_estimate_revision():
    """เคสจริงที่จุดชนวน: Phase 36 ย้าย anchor ไปใช้ประวัติที่ยื่น ก.ล.ต. แล้ว CVX realistic growth
    เด้ง -11.09% -> +3.21% ในวันเดียว. ถ้าไม่มีป้ายเวอร์ชัน สมุดพกจะบอกว่า 'ประมาณการของเรา
    เปลี่ยน' ซึ่งถูกตามตัวอักษรแต่แยกไม่ออกเลยว่าข้อมูลทำให้ขยับ หรือเราแก้วิธีคิดเมื่อวาน."""
    prev = _health(FULL, implied=14.0, realistic=-11.09)
    cur = _health(FULL, implied=14.0, realistic=3.21)

    same = attribute(prev, cur, "aaaaaaaaaaaa", "aaaaaaaaaaaa")
    changed = attribute(prev, cur, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    assert same["buckets"]["estimate"] != 0 and same["buckets"]["method"] == 0.0
    assert changed["buckets"]["method"] == changed["total"] != 0
    assert changed["buckets"]["estimate"] == 0.0
    assert changed["method_changed"] is True
    assert "aaaaaaaaaaaa -> bbbbbbbbbbbb" in changed["notes"][0]


def test_rows_without_an_engine_stamp_behave_exactly_as_before():
    """ประวัติก่อน Phase 37 ไม่มีป้าย — None แปลว่า 'ไม่รู้' ไม่ใช่ 'เปลี่ยน' และไม่ใช่ 'เหมือน'
    (หลักเดียวกับ compare._same_framework) การตั้งธงย้อนหลังทั้งประวัติแย่กว่าไม่ตั้ง."""
    prev = _health(FULL, implied=14.0, realistic=8.0)
    cur = _health(FULL, implied=14.0, realistic=13.0)

    for pe, ce in [(None, None), (None, "bbbbbbbbbbbb"), ("aaaaaaaaaaaa", None)]:
        a = attribute(prev, cur, pe, ce)
        assert a["method_changed"] is False
        assert a["buckets"]["estimate"] > 0


def test_a_basis_change_still_wins_over_an_engine_change():
    """พลิก /8 <-> /11 = เทียบไม่ได้เลย ซึ่งแรงกว่า 'เทียบได้แต่คนละกติกา' — ต้องรายงานอันที่แรงกว่า."""
    prev = _health(FULL, implied=9.0, realistic=8.0)
    cur = _health(FULL, max_=8.0)

    a = attribute(prev, cur, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    assert a["basis_changed"] is True and a["method_changed"] is False


def test_the_anchor_switching_source_is_method_not_estimate():
    """เวอร์ชันเอนจิ้นจับไม่ได้ทุกเคส: วันที่ประวัติ XBRL ของ NVDA ยาวครบ 6 ปี anchor จะเปลี่ยนจาก
    หน้าต่างสั้นเป็นประวัติยาวทีละตัว โดยโค้ดไม่ได้ถูกแก้เลย — ต้องดักที่ตัวข้อมูลด้วย."""
    prev = _health(FULL, implied=14.0, realistic=-11.09, anchor="fcf")
    cur = _health(FULL, implied=14.0, realistic=3.21, anchor="fcf_long")

    a = attribute(prev, cur, "aaaaaaaaaaaa", "aaaaaaaaaaaa")

    assert a["buckets"]["method"] == a["total"] != 0
    assert a["buckets"]["estimate"] == 0.0
    assert any("anchor" in n for n in a["notes"])


def test_the_same_anchor_source_still_separates_price_from_estimate():
    """ต้องไม่เหมาว่าอะไรที่มี anchor_window คือการเปลี่ยนวิธี — ไม่งั้นทุกแถวหลัง Phase 36
    จะตกถัง method หมดแล้วการแยกราคา/ประมาณการที่ Phase 32 ทำไว้จะตายทั้งดุ้น."""
    prev = _health(FULL, implied=14.0, realistic=8.0, anchor="fcf_long")
    cur = _health(FULL, implied=9.0, realistic=8.0, anchor="fcf_long")

    a = attribute(prev, cur)

    assert a["buckets"]["price"] > 0 and a["buckets"]["method"] == 0.0


def test_a_method_change_does_not_make_a_stock_untrustworthy():
    """วันที่แก้เกณฑ์ หุ้นทุกตัวเปลี่ยนเวอร์ชันพร้อมกัน — ถ้านับเป็นความไม่นิ่ง ธงจะขึ้นทั้งกระดาน
    พร้อมกันซึ่งไม่ได้แยกอะไรออกจากอะไรเลย (บทเรียนเดียวกับ macro grace window)."""
    snaps = [
        _snap("CVX", "2026-08-10", _health(FULL, implied=14.0, realistic=-11.09), engine="aaaaaaaaaaaa"),
        _snap("CVX", "2026-08-11", _health(FULL, implied=14.0, realistic=3.21), engine="bbbbbbbbbbbb"),
    ]
    s = stability(snaps)

    assert s["method_changes"] == 1
    assert s["unexplained"] == 0.0
    assert s["trustworthy"] is True
    assert s["gross"]["method"] > 0


def test_the_report_says_how_many_stocks_the_rule_change_touched():
    """ไม่กลืนหาย: ถึงจะไม่ตั้งธง ก็ต้องบอกออกไปตรงๆ ว่าช่วงก่อน/หลังเทียบกันตรงๆ ไม่ได้."""
    touched = [
        _snap("A", "2026-08-10", _health(FULL, implied=14.0, realistic=8.0), engine="aaaaaaaaaaaa"),
        _snap("A", "2026-08-11", _health(FULL, implied=14.0, realistic=3.0), engine="bbbbbbbbbbbb"),
    ]
    untouched = [
        _snap("B", "2026-08-10", _health([["ROIC>WACC", 1.0]]), engine="aaaaaaaaaaaa"),
        _snap("B", "2026-08-11", _health([["ROIC>WACC", 1.0]]), engine="aaaaaaaaaaaa"),
    ]

    rep = stability_report({"A": touched, "B": untouched})

    assert "1 จาก 2" in rep["method_note"]
    assert len(rep["engine_version"]) == 12


def test_the_report_stays_silent_when_no_rule_changed():
    """ข้อความที่ขึ้นทุกวันไม่ต่างจากไม่มีข้อความ — ไม่มีการแก้กติกา = ไม่ต้องพูดถึง."""
    calm = [_snap("C", f"2026-08-1{i}", _health([["ROIC>WACC", 1.0]]), engine="aaaaaaaaaaaa")
            for i in (0, 1)]

    assert stability_report({"C": calm})["method_note"] is None


def test_buckets_still_sum_to_total_when_the_method_changed():
    """invariant เดิมต้องไม่พังเพราะถังใหม่."""
    prev = _health(FULL, implied=14.0, realistic=8.0)
    cur = _health([["ROIC>WACC", 1.0]], implied=9.0, realistic=13.0, penalty=0.5)

    a = attribute(prev, cur, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    assert round(sum(a["buckets"].values()), 2) == a["total"]


def test_a_rule_change_that_did_not_move_this_stock_is_not_counted_as_touching_it():
    """ประวัติจริงมี 18 คอมมิตแตะไฟล์ให้คะแนนใน 5 สัปดาห์ — ถ้านับทุกครั้ง MSFT จะขึ้นว่า
    'แก้กติกา 9x' ทั้งที่ 3 ครั้งขยับ 0.00 จุด แล้วโน้ตของเหตุการณ์จริงจะถูกเบียดตกจอ.
    'กระทบตัวนี้' ต้องแปลว่าเลขขยับจริง ไม่ใช่แปลว่ามีคอมมิต."""
    same = _health(FULL, implied=14.0, realistic=8.0)

    a = attribute(same, same, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    assert a["method_changed"] is False
    assert a["notes"] == []


def test_a_zero_net_move_across_engines_is_still_not_split_into_buckets():
    """กับดักของการกรองตามขนาด: ขาพื้นฐาน +1 กับขาราคา -1 หักกลบเหลือ 0 — ถ้าปล่อยให้ไหลไป
    แยก bucket ตามปกติ จะได้รายงานว่า 'ธุรกิจดีขึ้น 1 จุด' ข้ามกติกาคนละชุด ซึ่งไม่เคยเกิดขึ้น."""
    prev = _health([["ROIC>WACC", 0.0]], implied=9.0, realistic=8.0)
    cur = _health([["ROIC>WACC", 1.0]], implied=14.0, realistic=8.0)
    assert cur["score"] == prev["score"]      # หักกลบพอดี

    a = attribute(prev, cur, "aaaaaaaaaaaa", "bbbbbbbbbbbb")

    assert a["buckets"]["business"] == 0.0 and a["buckets"]["price"] == 0.0
