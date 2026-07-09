"""Analysis history store (SQLite).

เก็บผลการวิเคราะห์ทุกครั้งที่ agent รัน — เพื่อ (1) ให้ UI ดึงไปแสดง
และ (2) เป็นรากฐานของ Phase 3 (cross-day change detection: เทียบวันนี้กับครั้งก่อน).

ใช้ไฟล์ DB เดียวกับ watchlist (data/watchlist.db) แต่คนละตาราง.
Summary ทั้งก้อนถูกเก็บเป็น JSON (summary_json) เพื่อความยืดหยุ่นของ schema,
ส่วนคอลัมน์ที่ต้อง query/เรียงบ่อยถูกดึงออกมาเป็นคอลัมน์แยก (denormalize เพื่อความเร็ว).
"""
import json
import sqlite3
from dataclasses import asdict, is_dataclass
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
                summary_json         TEXT NOT NULL,
                facts_json           TEXT,
                extraction_accuracy  REAL,
                extraction_json      TEXT,
                health_score         REAL,
                health_reasons_json  TEXT
            )
            """
        )
        # เรียง/กรองด้วย (ticker, เวลา) บ่อย -> ทำ index ให้ query เร็ว
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analyses_ticker_run ON analyses (ticker, run_at)"
        )
        # migration: DB เก่าที่สร้างก่อนมีคอลัมน์พวกนี้ -> เพิ่มทีละคอลัมน์ถ้ายังไม่มี
        cols = [row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()]
        for col, coltype in [
            ("facts_json", "TEXT"),
            ("extraction_accuracy", "REAL"),
            ("extraction_json", "TEXT"),
            ("health_score", "REAL"),
            ("health_reasons_json", "TEXT"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE analyses ADD COLUMN {col} {coltype}")


def _facts_to_json(facts) -> str | None:
    """list[Fact] (dataclass) -> JSON string เพื่อเทียบ metric ข้ามวัน (Phase 3)."""
    if not facts:
        return None
    rows = [asdict(f) if is_dataclass(f) else dict(f) for f in facts]
    return json.dumps(rows, ensure_ascii=False)


def save_analysis(summary, grounding: dict, facts=None, extraction: dict | None = None,
                   health: dict | None = None) -> int:
    """บันทึกผล 1 ครั้ง; คืน id ของแถวที่เพิ่ม.
    summary = Pydantic Summary, grounding = dict จาก loop (มี key 'facts' ซ้อนอยู่),
    facts = list[Fact] ดิบ (เก็บไว้ให้ change-detection เทียบตัวเลขข้ามวัน),
    extraction = dict จาก check_extraction_accuracy (Phase 4 — ความแม่นการคำนวณของเราเอง),
    health = dict จาก compute_health (score/tier/label/reasons) — เก็บทุกแถวเพื่อดู trend
    ย้อนหลัง + เห็นเหตุผลตอนนั้น ถ้าคะแนนเด้งผิดปกติวันไหน (None = ยังไม่คำนวณให้)."""
    grounding_facts = grounding.get("facts", {})
    init_db()   # idempotent: กัน 'no such table: analyses' ถ้ายังไม่เคยสร้าง (เช่น เรียกตรงไม่ผ่าน loop)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO analyses (
                ticker, run_at, fundamental_strength, valuation_view, sentiment,
                price, confidence, price_ok, news_grounded_ratio, facts_grounded_ratio,
                summary_json, facts_json, extraction_accuracy, extraction_json,
                health_score, health_reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                grounding_facts.get("facts_grounded_ratio"),
                summary.model_dump_json(),                # เก็บ Summary ทั้งก้อนเป็น JSON
                _facts_to_json(facts),                    # เก็บ facts ดิบ (อาจเป็น None ถ้าไม่ส่งมา)
                extraction.get("accuracy") if extraction else None,
                json.dumps(extraction, ensure_ascii=False) if extraction else None,
                health.get("score") if health else None,
                json.dumps(health, ensure_ascii=False) if health else None,
            ),
        )
        return cur.lastrowid


def _row_to_dict(row: sqlite3.Row) -> dict:
    """แปลงแถว -> dict และ parse summary_json กลับเป็น object ซ้อน (พร้อมส่งเป็น JSON ให้ UI)."""
    d = dict(row)
    d["price_ok"] = bool(d["price_ok"])
    d["summary"] = json.loads(d.pop("summary_json"))
    facts_json = d.pop("facts_json", None)
    d["facts"] = json.loads(facts_json) if facts_json else []   # [] ถ้าแถวเก่าไม่มี
    extraction_json = d.pop("extraction_json", None)
    d["extraction"] = json.loads(extraction_json) if extraction_json else None  # None ถ้าแถวเก่าไม่มี
    health_reasons_json = d.pop("health_reasons_json", None)
    d["health"] = json.loads(health_reasons_json) if health_reasons_json else None  # None ถ้าแถวเก่าไม่มี
    return d


def latest_per_ticker() -> list[dict]:
    """ผลล่าสุดของแต่ละ ticker (มุมมองหลักของ dashboard)."""
    init_db()   # idempotent: กัน 'no such table' บน DB/โปรเซสที่ยังไม่เคยสร้างตาราง
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
    init_db()   # idempotent: กัน 'no such table' บน DB/โปรเซสที่ยังไม่เคยสร้างตาราง
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE ticker = ? ORDER BY run_at DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
