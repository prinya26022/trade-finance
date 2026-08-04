"""รวมไฟล์ DB สองฝั่งตอน git ชน (Phase 33.6). Offline ล้วน — สร้าง sqlite ชั่วคราวเอง.

เทสต์ชุดนี้มีเพราะทางเลือกเดิมคือ "เลือกไฟล์ของฝั่งใดฝั่งหนึ่ง" ซึ่งทิ้งงานของอีกฝั่งเสมอ
และรอบก่อนรอดมาได้เพราะบังเอิญ local เป็นสับเซตของ CI พอดี. พอเริ่มแก้ DB ผ่านหน้าเว็บ
(ลบ ticker, แก้ thesis) ความบังเอิญนั้นหมดอายุ — เคสที่ต้องกันคือ "ต่างฝั่งต่างแก้" จริงๆ
"""
import sqlite3

import pytest

from src.db.merge import merge_db

ANALYSES = """
CREATE TABLE analyses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    run_at       TEXT NOT NULL,
    price        REAL,
    health_score REAL,
    summary_json TEXT NOT NULL
)"""

CLAUDE = """
CREATE TABLE claude_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    period      TEXT NOT NULL,
    model       TEXT NOT NULL,
    run_at      TEXT NOT NULL,
    analysis_id INTEGER,
    summary_json TEXT NOT NULL
)"""

WATCHLIST = """
CREATE TABLE watchlist (
    ticker     TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    added_at   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'watching',
    shares     REAL
)"""

