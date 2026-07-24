"""Macro release store (SQLite) — จำว่า 'เราเห็น/แจ้งเตือน' การประกาศล่าสุดของแต่ละ series ไปถึงไหนแล้ว.

หน้าที่เดียว: กัน radar แจ้งซ้ำ. เมื่อ FRED มี observation เดือนใหม่โผล่ (= มีการประกาศจริง)
radar จะเทียบกับ ref_date ล่าสุดที่บันทึกไว้ที่นี่ ถ้าใหม่กว่า -> แจ้งเตือน 1 ครั้ง แล้ว mark_seen.

ใช้ไฟล์ DB **แยก** (data/macro.db) ไม่ใช่ watchlist.db — เพราะ macro alert จะรันใน workflow แยก
(ถี่กว่า daily) แล้ว commit state กลับ repo; ถ้าใช้ไฟล์เดียวกับ daily job จะชน commit กัน.
self-init เหมือน store อื่นๆ (CI checkout DB มาซึ่งอาจไม่มีตารางนี้ -> ทุก read/write เรียก init_db() ก่อน).
สำคัญ: state ต้อง persist ข้ามรัน CI ไม่งั้นทุกรอบเป็น 'รอบแรก' (bootstrap เงียบ) แล้วจะไม่แจ้งเลย."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parents[2] / "data" / "macro.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_seen (
                series_key TEXT PRIMARY KEY,
                ref_date   TEXT NOT NULL,   -- เดือนอ้างอิงล่าสุดที่แจ้งไปแล้ว (YYYY-MM-DD)
                value      REAL,
                updated_at TEXT NOT NULL
            )
            """
        )


def get_seen(series_key: str) -> str | None:
    """ref_date ล่าสุดที่เคยแจ้งของ series นี้ (YYYY-MM-DD) หรือ None ถ้ายังไม่เคย."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT ref_date FROM macro_seen WHERE series_key = ?", (series_key,)
        ).fetchone()
    return row["ref_date"] if row else None


def mark_seen(series_key: str, ref_date: str, value: float | None = None) -> None:
    """บันทึกว่าแจ้ง series นี้ถึง ref_date แล้ว (upsert)."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO macro_seen (series_key, ref_date, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(series_key) DO UPDATE SET
                ref_date = excluded.ref_date,
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (series_key, ref_date, value, datetime.now().isoformat()),
        )
