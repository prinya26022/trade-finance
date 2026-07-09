"""Thesis store (SQLite) — Phase 5.

เก็บ "เหตุผลที่ถือ/จับตา" ของแต่ละ ticker เพื่อให้ระบบตรวจสอบได้ว่า thesis ยังอยู่ไหม
(ด่าน 4 invalidation + ด่าน 7 thesis stop + journal ตาม checklist).

เก็บ 3 อย่างต่อ ticker (hybrid — คนเขียนอิสระ + เครื่องเช็คได้):
  1. thesis        : ข้อความอิสระ "ทำไมถือ/สนใจ" -> ป้อนให้ LLM วิเคราะห์แบบรู้บริบท
  2. invalidation  : list ของ rule มีโครงสร้าง เช่น {"metric","op","value","note"}
                     -> เช็คด้วยเครื่องแบบ deterministic (ไม่เรียก LLM ไม่กิน quota)
  3. fair_value    : (ไม่บังคับ) ราคาที่ประเมินว่ายุติธรรม -> ไว้ดู margin of safety

ใช้ไฟล์ DB เดียวกับ watchlist (data/watchlist.db) แต่คนละตาราง.
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"

# operator ที่รองรับใน invalidation rule (จำกัดไว้ชุดเดียว กัน rule แปลก ๆ + eval() ปลอดภัย)
VALID_OPS = {"<", "<=", ">", ">=", "==", "!="}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """สร้างตาราง theses ถ้ายังไม่มี — 1 thesis ต่อ ticker (ticker เป็น PK, เขียนทับได้)."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS theses (
                ticker            TEXT PRIMARY KEY,
                thesis            TEXT NOT NULL,
                invalidation_json TEXT NOT NULL DEFAULT '[]',
                fair_value        REAL,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
            """
        )


def _validate_rules(rules: list[dict]) -> list[dict]:
    """ตรวจ invalidation rules ให้อยู่ในรูปที่เช็คได้จริง; โยน ValueError ถ้าผิดรูป."""
    clean = []
    for r in rules:
        metric = str(r.get("metric", "")).strip()
        op = str(r.get("op", "")).strip()
        if not metric:
            raise ValueError("invalidation rule ต้องมี 'metric'")
        if op not in VALID_OPS:
            raise ValueError(f"op '{op}' ไม่รองรับ (ใช้ได้: {sorted(VALID_OPS)})")
        try:
            value = float(r["value"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"rule ของ '{metric}' ต้องมี 'value' เป็นตัวเลข")
        clean.append({"metric": metric, "op": op, "value": value, "note": str(r.get("note", ""))})
    return clean


def set_thesis(ticker: str, thesis: str, invalidation: list[dict] | None = None,
               fair_value: float | None = None) -> None:
    """เพิ่ม/แก้ thesis ของ ticker (upsert). invalidation = list ของ rule (อาจว่าง)."""
    init_db()   # idempotent: กันกรณีตารางยังไม่ถูกสร้าง (เช่น DB ที่ CI commit ก่อนมีฟีเจอร์นี้)
    ticker = ticker.upper()
    rules = _validate_rules(invalidation or [])
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO theses (ticker, thesis, invalidation_json, fair_value, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                thesis            = excluded.thesis,
                invalidation_json = excluded.invalidation_json,
                fair_value        = excluded.fair_value,
                updated_at        = excluded.updated_at
            """,
            (ticker, thesis, json.dumps(rules, ensure_ascii=False), fair_value, now, now),
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["invalidation"] = json.loads(d.pop("invalidation_json"))
    return d


def get_thesis(ticker: str) -> dict | None:
    """คืน thesis ของ ticker (dict มี key 'invalidation' เป็น list แล้ว) หรือ None ถ้ายังไม่มี."""
    init_db()   # idempotent: กัน 'no such table: theses' บน DB ที่สร้างก่อนมีฟีเจอร์นี้
    with _connect() as conn:
        row = conn.execute("SELECT * FROM theses WHERE ticker = ?", (ticker.upper(),)).fetchone()
        return _row_to_dict(row) if row else None


def delete_thesis(ticker: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM theses WHERE ticker = ?", (ticker.upper(),))


def all_theses() -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM theses ORDER BY ticker").fetchall()
        return [_row_to_dict(r) for r in rows]


def _parse_rule(s: str) -> dict:
    """แปลง rule แบบกระชับ 'METRIC OP VALUE | note' -> dict (ไว้ใช้ใน CLI).
    เช่น 'Operating Margin < 10 | core profit หลุด'."""
    note = ""
    if "|" in s:
        s, note = s.split("|", 1)
    for op in ("<=", ">=", "==", "!=", "<", ">"):   # ยาวก่อน กัน '<' ชน '<='
        if op in s:
            metric, value = s.split(op, 1)
            return {"metric": metric.strip(), "op": op, "value": float(value), "note": note.strip()}
    raise ValueError(f"rule ผิดรูป: '{s}' (ต้องมี operator เช่น \"Operating Margin < 10\")")


if __name__ == "__main__":
    # CLI จัดการ thesis (สะพานก่อนมี UI):
    #   python -m src.thesis.store list
    #   python -m src.thesis.store get SBUX
    #   python -m src.thesis.store delete SBUX
    #   python -m src.thesis.store set SBUX "ถือเพราะแบรนด์แข็ง คาดกำไรฟื้น" \
    #       --fair 90 --rule "Operating Margin < 10 | core profit หลุด" --rule "ROE < 0"
    import argparse
    import json as _json

    init_db()
    parser = argparse.ArgumentParser(prog="python -m src.thesis.store", description="จัดการ thesis ต่อ ticker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("get").add_argument("ticker")
    sub.add_parser("delete").add_argument("ticker")
    s = sub.add_parser("set")
    s.add_argument("ticker")
    s.add_argument("thesis")
    s.add_argument("--fair", type=float, default=None)
    s.add_argument("--rule", action="append", default=[], metavar='"METRIC OP VALUE | note"')
    args = parser.parse_args()

    if args.cmd == "list":
        rows = all_theses()
        print(f"{len(rows)} thesis:")
        for t in rows:
            print(f"  {t['ticker']:6} | {t['thesis'][:45]} | rules={len(t['invalidation'])} | fair={t['fair_value']}")
    elif args.cmd == "get":
        print(_json.dumps(get_thesis(args.ticker), ensure_ascii=False, indent=2))
    elif args.cmd == "delete":
        delete_thesis(args.ticker)
        print(f"ลบ thesis ของ {args.ticker.upper()} แล้ว")
    elif args.cmd == "set":
        rules = [_parse_rule(r) for r in args.rule]
        set_thesis(args.ticker, args.thesis, invalidation=rules, fair_value=args.fair)
        print(f"บันทึก thesis ของ {args.ticker.upper()} ({len(rules)} rules) แล้ว")
