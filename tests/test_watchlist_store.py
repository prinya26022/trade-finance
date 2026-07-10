"""Regression: watchlist store ต้อง self-init/migrate ก่อนอ่านเสมอ.

บั๊กจริงที่หลุดขึ้น CI: DB ที่ CI commit ไว้เป็น schema เก่า (ก่อน Phase 5.5a ไม่มีคอลัมน์
status/entry_*) พอ list_all() อ่านโดยไม่ init_db() ก่อน -> r["status"] = IndexError
ทำให้ทั้ง /api/portfolio และ send_report พังบน GitHub Actions.
test นี้จำลอง DB schema เก่าเป๊ะ แล้วยืนยันว่าอ่านได้โดยไม่พังอีก.
"""
import sqlite3


def _make_old_schema_db(path):
    """สร้าง watchlist.db แบบ pre-Phase-5.5a: มีแค่ 3 คอลัมน์แรก ไม่มี status/entry_*."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE watchlist (ticker TEXT PRIMARY KEY, "
        "asset_type TEXT NOT NULL DEFAULT 'stock', added_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO watchlist VALUES ('AAPL', 'stock', '2026-01-01T00:00:00')")
    conn.commit()
    conn.close()


def test_list_all_migrates_old_schema(tmp_db):
    """อ่าน DB schema เก่า -> ต้อง migrate ให้มีคอลัมน์ status เอง ไม่ IndexError."""
    _make_old_schema_db(tmp_db)
    from src.watchlist import store

    rows = store.list_all()   # เดิมพังตรงนี้: 'No item with that key'
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["status"] == "watching"   # คอลัมน์ใหม่ default ถูกเติมให้


def test_get_entry_on_old_schema(tmp_db):
    """get_entry (ที่ performance/edge เรียก) ก็ต้องไม่พังบน DB เก่า."""
    _make_old_schema_db(tmp_db)
    from src.watchlist import store

    row = store.get_entry("AAPL")
    assert row is not None
    assert row["status"] == "watching"
    assert row["entry_price"] is None


def test_hold_then_watch_roundtrip(tmp_db):
    from src.watchlist import store

    store.add("NVDA")
    store.set_holding("NVDA", 120.5, entry_date="2026-02-01", shares=10)
    row = store.get_entry("NVDA")
    assert row["status"] == "holding"
    assert row["entry_price"] == 120.5
    assert row["entry_date"] == "2026-02-01"

    store.set_watching("NVDA")
    assert store.get_entry("NVDA")["status"] == "watching"


# ---- add_shares (Phase 11: ซื้อเพิ่ม -> เฉลี่ย entry_price อัตโนมัติ) ----

def test_add_shares_computes_weighted_average(tmp_db):
    import pytest
    from src.watchlist.store import set_holding, add_shares, get_entry

    set_holding("DUOL", 99.63, entry_date="2026-05-06", shares=2)
    r = add_shares("DUOL", 130.0, shares=3)

    # (99.63*2 + 130*3) / 5 = 117.852
    assert r["new_shares"] == 5
    assert r["new_price"] == pytest.approx(117.852, abs=1e-6)

    row = get_entry("DUOL")
    assert row["shares"] == 5
    assert row["entry_price"] == pytest.approx(117.852, abs=1e-6)
    # entry_date เดิมต้องไม่เปลี่ยน (ยังเทียบ edge ตั้งแต่วันแรกที่ซื้อ)
    assert row["entry_date"] == "2026-05-06"
    assert row["status"] == "holding"


def test_add_shares_requires_existing_holding(tmp_db):
    import pytest
    from src.watchlist.store import add, add_shares

    add("NVDA")   # แค่ watching, ยังไม่เคย hold
    with pytest.raises(ValueError, match="holding"):
        add_shares("NVDA", 100.0, shares=1)


def test_add_shares_requires_prior_shares_count(tmp_db):
    import pytest
    from src.watchlist.store import set_holding, add_shares

    set_holding("AAPL", 200.0)   # ไม่ระบุ shares ตอนตั้งครั้งแรก
    with pytest.raises(ValueError, match="shares"):
        add_shares("AAPL", 210.0, shares=1)


def test_remove_deletes_from_watchlist_but_keeps_history(tmp_db):
    from src.watchlist.store import add, remove, list_all
    from tests.conftest import save_row
    from src.history.store import history

    add("SBUX")
    save_row(ticker="SBUX")
    remove("SBUX")

    assert all(r["ticker"] != "SBUX" for r in list_all())
    assert len(history("SBUX")) == 1   # ประวัติ analyses เดิมยังอยู่ ไม่ถูกลบตาม
