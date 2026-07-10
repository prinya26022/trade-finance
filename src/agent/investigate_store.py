"""เก็บ investigation transcript (Phase 13) ลง SQLite — ไฟล์ DB เดียวกับ analyses/watchlist.

แยกตารางเพราะ investigation เป็นงานหนัก (หลาย Gemini call) รันไม่บ่อยเท่า analyze รายวัน —
เก็บล่าสุดต่อ ticker พอ (ไว้โชว์บนหน้า detail ว่า 'agent สืบยังไง' + เป็น eval artifact).
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS investigations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT NOT NULL,
                run_at     TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                conclusion TEXT NOT NULL,
                stopped    TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invest_ticker_run ON investigations (ticker, run_at)")


def save_investigation(inv) -> int:
    """inv = Investigation (มี .to_dict()). คืน id ของแถวที่เพิ่ม."""
    init_db()
    d = inv.to_dict()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO investigations (ticker, run_at, steps_json, conclusion, stopped) VALUES (?, ?, ?, ?, ?)",
            (d["ticker"], datetime.now().isoformat(timespec="seconds"),
             json.dumps(d["steps"], ensure_ascii=False), d["conclusion"], d["stopped"]),
        )
        return cur.lastrowid


def latest_investigation(ticker: str) -> dict | None:
    """investigation ล่าสุดของ ticker (พร้อม steps parse กลับเป็น list) — None ถ้ายังไม่เคยสืบ."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM investigations WHERE ticker = ? ORDER BY run_at DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["steps"] = json.loads(d.pop("steps_json"))
    return d