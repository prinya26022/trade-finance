"""Watchlist store (SQLite).

เก็บ ticker ที่เราจับตา พร้อม asset_type ("stock" | "crypto") ตั้งแต่แรก
เพื่อให้ระบบ asset-agnostic — loop จะอ่านจากที่นี่แล้วเลือก provider ตาม asset_type
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # ให้ query คืน row ที่เข้าถึงด้วยชื่อคอลัมน์ได้ (row["ticker"])
    return conn


def init_db() -> None:
    """สร้างตารางถ้ายังไม่มี — เรียกครั้งเดียวตอนเริ่ม"""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker      TEXT PRIMARY KEY,
                asset_type  TEXT NOT NULL DEFAULT 'stock',
                added_at    TEXT NOT NULL
            )
            """
        )


def add(ticker: str, asset_type: str = "stock") -> None:
    """เพิ่ม ticker (ถ้ามีอยู่แล้วเฉยๆ ไม่ error)"""
    with _connect() as conn:
        conn.execute(
            # ใช้ ? เป็น placeholder (parameterized) กัน SQL injection — อย่าเอา f-string มายัด SQL
            "INSERT OR IGNORE INTO watchlist (ticker, asset_type, added_at) VALUES (?, ?, ?)",
            (ticker.upper(), asset_type, datetime.now().isoformat()),
        )


def remove(ticker: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))


def list_all() -> list[sqlite3.Row]:
    """คืนทุก ticker ในรายการ (เรียงตามลำดับที่เพิ่ม)"""
    with _connect() as conn:
        return conn.execute(
            "SELECT ticker, asset_type, added_at FROM watchlist ORDER BY added_at"
        ).fetchall()