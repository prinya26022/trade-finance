"""เรื่องอนาคตของบริษัท 3 ข้อ (Phase 56) — พื้นฐานก่อนจะมี thesis เต็ม.

ที่มา: วิธีคิดของ CK Cheong ("ใครมองอนาคตได้ดีกว่าคือผู้ชนะ", มองสินค้า 5–10 ปี ไม่ใช่ P/E วันนี้)
แปลงเป็นสิ่งที่ตรวจได้ — ข้อ 1 อย่างเดียวคือเรื่องเล่า ข้อ 2–3 ทำให้มันผิดได้:
  1. future   : สินค้า/บริการนี้อีก 5–10 ปีจะดีขึ้นเพราะอะไร
  2. signals  : ถ้าเรื่องข้อ 1 จริง ตัวเลขอะไรต้องเกิดตามมา (ไว้เทียบกับผลวิเคราะห์รายรอบ)
  3. wrong_if : เห็นอะไรแล้วจะยอมรับว่าคิดผิด (ภาษาคน — ตัวที่เช็คด้วยเครื่องได้อยู่ใน theses.invalidation)

ทำไมแยกจาก theses: thesis ต้องมี "เหตุผลที่ถือ" เต็ม และมีแค่ตัวที่ถือ/สนใจจริงจัง (ตอนนี้ DUOL ตัวเดียว)
แต่ 3 ข้อนี้ผู้ใช้อยากได้ "ทุกตัวใน watchlist ไว้เป็นพื้นฐาน" — รวมตัวที่ยังไม่คิดจะซื้อ

author: ใครเขียนเวอร์ชันนี้ ("user" หรือ "claude-draft") — ร่างของ Claude ต้องแยกออกจากความเชื่อของผู้ใช้
ไม่งั้นวันหลังจะย้อนดูไม่ได้ว่าคิดเองหรือรับมา
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"
FIELDS = ("future", "signals", "wrong_if")
AUTHORS = {"user", "claude-draft"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stories (
                ticker     TEXT PRIMARY KEY,
                future     TEXT NOT NULL DEFAULT '',
                signals    TEXT NOT NULL DEFAULT '',
                wrong_if   TEXT NOT NULL DEFAULT '',
                author     TEXT NOT NULL DEFAULT 'user',
                updated_at TEXT NOT NULL
            )
            """
        )


def set_story(ticker: str, future: str, signals: str, wrong_if: str, author: str = "user") -> dict:
    """เขียนทับทั้ง 3 ข้อ (1 เรื่องต่อ ticker — เป็นสถานะความเชื่อปัจจุบัน ไม่ใช่เหตุการณ์แบบ decisions).
    ต้องมีครบทั้ง 3 ข้อ: ข้อ 1 อย่างเดียวคือเรื่องเล่าที่ไม่มีวันผิด ซึ่งคือสิ่งที่ส่วนนี้ตั้งใจกัน"""
    if author not in AUTHORS:
        raise ValueError(f"author ต้องเป็น {sorted(AUTHORS)}")
    vals = {k: (v or "").strip() for k, v in zip(FIELDS, (future, signals, wrong_if))}
    missing = [k for k, v in vals.items() if not v]
    if missing:
        raise ValueError(f"ต้องตอบครบ 3 ข้อ (ขาด {', '.join(missing)})")
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO stories (ticker, future, signals, wrong_if, author, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET future=excluded.future, signals=excluded.signals,
                wrong_if=excluded.wrong_if, author=excluded.author, updated_at=excluded.updated_at
            """,
            (ticker.upper(), vals["future"], vals["signals"], vals["wrong_if"], author, now),
        )
    return get_story(ticker)


def get_story(ticker: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM stories WHERE ticker = ?", (ticker.upper(),)).fetchone()
    return dict(row) if row else None


def all_stories() -> list[dict]:
    init_db()
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM stories ORDER BY ticker")]
