"""จำสถานะกราฟรอบก่อนของแต่ละ ticker — เพื่อส่งเฉพาะ **"อะไรเปลี่ยน"** ไม่ใช่ภาพเดิมทุกวัน.

DB แยกไฟล์ (data/technical.db) เหตุผลเดียวกับ aicapex/macro: workflow คนละตัว commit DB กลับ
repo คนละรอบ ใช้ไฟล์ร่วมกันจะชน commit กันเอง. self-init ทุก read/write — CI checkout DB ที่
commit ไว้ซึ่งอาจเก่ากว่าสคีมาปัจจุบัน

แยก `tech_state` (ตอนนี้เป็นอะไร) กับ `tech_history` (เคยเป็นอะไรมาบ้าง) เพราะ "อยู่ในขาลงมา
12 สัปดาห์" กับ "อยู่ในขาลง" เป็นคนละข้อเท็จจริง และอันแรกตอบจากอันหลังไม่ได้ (Phase 49)
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "technical.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tech_state (
            ticker      TEXT PRIMARY KEY,
            tier        TEXT NOT NULL,
            score       INTEGER,
            last_week   TEXT,
            version     TEXT NOT NULL,       -- engine version ของเกณฑ์ที่ให้ tier นี้ (Phase 37)
            payload     TEXT NOT NULL,       -- ผลเต็มล่าสุด — หน้าเว็บ (53.5) อ่านจากตรงนี้ ไม่ดึงเอง
            updated_at  TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tech_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            asof        TEXT NOT NULL,
            tier        TEXT NOT NULL,
            score       INTEGER,
            last_week   TEXT,
            version     TEXT NOT NULL,
            payload     TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tech_hist ON tech_history(ticker, asof)")
    conn.commit()


def states(db_path: Path | None = None) -> dict[str, dict]:
    """{ticker: แถว tech_state} — {} ถ้ายังไม่เคยรัน."""
    with closing(_connect(db_path)) as conn:
        return {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM tech_state")}


def record(ticker: str, result: dict, version: str, update_state: bool = True,
           db_path: Path | None = None, now: datetime | None = None) -> None:
    """ต่อท้ายประวัติเสมอ; ทับ state เฉพาะเมื่อ update_state (ผล "วัดไม่ได้" ไม่ทับ — ข้อ radar.py)."""
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    payload = json.dumps(result, ensure_ascii=False)
    row = (ticker, result["tier"], result.get("score"), result.get("last_week"), version, payload)
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO tech_history (ticker, tier, score, last_week, version, payload, asof, "
            "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (*row, result.get("asof", ts[:10]), ts))
        if update_state:
            conn.execute(
                "INSERT INTO tech_state (ticker, tier, score, last_week, version, payload, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(ticker) DO UPDATE SET tier=excluded.tier, "
                "score=excluded.score, last_week=excluded.last_week, version=excluded.version, "
                "payload=excluded.payload, updated_at=excluded.updated_at", (*row, ts))
        conn.commit()
