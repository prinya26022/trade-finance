"""จำสถานะของสัญญาณแต่ละตัวจากรอบก่อน — เพื่อตอบว่า **"วันนี้อะไรเปลี่ยน"** ไม่ใช่ทวนซ้ำทุกวัน.

ใช้ไฟล์ DB **แยก** (data/aicapex.db) ไม่ใช่ watchlist.db หรือ macro.db — เหตุผลเดียวกับที่
src/macro/store.py แยกออกมา: workflow คนละตัว commit DB กลับ repo คนละรอบ ถ้าใช้ไฟล์เดียวกัน
จะชน commit กันเอง

self-init ทุก read/write (บทเรียนที่ทำซ้ำมาแล้วทั้งโปรเจกต์): CI checkout DB ที่ commit ไว้
ซึ่งอาจเก่ากว่าสคีมาปัจจุบัน — ถ้าไม่ init ก่อนอ่าน จะพังเฉพาะบน CI ที่ debug ยากที่สุด

**state ต้องอยู่รอดข้ามรัน** ไม่งั้นทุกรอบจะเป็น 'รอบแรก' แล้วไม่มีวันตรวจเจอการเปลี่ยนแปลงเลย
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "aicapex.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_state (
                key         TEXT PRIMARY KEY,
                state       TEXT NOT NULL,
                value       REAL,
                seen_at     TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT NOT NULL,
                state       TEXT NOT NULL,
                value       REAL,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_key ON signal_history(key, recorded_at)")
        conn.commit()
    finally:
        if own:
            conn.close()


def previous_states(db_path: Path | None = None) -> dict[str, dict]:
    """สถานะที่บันทึกไว้รอบก่อน — {} ถ้ายังไม่เคยรัน (รอบแรก จะไม่รายงานว่า 'เปลี่ยน')."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        return {r["key"]: dict(r) for r in conn.execute("SELECT * FROM signal_state")}
    finally:
        conn.close()


def record(signals, db_path: Path | None = None, now: datetime | None = None) -> None:
    """บันทึกสถานะปัจจุบันทับของเดิม + ต่อท้ายประวัติ.

    เก็บประวัติแยกด้วยเพราะ 'สัญญาณนี้อยู่สถานะ alert มากี่วันแล้ว' เป็นคำถามที่ต่างจาก
    'ตอนนี้สถานะอะไร' อย่างสิ้นเชิง — และเป็นคำถามที่ตอบไม่ได้เลยถ้าเก็บแค่ค่าล่าสุด"""
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        init_db(conn)
        for s in signals:
            conn.execute(
                "INSERT INTO signal_state (key, state, value, seen_at) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET state=excluded.state, value=excluded.value, "
                "seen_at=excluded.seen_at",
                (s.key, s.state, s.value, stamp))
            conn.execute(
                "INSERT INTO signal_history (key, state, value, recorded_at) VALUES (?,?,?,?)",
                (s.key, s.state, s.value, stamp))
        conn.commit()
    finally:
        conn.close()


def days_in_state(key: str, state: str, db_path: Path | None = None) -> int | None:
    """สัญญาณนี้อยู่สถานะเดิมติดต่อกันมากี่วัน — None ถ้าไม่มีประวัติพอ.

    ใช้ตอบ 'มันเพิ่งพัง หรือพังมานานแล้ว' ซึ่งเปลี่ยนการตัดสินใจคนละแบบ: เพิ่งเปลี่ยน =
    ข่าว, อยู่มา 60 วัน = สภาพปกติใหม่ที่ต้องเลิกตกใจแล้วเริ่มวางแผน"""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        rows = conn.execute(
            "SELECT state, recorded_at FROM signal_history WHERE key=? ORDER BY recorded_at DESC",
            (key,)).fetchall()
    finally:
        conn.close()
    if not rows or rows[0]["state"] != state:
        return None
    newest = datetime.fromisoformat(rows[0]["recorded_at"])
    oldest_same = newest
    for r in rows:
        if r["state"] != state:
            break
        oldest_same = datetime.fromisoformat(r["recorded_at"])
    return (newest - oldest_same).days
