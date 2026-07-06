"""Analysis history store (SQLite).

เก็บผลการวิเคราะห์ทุกครั้งที่ agent รัน — เพื่อ (1) ให้ UI ดึงไปแสดง
และ (2) เป็นรากฐานของ Phase 3 (cross-day change detection: เทียบวันนี้กับครั้งก่อน).

ใช้ไฟล์ DB เดียวกับ watchlist (data/watchlist.db) แต่คนละตาราง.
Summary ทั้งก้อนถูกเก็บเป็น JSON (summary_json) เพื่อความยืดหยุ่นของ schema,
ส่วนคอลัมน์ที่ต้อง query/เรียงบ่อยถูกดึงออกมาเป็นคอลัมน์แยก (denormalize เพื่อความเร็ว).
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
    """สร้างตาราง analyses ถ้ายังไม่มี — เรียกครั้งเดียวตอนเริ่ม"""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker               TEXT NOT NULL,
                run_at               TEXT NOT NULL,
                fundamental_strength TEXT,
                valuation_view       TEXT,
                sentiment            TEXT,
                price                REAL,
                confidence           REAL,
                price_ok             INTEGER,
                news_grounded_ratio  REAL,
                facts_grounded_ratio REAL,
                summary_json         TEXT NOT NULL
            )
            """
        )
        # เรียง/กรองด้วย (ticker, เวลา) บ่อย -> ทำ index ให้ query เร็ว
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analyses_ticker_run ON analyses (ticker, run_at)"
        )


def save_analysis(summary, grounding: dict) -> int:
    """บันทึกผล 1 ครั้ง; คืน id ของแถวที่เพิ่ม.
    summary = Pydantic Summary, grounding = dict จาก loop (มี key 'facts' ซ้อนอยู่)."""
    facts = grounding.get("facts", {})
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO analyses (
                ticker, run_at, fundamental_strength, valuation_view, sentiment,
                price, confidence, price_ok, news_grounded_ratio, facts_grounded_ratio,
                summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary.ticker,
                datetime.now().isoformat(timespec="seconds"),
                summary.fundamental_strength,
                summary.valuation_view,
                summary.sentiment,
                summary.price,
                summary.confidence,
                int(grounding.get("price_ok", False)),   # SQLite ไม่มี bool -> เก็บเป็น 0/1
                grounding.get("news_grounded_ratio"),
                facts.get("facts_grounded_ratio"),
                summary.model_dump_json(),                # เก็บ Summary ทั้งก้อนเป็น JSON
            ),
        )
        return cur.lastrowid


def _row_to_dict(row: sqlite3.Row) -> dict:
    """แปลงแถว -> dict และ parse summary_json กลับเป็น object ซ้อน (พร้อมส่งเป็น JSON ให้ UI)."""
    d = dict(row)
    d["price_ok"] = bool(d["price_ok"])
    d["summary"] = json.loads(d.pop("summary_json"))
    return d


def latest_per_ticker() -> list[dict]:
    """ผลล่าสุดของแต่ละ ticker (มุมมองหลักของ dashboard)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT a.* FROM analyses a
            JOIN (
                SELECT ticker, MAX(run_at) AS mr FROM analyses GROUP BY ticker
            ) latest ON a.ticker = latest.ticker AND a.run_at = latest.mr
            ORDER BY a.ticker
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def history(ticker: str, limit: int = 50) -> list[dict]:
    """ประวัติการวิเคราะห์ของ ticker เดียว เรียงใหม่ก่อน (ไว้ทำ timeline/trend)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE ticker = ? ORDER BY run_at DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
