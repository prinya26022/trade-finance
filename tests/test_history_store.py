"""health_trends() (Phase 23) — เบากว่า history()/latest_per_ticker() มาก (query แค่ 3 คอลัมน์
ไม่ parse summary_json/facts_json ทุกแถว) ไว้ป้อน sparkline แนวโน้ม health ในการ์ด/ตาราง.
ใช้ tmp_db fixture (conftest.py) กันไม่ให้แตะ data/watchlist.db จริง.
"""
from src.history.store import save_analysis, health_trends

_GROUNDING = {"price_ok": True, "news_grounded_ratio": 1.0, "facts": {"facts_grounded_ratio": 1.0}}


def _save(ticker, score, fake_summary):
    save_analysis(fake_summary(ticker=ticker), _GROUNDING, [], health={"score": score} if score is not None else None)


def test_health_trends_orders_oldest_to_newest(tmp_db, fake_summary):
    _save("AAPL", 5.0, fake_summary)
    _save("AAPL", 6.0, fake_summary)
    _save("AAPL", 7.0, fake_summary)
    trends = health_trends()
    assert [p["value"] for p in trends["AAPL"]] == [5.0, 6.0, 7.0]


def test_health_trends_skips_rows_without_health_score(tmp_db, fake_summary):
    _save("BTC", None, fake_summary)   # excluded/แถวเก่าก่อน Phase 10 -> health=None
    assert health_trends().get("BTC") is None


def test_health_trends_separates_by_ticker(tmp_db, fake_summary):
    _save("AAPL", 7.0, fake_summary)
    _save("MSFT", 8.0, fake_summary)
    trends = health_trends()
    assert [p["value"] for p in trends["AAPL"]] == [7.0]
    assert [p["value"] for p in trends["MSFT"]] == [8.0]


def test_health_trends_limits_points_per_ticker(tmp_db, fake_summary):
    for score in [1.0, 2.0, 3.0, 4.0, 5.0]:
        _save("AAPL", score, fake_summary)
    trends = health_trends(limit_per_ticker=3)
    # ล่าสุด 3 จุด (3,4,5) เรียงเก่า->ใหม่ — ไม่ใช่ 3 จุดแรก
    assert [p["value"] for p in trends["AAPL"]] == [3.0, 4.0, 5.0]


def test_health_trends_empty_db_returns_empty_dict(tmp_db):
    assert health_trends() == {}