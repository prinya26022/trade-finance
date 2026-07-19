"""health_trends() (Phase 23) — เบากว่า history()/latest_per_ticker() มาก (query แค่ 3 คอลัมน์
ไม่ parse summary_json/facts_json ทุกแถว) ไว้ป้อน sparkline แนวโน้ม health ในการ์ด/ตาราง.
Dedupe รายวัน (audit fix เดียวกันวันนี้): ถ้าวันไหนรันซ้ำหลายครั้ง (ทดสอบมือ/cron+manual) เก็บแค่
ค่ารันล่าสุดของวันนั้น ไม่งั้น sparkline จะเปลืองจุดไปกับวันเดียวกันแทนที่จะขยายช่วงเวลาย้อนหลังได้ไกลกว่า
(เหมือนกราฟใหญ่ในหน้า ticker detail ทำอยู่แล้ว — healthByDay).
ใช้ tmp_db fixture (conftest.py) กันไม่ให้แตะ data/watchlist.db จริง — insert ตรงผ่าน _connect()
แทน save_analysis() เพราะต้องคุม run_at เอง (save_analysis ใช้ datetime.now() เสมอ ควบคุมวันที่
ในเทสต์ไม่ได้).
"""
from src.history.store import _connect, init_db, health_trends


def _insert(ticker: str, run_at: str, health_score: float | None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO analyses (ticker, run_at, summary_json, health_score) VALUES (?, ?, '{}', ?)",
            (ticker, run_at, health_score),
        )


def test_health_trends_orders_oldest_to_newest(tmp_db):
    _insert("AAPL", "2026-07-01T10:00:00", 5.0)
    _insert("AAPL", "2026-07-02T10:00:00", 6.0)
    _insert("AAPL", "2026-07-03T10:00:00", 7.0)
    trends = health_trends()
    assert [p["value"] for p in trends["AAPL"]] == [5.0, 6.0, 7.0]
    assert [p["period"] for p in trends["AAPL"]] == ["2026-07-01", "2026-07-02", "2026-07-03"]


def test_health_trends_skips_rows_without_health_score(tmp_db):
    _insert("BTC", "2026-07-01T10:00:00", None)   # excluded/แถวเก่าก่อน Phase 10 -> health=None
    assert health_trends().get("BTC") is None


def test_health_trends_separates_by_ticker(tmp_db):
    _insert("AAPL", "2026-07-01T10:00:00", 7.0)
    _insert("MSFT", "2026-07-01T10:00:00", 8.0)
    trends = health_trends()
    assert [p["value"] for p in trends["AAPL"]] == [7.0]
    assert [p["value"] for p in trends["MSFT"]] == [8.0]


def test_health_trends_limits_points_per_ticker(tmp_db):
    for day, score in enumerate([1.0, 2.0, 3.0, 4.0, 5.0], start=1):
        _insert("AAPL", f"2026-07-0{day}T10:00:00", score)
    trends = health_trends(limit_per_ticker=3)
    # 3 วันล่าสุด (3,4,5) เรียงเก่า->ใหม่ — ไม่ใช่ 3 วันแรก
    assert [p["value"] for p in trends["AAPL"]] == [3.0, 4.0, 5.0]


def test_health_trends_empty_db_returns_empty_dict(tmp_db):
    assert health_trends() == {}


def test_health_trends_dedupes_same_day_keeps_latest_run(tmp_db):
    # เคสจริงที่เจอ: AAPL รันซ้ำ 4 ครั้งในวันเดียว (07-07) ตอน dev ทดสอบ — sparkline ต้องเห็น
    # วันนั้นเป็น "1 จุด" ด้วยค่า "รันล่าสุด" ของวันนั้น ไม่ใช่ 4 จุดเปลืองที่ไปกับวันเดียวกัน
    _insert("AAPL", "2026-07-06T20:55:57", 6.0)
    _insert("AAPL", "2026-07-07T00:07:54", 6.0)
    _insert("AAPL", "2026-07-07T11:37:20", 6.0)
    _insert("AAPL", "2026-07-07T12:27:14", 6.0)
    _insert("AAPL", "2026-07-07T18:25:02", 6.5)   # รันล่าสุดของวัน 07-07 -> ต้องเป็นค่าที่เหลือ
    _insert("AAPL", "2026-07-08T09:00:00", 7.0)
    trends = health_trends()
    assert [(p["period"], p["value"]) for p in trends["AAPL"]] == [
        ("2026-07-06", 6.0),
        ("2026-07-07", 6.5),   # ไม่ใช่ 4 จุดซ้ำ, และไม่ใช่ค่าแรกของวัน (6.0) แต่เป็นค่าล่าสุด
        ("2026-07-08", 7.0),
    ]


def test_health_trends_dedupe_respects_per_ticker_limit_after_collapsing_days(tmp_db):
    # limit ต้องนับ "วันปฏิทิน" หลัง dedupe แล้ว ไม่ใช่นับ "แถวดิบ" ก่อน dedupe
    _insert("AAPL", "2026-07-01T09:00:00", 1.0)
    _insert("AAPL", "2026-07-01T10:00:00", 1.5)   # วันเดียวกับข้างบน -> ไม่นับเพิ่ม
    _insert("AAPL", "2026-07-02T09:00:00", 2.0)
    trends = health_trends(limit_per_ticker=2)
    assert [p["value"] for p in trends["AAPL"]] == [1.5, 2.0]