THESES = """
CREATE TABLE theses (
    ticker     TEXT PRIMARY KEY,
    thesis     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""


def make_db(path, schemas, rows=None):
    conn = sqlite3.connect(path)
    for s in schemas:
        conn.execute(s)
    for table, records in (rows or {}).items():
        for r in records:
            cols = ", ".join(r)
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(r))})",
                         list(r.values()))
    conn.commit()
    conn.close()
    return str(path)


def read(path, table, order="rowid"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]
    conn.close()
    return rows


def analysis(id, ticker, run_at, **kw):
    return {"id": id, "ticker": ticker, "run_at": run_at, "summary_json": "{}", **kw}


@pytest.fixture
def three(tmp_path):
    """สภาพจริงที่เจอ: base มีผลถึงเมื่อวาน แล้วสองฝั่งเดินต่อคนละทาง."""
    rows = {"analyses": [analysis(1, "AAPL", "2026-08-01"), analysis(2, "NVDA", "2026-08-01")],
            "watchlist": [{"ticker": "AAPL", "added_at": "2026-01-01"},
                          {"ticker": "NVDA", "added_at": "2026-01-01"}]}
    base = make_db(tmp_path / "base.db", [ANALYSES, WATCHLIST, CLAUDE, THESES], rows)
    ours = make_db(tmp_path / "ours.db", [ANALYSES, WATCHLIST, CLAUDE, THESES], rows)
    theirs = make_db(tmp_path / "theirs.db", [ANALYSES, WATCHLIST, CLAUDE, THESES], rows)
    return base, ours, theirs, str(tmp_path / "out.db")


def add(path, table, row):
    conn = sqlite3.connect(path)
    conn.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                 list(row.values()))
    conn.commit()
    conn.close()


def run(path, sql, *params):
    conn = sqlite3.connect(path)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


# ---------- แถวใหม่ทั้งสองฝั่ง ----------

def test_rows_added_on_both_sides_all_survive(three):
    """เคสหลักที่เกิดทุกวัน: CI เพิ่มรอบรายวัน เราเพิ่มผลจากแชท — id ชนกันแต่คนละแถว."""
    base, ours, theirs, out = three
    add(ours, "analyses", analysis(3, "DUOL", "2026-08-03T10:00"))
    add(theirs, "analyses", analysis(3, "AAPL", "2026-08-03T02:00"))     # id ชนกันพอดี

    merge_db(base, ours, theirs, out)
    rows = read(out, "analyses")
    assert len(rows) == 4
    assert len({r["id"] for r in rows}) == 4                            # id ต้องไม่ซ้ำ
    assert {(r["ticker"], r["run_at"]) for r in rows} == {
        ("AAPL", "2026-08-01"), ("NVDA", "2026-08-01"),
        ("DUOL", "2026-08-03T10:00"), ("AAPL", "2026-08-03T02:00")}


def test_foreign_key_follows_the_row_when_its_id_is_moved(three):
    """ถ้าย้าย id แล้วไม่ตามแก้คนที่อ้างถึง สายจะไปโผล่ผิดแถว — เงียบและอันตรายกว่าหาย."""
    base, ours, theirs, out = three
    add(ours, "analyses", analysis(3, "DUOL", "2026-08-03T10:00"))
    add(ours, "claude_analyses", {"id": 1, "ticker": "DUOL", "period": "2026-08",
                                  "model": "claude-opus-5", "run_at": "2026-08-03T11:00",
                                  "analysis_id": 3, "summary_json": "{}"})
    add(theirs, "analyses", analysis(3, "AAPL", "2026-08-03T02:00"))

    merge_db(base, ours, theirs, out)
    link = read(out, "claude_analyses")[0]
    target = [r for r in read(out, "analyses") if r["id"] == link["analysis_id"]][0]
    assert target["ticker"] == "DUOL"                                   # ยังชี้แถวเดิมของมัน


def test_the_same_daily_run_recorded_on_both_sides_is_not_duplicated(three):
    """เรารันวิเคราะห์เองแล้ว CI ก็รันรอบเดียวกัน -> ตัวตนเดียวกัน ต้องเหลือแถวเดียว."""
    base, ours, theirs, out = three
    add(ours, "analyses", analysis(3, "AAPL", "2026-08-03T02:00", price=100.0))
    add(theirs, "analyses", analysis(9, "AAPL", "2026-08-03T02:00", price=100.0))

    merge_db(base, ours, theirs, out)
    assert len(read(out, "analyses")) == 3


# ---------- แก้/ลบ ----------

def test_an_edit_on_one_side_only_is_taken(three):
    base, ours, theirs, out = three
    run(theirs, "UPDATE analyses SET health_score = 8.5 WHERE id = 1")

    merge_db(base, ours, theirs, out)
    assert read(out, "analyses")[0]["health_score"] == 8.5


def test_deleting_in_the_ui_actually_deletes(three):
    """ลบ ticker ผ่านหน้าเว็บแล้วถูก CI เขียนกลับมา = ฟีเจอร์ลบใช้ไม่ได้จริง."""
    base, ours, theirs, out = three
    run(ours, "DELETE FROM watchlist WHERE ticker = 'NVDA'")

    report = merge_db(base, ours, theirs, out)
    assert [r["ticker"] for r in read(out, "watchlist")] == ["AAPL"]
    assert report["conflicts"] == []                                    # ไม่ใช่เรื่องต้องถาม


def test_delete_versus_edit_keeps_the_row_and_says_so(three):
    """คืนของที่ไม่อยากได้ง่ายกว่ากู้ของที่หาย — แต่ต้องรายงาน ไม่ใช่ตัดสินเงียบๆ."""
    base, ours, theirs, out = three
    run(ours, "DELETE FROM watchlist WHERE ticker = 'NVDA'")
    run(theirs, "UPDATE watchlist SET shares = 10 WHERE ticker = 'NVDA'")

    report = merge_db(base, ours, theirs, out)
    assert {r["ticker"] for r in read(out, "watchlist")} == {"AAPL", "NVDA"}
    assert len(report["conflicts"]) == 1
    assert "ลบ" in report["conflicts"][0]["kind"]


def test_both_sides_edit_the_same_thesis_newest_wins_and_is_reported(three):
    base, ours, theirs, out = three
    for db in (base, ours, theirs):
        add(db, "theses", {"ticker": "AAPL", "thesis": "เดิม",
                           "created_at": "2026-01-01", "updated_at": "2026-01-01"})
    run(ours, "UPDATE theses SET thesis='ของเรา', updated_at='2026-08-02' WHERE ticker='AAPL'")
    run(theirs, "UPDATE theses SET thesis='ของเขา', updated_at='2026-08-04' WHERE ticker='AAPL'")

    report = merge_db(base, ours, theirs, out)
    assert read(out, "theses")[0]["thesis"] == "ของเขา"
    assert len(report["conflicts"]) == 1
    assert report["conflicts"][0]["chose"] == "theirs"


def test_a_dangling_link_is_cleared_not_left_pointing_at_nothing(three):
    base, ours, theirs, out = three
    for db in (base, ours):
        add(db, "claude_analyses", {"id": 1, "ticker": "NVDA", "period": "2026-08",
                                    "model": "claude-opus-5", "run_at": "2026-08-02",
                                    "analysis_id": 2, "summary_json": "{}"})
    add(theirs, "claude_analyses", {"id": 1, "ticker": "NVDA", "period": "2026-08",
                                    "model": "claude-opus-5", "run_at": "2026-08-02",
                                    "analysis_id": 2, "summary_json": "{}"})
    run(theirs, "DELETE FROM analyses WHERE id = 2")                    # แถวปลายทางหายไป

    report = merge_db(base, ours, theirs, out)
    assert read(out, "claude_analyses")[0]["analysis_id"] is None
    assert any("ไม่มีแล้ว" in c["kind"] for c in report["conflicts"])


def test_an_id_freed_by_a_delete_is_never_reused(three):
    """ถ้าเอาเลขที่เพิ่งลบไปให้แถวใหม่ ของที่ยังอ้างเลขนั้นจะชี้ผิดแถวแทนที่จะถูกจับได้."""
    base, ours, theirs, out = three
    run(ours, "DELETE FROM analyses WHERE id = 2")
    add(theirs, "analyses", analysis(3, "DUOL", "2026-08-03"))

    merge_db(base, ours, theirs, out)
    assert {r["id"] for r in read(out, "analyses")} == {1, 3}


# ---------- โครงสร้างต่างกัน ----------

def test_a_column_added_by_a_migration_on_one_side_survives(three):
    """schema ก็แตกกิ่งได้: เรารัน migration ไปแล้ว ฝั่ง CI ยังเป็นของเก่า."""
    base, ours, theirs, out = three
    run(ours, "ALTER TABLE analyses ADD COLUMN framework_version TEXT")
    run(ours, "UPDATE analyses SET framework_version = 'abc123' WHERE id = 1")
    add(theirs, "analyses", analysis(3, "DUOL", "2026-08-03"))

    merge_db(base, ours, theirs, out)
    rows = {r["ticker"]: r for r in read(out, "analyses")}
    assert rows["AAPL"]["framework_version"] == "abc123"
    assert rows["DUOL"]["framework_version"] is None                    # ฝั่งเก่าไม่มีค่า = ว่าง


def test_a_table_that_exists_on_one_side_only_is_carried_over(three):
    base, ours, theirs, out = three
    run(theirs, "CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ticker TEXT NOT NULL, decided_at TEXT NOT NULL, action TEXT NOT NULL)")
    add(theirs, "decisions", {"id": 1, "ticker": "AAPL", "decided_at": "2026-08-03",
                              "action": "buy"})

    merge_db(base, ours, theirs, out)
    assert read(out, "decisions")[0]["action"] == "buy"


def test_indexes_and_uniqueness_are_rebuilt_in_the_output(three):
    base, ours, theirs, out = three
    for db in (base, ours, theirs):
        run(db, "CREATE UNIQUE INDEX uq_claude ON claude_analyses (ticker, period, model)")

    merge_db(base, ours, theirs, out)
    conn = sqlite3.connect(out)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert "uq_claude" in names


# ---------- คุณสมบัติรวม ----------

def test_merging_two_identical_files_changes_nothing(three):
    base, ours, theirs, out = three
    report = merge_db(base, ours, theirs, out)
    assert read(out, "analyses") == read(ours, "analyses")
    assert read(out, "watchlist") == read(ours, "watchlist")
    assert report["conflicts"] == []


def test_without_a_base_it_unions_and_refuses_to_delete(three):
    """ไม่มีจุดอ้างอิงร่วม = แยกไม่ออกว่า 'ลบ' หรือ 'ยังไม่เคยมี' -> ห้ามเดา ห้ามลบ."""
    _, ours, theirs, out = three
    run(ours, "DELETE FROM watchlist WHERE ticker = 'NVDA'")

    report = merge_db(None, ours, theirs, out)
    assert report["two_way"] is True
    assert {r["ticker"] for r in read(out, "watchlist")} == {"AAPL", "NVDA"}


def test_new_ids_keep_working_with_autoincrement_after_the_merge(three):
    """หลังรวมแล้วโปรแกรมยังต้องเขียนต่อได้ — sqlite_sequence ต้องไม่ค้างที่เลขเก่า."""
    base, ours, theirs, out = three
    add(ours, "analyses", analysis(3, "DUOL", "2026-08-03T10:00"))
    add(theirs, "analyses", analysis(3, "AAPL", "2026-08-03T02:00"))

    merge_db(base, ours, theirs, out)
    conn = sqlite3.connect(out)
    conn.execute("INSERT INTO analyses (ticker, run_at, summary_json) VALUES ('MSFT','x','{}')")
    conn.commit()
    ids = [r[0] for r in conn.execute("SELECT id FROM analyses")]
    conn.close()
    assert len(ids) == len(set(ids)) == 5


def test_the_real_stores_can_still_open_the_merged_file(tmp_path, monkeypatch):
    """ผลลัพธ์ต้องเป็น DB ที่โปรเจกต์ใช้งานต่อได้จริง ไม่ใช่แค่ไฟล์ที่เปิดได้."""
    import importlib

    from src.history import store as history_store
    from src.watchlist import store as watchlist_store

    mods = [importlib.import_module(m) for m in
            ("src.watchlist.store", "src.history.store", "src.history.claude_store",
             "src.thesis.store", "src.settings.store")]

    def point_at(path):
        for m in mods:
            monkeypatch.setattr(m, "DB_PATH", path)

    dbs = []
    for name in ("base", "ours", "theirs"):
        path = tmp_path / f"{name}.db"
        point_at(path)
        for m in mods:
            m.init_db()
        dbs.append(str(path))

    point_at(tmp_path / "ours.db")          # เพิ่มของฝั่งเราด้วย store จริง ไม่ใช่ SQL ดิบ
    watchlist_store.add("DUOL")
    point_at(tmp_path / "theirs.db")
    watchlist_store.add("NVDA")

    out = tmp_path / "out.db"
    merge_db(*dbs, out)

    point_at(out)
    assert {r["ticker"] for r in watchlist_store.list_all()} == {"DUOL", "NVDA"}
    assert history_store.all_rows() == []
    watchlist_store.add("AAPL")             # ต้องเขียนต่อได้ ไม่ใช่แค่อ่านได้
    assert len(watchlist_store.list_all()) == 3
