"""ที่เก็บบทวิเคราะห์ที่ 'คนแปะให้ Claude อ่านในแชท' แล้วนำผลกลับมาบันทึก (Phase 33).

ทำไมต้องแยกตาราง ไม่ยัดรวมกับ analyses:
- คนละจังหวะเวลา: analyses = อัตโนมัติทุกวัน (Gemini), ตารางนี้ = เดือนละครั้ง (คนกดเอง)
- คนละความน่าเชื่อของ pipeline: แถวนี้ผ่านมือคน (copy/paste) ไม่ได้มาจาก API call ที่ตรวจสอบ
  ย้อนหลังได้ — ถ้าปนกัน ทุกที่ที่นับ 'ประวัติการวิเคราะห์' (changes, timeline, scorecard,
  performance) จะเห็นแถวเดือนละครั้งโผล่มาปนกับรายวันโดยไม่รู้ตัว แล้วสถิติเพี้ยนเงียบๆ
- แยกไว้ทำให้ 'เทียบสองสำนัก' เป็นการ join ที่ตั้งใจ (ดู src/agent/compare.py) ไม่ใช่ผลข้างเคียง

ใช้ไฟล์ DB เดียวกับ watchlist/analyses (data/watchlist.db) คนละตาราง เหมือน store อื่นๆ.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"

# 1 ticker ต่อ 1 งวด ต่อ 1 โมเดล = 1 แถว — แปะซ้ำ/แก้แล้วนำเข้าใหม่ = ทับของเดิม ไม่ใช่เพิ่มแถว
# (การนำเข้าด้วยมือมีโอกาสทำซ้ำสูงมาก ถ้าปล่อยให้ซ้ำได้ การเทียบจะนับซ้ำโดยไม่มีใครรู้)
_UNIQUE = "uq_claude_ticker_period_model"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claude_analyses (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker               TEXT NOT NULL,
                period               TEXT NOT NULL,   -- งวด YYYY-MM (สรุปรายเดือน)
                model                TEXT NOT NULL,   -- ชื่อโมเดลที่ตอบ (บันทึกไว้เพื่อเทียบข้ามรุ่น)
                run_at               TEXT NOT NULL,   -- เวลาที่ 'นำเข้า' ผล
                pack_created_at      TEXT,            -- เวลาที่ export ข้อมูลออกไป (= วันที่ของ snapshot)
                analysis_id          INTEGER,         -- แถว analyses (Gemini) ที่ใช้ข้อมูลชุดเดียวกัน
                fundamental_strength TEXT,
                valuation_view       TEXT,
                sentiment            TEXT,
                price                REAL,
                confidence           REAL,
                price_ok             INTEGER,
                news_grounded_ratio  REAL,
                facts_grounded_ratio REAL,
                summary_json         TEXT NOT NULL,
                grounding_json       TEXT,
                notes                TEXT,
                framework_version    TEXT     -- checklist/TASK ที่ใช้ตอนนั้น (ดู summarize.framework_version)
            )
            """
        )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {_UNIQUE} "
            "ON claude_analyses (ticker, period, model)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_claude_period ON claude_analyses (period)"
        )
        # migration: ตารางที่สร้างไว้ก่อนมีคอลัมน์นี้ (CREATE TABLE IF NOT EXISTS ไม่เพิ่มให้เอง)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(claude_analyses)").fetchall()]
        for col, coltype in [("framework_version", "TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE claude_analyses ADD COLUMN {col} {coltype}")


def save(summary, grounding: dict, period: str, model: str,
         pack_created_at: str | None = None, analysis_id: int | None = None,
         notes: str | None = None, framework_version: str | None = None) -> int:
    """บันทึก/ทับ 1 แถว; คืน id. summary = Pydantic Summary (ตัวเดียวกับฝั่ง Gemini เป๊ะ —
    นั่นคือเหตุผลที่ export บังคับให้ Claude ตอบตาม schema เดิม: เทียบกันได้ตรงๆ)."""
    init_db()
    grounding_facts = grounding.get("facts", {})
    with _connect() as conn:
        cur = conn.execute(
            f"""
            INSERT INTO claude_analyses (
                ticker, period, model, run_at, pack_created_at, analysis_id,
                fundamental_strength, valuation_view, sentiment, price, confidence,
                price_ok, news_grounded_ratio, facts_grounded_ratio,
                summary_json, grounding_json, notes, framework_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, period, model) DO UPDATE SET
                run_at = excluded.run_at,
                pack_created_at = excluded.pack_created_at,
                analysis_id = excluded.analysis_id,
                fundamental_strength = excluded.fundamental_strength,
                valuation_view = excluded.valuation_view,
                sentiment = excluded.sentiment,
                price = excluded.price,
                confidence = excluded.confidence,
                price_ok = excluded.price_ok,
                news_grounded_ratio = excluded.news_grounded_ratio,
                facts_grounded_ratio = excluded.facts_grounded_ratio,
                summary_json = excluded.summary_json,
                grounding_json = excluded.grounding_json,
                notes = excluded.notes,
                framework_version = excluded.framework_version
            """,
            (
                summary.ticker.upper(),
                period,
                model,
                datetime.now().isoformat(timespec="seconds"),
                pack_created_at,
                analysis_id,
                summary.fundamental_strength,
                summary.valuation_view,
                summary.sentiment,
                summary.price,
                summary.confidence,
                int(grounding.get("price_ok", False)),
                grounding.get("news_grounded_ratio"),
                grounding_facts.get("facts_grounded_ratio"),
                summary.model_dump_json(),
                json.dumps(grounding, ensure_ascii=False),
                notes,
                framework_version,
            ),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM claude_analyses WHERE ticker = ? AND period = ? AND model = ?",
            (summary.ticker.upper(), period, model),
        ).fetchone()
        return row["id"]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["price_ok"] = bool(d["price_ok"])
    d["summary"] = json.loads(d.pop("summary_json"))
    grounding_json = d.pop("grounding_json", None)
    d["grounding"] = json.loads(grounding_json) if grounding_json else None
    return d


def for_period(period: str) -> list[dict]:
    """ทุก ticker ของงวดนั้น (เรียงตามชื่อ) — มุมมองหลักของหน้าเทียบผล."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM claude_analyses WHERE period = ? ORDER BY ticker", (period,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def history(ticker: str, limit: int = 24) -> list[dict]:
    """ประวัติรายเดือนของ ticker เดียว ใหม่ -> เก่า."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM claude_analyses WHERE ticker = ? ORDER BY period DESC LIMIT ?",
            (ticker.upper(), limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def periods() -> list[str]:
    """งวดที่มีข้อมูลแล้ว ใหม่ -> เก่า (ให้ UI/CLI เลือกงวดได้โดยไม่ต้องเดา)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT period FROM claude_analyses ORDER BY period DESC"
        ).fetchall()
    return [r["period"] for r in rows]
