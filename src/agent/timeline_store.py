"""เก็บ 'เรื่องเล่า' timeline ที่ narrate แล้ว (Phase 14) — narration ยิง Gemini จึงไม่อยาก
รันตอน render ทุกครั้ง: เก็บล่าสุดต่อ ticker ไว้ แล้วหน้า detail อ่านของที่เก็บ (events ยัง
คำนวณสดได้เพราะ deterministic/ฟรี). ไฟล์ DB เดียวกับตารางอื่น."""
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
            CREATE TABLE IF NOT EXISTS timeline_narratives (
                ticker    TEXT PRIMARY KEY,
                run_at    TEXT NOT NULL,
                narrative TEXT NOT NULL
            )
            """
        )


def save_narrative(ticker: str, narrative: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO timeline_narratives (ticker, run_at, narrative) VALUES (?, ?, ?) "
            "ON CONFLICT(ticker) DO UPDATE SET run_at=excluded.run_at, narrative=excluded.narrative",
            (ticker.upper(), datetime.now().isoformat(timespec="seconds"), narrative),
        )


def get_narrative(ticker: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM timeline_narratives WHERE ticker = ?",
                           (ticker.upper(),)).fetchone()
    return dict(row) if row else None