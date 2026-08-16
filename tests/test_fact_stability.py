"""ตัวเลขที่หายๆ โผล่ๆ ข้ามวัน (Phase 38) — ฉีดประวัติปลอม ไม่แตะ DB/yfinance.

ที่มา: สมุดพกบอกได้แค่ "ASML ขยับ 7 จุดเพราะข้อมูลฝั่งเรา" แต่ไม่บอกว่าตัวเลขไหน — ของจริงคือ
CFO ที่ yfinance เรียกคนละชื่อบางรอบ กว่าจะเจอต้องนั่งไล่ facts ทีละวัน

สิ่งที่ต้องพิสูจน์ที่สุดคือ **ตัวจับต้องเงียบตอนที่เราเป็นคนแก้เอง** — ถ้าทุกครั้งที่เราเพิ่ม/ตัด
Fact แล้วมันติดธง รายงานจะเต็มไปด้วยการเปลี่ยนแปลงที่เราตั้งใจ แล้วของจริงจะจมหายไป
"""
from src.evals.check_fact_stability import (
    MIN_FLIPS,
    check_many,
    check_one,
    render_text,
)


def _row(ticker, day, labels, computable=8, max_=11.0, val_score=2.0):
    return {
        "ticker": ticker,
        "run_at": f"{day}T17:00:00",
        "facts": [{"label": n, "value": 1.0, "unit": "x", "period": "FY2025"} for n in labels],
        "health": {
            "score": 9.0, "max": max_,
            "fundamental": {"computable": computable, "criteria": []},
            "valuation": ({"score": val_score} if val_score is not None else None),
        },
    }


BASE = ["Revenue", "Net Income", "CFO"]


# ---------- ต้องจับได้ ----------

def test_a_value_that_disappears_and_comes_back_is_reported():
    """อาการจริงของ ASML: CFO หาย -> กลับมา -> หาย ตามชุดแถวที่ yfinance บังเอิญคืนมารอบนั้น."""
    snaps = [
        _row("ASML", "2026-07-29", BASE),
        _row("ASML", "2026-07-30", ["Revenue", "Net Income"], computable=7),
        _row("ASML", "2026-07-31", BASE),
        _row("ASML", "2026-08-01", ["Revenue", "Net Income"], computable=7),
    ]

    out = check_one("ASML", snaps)

    assert [r["label"] for r in out] == ["CFO"]
    assert out[0]["flips"] == 3
    assert out[0]["missing_days"] == 2 and out[0]["total_days"] == 4


def test_the_report_says_whether_the_gap_reached_the_score():
    """'หายจาก DATA' กับ 'ลากคะแนนไปด้วย' ไม่เท่ากัน — ตัวหลังต้องขึ้นก่อนเสมอ ไม่งั้นคนอ่านจะ
    ไล่แก้ตามลำดับที่ผิด."""
    harmless = [
        _row("A", "2026-07-01", BASE + ["P/S"]),
        _row("A", "2026-07-02", BASE),                       # P/S หาย แต่คะแนนประกอบเหมือนเดิม
        _row("A", "2026-07-03", BASE + ["P/S"]),
    ]
    harmful = [
        _row("B", "2026-07-01", BASE),
        _row("B", "2026-07-02", ["Revenue", "Net Income"], computable=7),
        _row("B", "2026-07-03", BASE),
    ]

    out = check_many([*harmless, *harmful])

    assert out[0]["ticker"] == "B" and out[0]["score_impact"] > 0
    assert out[1]["ticker"] == "A" and out[1]["score_impact"] == 0


def test_a_price_side_input_counts_even_though_no_criterion_moved():
    """เคส MA ของจริง: Market Cap หาย -> เกณฑ์พื้นฐานครบ 8 เท่าเดิมทุกข้อ แต่ทั้งแถวร่วงไป
    partial /8 = แกว่ง 2 จุด. ตัววัดที่ดูแค่จำนวนเกณฑ์จะมองข้ามเคสที่แพงที่สุด."""
    snaps = [
        _row("MA", "2026-07-27", BASE + ["Market Cap"]),
        _row("MA", "2026-07-28", BASE, max_=8.0, val_score=None),   # เกณฑ์ยังครบ 8 เท่าเดิม
        _row("MA", "2026-07-29", BASE + ["Market Cap"]),
    ]

    out = check_one("MA", snaps)

    assert out[0]["label"] == "Market Cap"
    assert out[0]["score_impact"] == 2


# ---------- ต้องเงียบตอนที่เราเป็นคนแก้เอง ----------

def test_a_value_we_added_once_is_not_called_unstable():
    """Phase 17/18 เพิ่ม Fact 10 ตัวรวดในวันเดียว — ถ้านับเป็นความไม่นิ่ง หุ้นทุกตัวจะติดธง
    พร้อมกันในวันนั้น ซึ่งไม่ได้บอกอะไรเลย."""
    snaps = [
        _row("X", "2026-07-10", BASE),
        _row("X", "2026-07-11", BASE + ["NOPAT", "Invested Capital"]),
        _row("X", "2026-07-12", BASE + ["NOPAT", "Invested Capital"]),
    ]
    assert check_one("X", snaps) == []


def test_a_value_we_removed_once_is_not_called_unstable():
    """Phase 33.2 ตัด P/S,P/B ของ ADR ทิ้งถาวร — ของที่เราตัดเองไม่เคยกลับมาเอง."""
    snaps = [
        _row("TSM", "2026-08-05", BASE + ["P/S"]),
        _row("TSM", "2026-08-06", BASE),
        _row("TSM", "2026-08-07", BASE),
    ]
    assert check_one("TSM", snaps) == []


def test_the_threshold_is_the_documented_one():
    """กันเผลอขยับ MIN_FLIPS แล้วธงหาย/ท่วมเงียบๆ — 2 = 'หายแล้วกลับมา' อย่างน้อยหนึ่งรอบ."""
    assert MIN_FLIPS == 2
    one_way = [_row("X", "2026-07-01", BASE), _row("X", "2026-07-02", ["Revenue", "Net Income"])]
    assert check_one("X", one_way) == []


def test_a_metric_that_is_meant_to_appear_later_is_exempt():
    """FCF CAGR (long-run) โผล่เมื่อประวัติ ก.ล.ต. ยาวพอ (Phase 36) = พฤติกรรมที่ออกแบบไว้."""
    label = "FCF CAGR (long-run)"
    snaps = [
        _row("CVX", "2026-08-01", BASE + [label]),
        _row("CVX", "2026-08-02", BASE),
        _row("CVX", "2026-08-03", BASE + [label]),
    ]
    assert check_one("CVX", snaps) == []


# ---------- ขอบ ----------

def test_reruns_on_the_same_day_are_collapsed():
    """รันมือซ้ำในวันเดียวไม่ใช่ 'ข้อมูลเปลี่ยนข้ามวัน' — เกณฑ์เดียวกับ scorecard.snapshots
    ไม่งั้นการทดสอบมือหนึ่งครั้งจะกลายเป็นหลักฐานว่าแหล่งข้อมูลไม่นิ่ง."""
    rows = [
        {**_row("A", "2026-07-01", BASE), "run_at": "2026-07-01T09:00:00"},
        {**_row("A", "2026-07-01", ["Revenue"]), "run_at": "2026-07-01T20:00:00"},
        {**_row("A", "2026-07-02", ["Revenue"]), "run_at": "2026-07-02T17:00:00"},
    ]
    assert check_many(rows) == []


def test_one_day_of_history_has_nothing_to_compare():
    assert check_one("A", [_row("A", "2026-07-01", BASE)]) == []


def test_rows_without_health_do_not_crash():
    """แถวก่อน Phase 10 ไม่มี health เลย — ต้องยังจับการหายได้ แค่บอกผลกระทบไม่ได้."""
    snaps = [
        {**_row("A", "2026-07-01", BASE), "health": None},
        {**_row("A", "2026-07-02", ["Revenue"]), "health": None},
        {**_row("A", "2026-07-03", BASE), "health": None},
    ]
    out = check_one("A", snaps)
    assert {r["label"] for r in out} == {"CFO", "Net Income"}
    assert all(r["score_impact"] == 0 for r in out)


def test_silence_is_stated_not_blank():
    """รายงานว่างเปล่าอ่านไม่ออกว่า 'ไม่มีปัญหา' หรือ 'ตัวตรวจพัง' — บทเรียนเดิมจาก macro radar."""
    assert "ไม่พบ" in render_text([])


def test_the_window_is_measured_from_the_newest_run_not_the_clock():
    """รอบ CI ตกบ้าง ข้อมูลจึงตามหลังปฏิทินได้หลายวัน — ถ้าอิงนาฬิกา รายงานจะว่างเปล่าในวันที่
    CI ไม่ได้รัน ซึ่งอ่านผิดเป็น 'ทุกอย่างนิ่งดี' พอดี ทั้งที่จริงคือไม่ได้ตรวจ."""
    old = [_row("A", "2026-01-01", BASE), _row("A", "2026-01-02", ["Revenue"]),
           _row("A", "2026-01-03", BASE)]

    assert check_many(old, since_days=14)          # ข้อมูลเก่าแต่ติดกัน -> ยังเห็น
    assert check_many(old, since_days=1) == []     # หน้าต่างแคบกว่าช่วงที่แกว่ง -> เงียบ


def test_events_outside_the_window_age_out():
    """รายการที่เคยเกิดจะค้างในประวัติตลอดไป — ถ้าไม่มีหน้าต่าง แจ้งเตือนเดิมจะถูกส่งซ้ำทุกวัน
    จนไม่มีใครอ่าน (หลักเดียวกับ macro grace window)."""
    rows = [_row("A", "2026-07-01", BASE), _row("A", "2026-07-02", ["Revenue"]),
            _row("A", "2026-07-03", BASE)]
    rows += [_row("A", f"2026-08-{d:02d}", BASE) for d in range(1, 6)]   # นิ่งมาตลอดตั้งแต่นั้น

    assert check_many(rows) != []                  # ทั้งประวัติ -> ยังเห็นของเก่า
    assert check_many(rows, since_days=14) == []   # หน้าต่างล่าสุด -> เงียบแล้ว
