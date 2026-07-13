"""Watchlist store (SQLite).

เก็บ ticker ที่เราจับตา พร้อม asset_type ("stock" | "crypto") ตั้งแต่แรก
เพื่อให้ระบบ asset-agnostic — loop จะอ่านจากที่นี่แล้วเลือก provider ตาม asset_type

Phase 5.5: เพิ่มมิติ 'สถานะการถือครอง' — แยก 'จับตา' (watching) ออกจาก 'ถืออยู่จริง'
(holding + entry_price/date/shares) เพราะ invalidation/thesis-stop มีน้ำหนักต่างกันมาก
ระหว่างของที่ถืออยู่ (เรื่องด่วนต้องตัดสินใจ) กับที่แค่จับตา (แค่ยังไม่ถึงจังหวะ).
"""
import sqlite3
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # ให้ query คืน row ที่เข้าถึงด้วยชื่อคอลัมน์ได้ (row["ticker"])
    return conn


def init_db() -> None:
    """สร้างตารางถ้ายังไม่มี + เพิ่มคอลัมน์ Phase 5.5 ถ้า DB เก่ายังไม่มี (migration)."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker      TEXT PRIMARY KEY,
                asset_type  TEXT NOT NULL DEFAULT 'stock',
                added_at    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'watching',   -- 'watching' | 'holding' | 'frozen'
                entry_price REAL,                               -- ราคาที่ซื้อ (เฉพาะ holding)
                entry_date  TEXT,                               -- วันที่ซื้อ (ไว้เทียบ benchmark)
                shares      REAL                                -- จำนวน/น้ำหนัก (optional)
            )
            """
        )
        # migration: DB เก่ามีแค่ 3 คอลัมน์แรก -> เพิ่มทีละคอลัมน์ถ้ายังไม่มี
        cols = [row[1] for row in conn.execute("PRAGMA table_info(watchlist)").fetchall()]
        for col, decl in [
            ("status", "TEXT NOT NULL DEFAULT 'watching'"),
            ("entry_price", "REAL"),
            ("entry_date", "TEXT"),
            ("shares", "REAL"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE watchlist ADD COLUMN {col} {decl}")


def add(ticker: str, asset_type: str = "stock") -> None:
    """เพิ่ม ticker (ถ้ามีอยู่แล้วเฉยๆ ไม่ error). สถานะเริ่มต้น = 'watching'."""
    init_db()   # idempotent: กัน 'no such table' / คอลัมน์ Phase 5.5 ขาดบน DB เก่า (เช่น ที่ CI commit ไว้)
    with _connect() as conn:
        conn.execute(
            # ใช้ ? เป็น placeholder (parameterized) กัน SQL injection — อย่าเอา f-string มายัด SQL
            "INSERT OR IGNORE INTO watchlist (ticker, asset_type, added_at) VALUES (?, ?, ?)",
            (ticker.upper(), asset_type, datetime.now().isoformat()),
        )


def remove(ticker: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))


def set_holding(ticker: str, entry_price: float, entry_date: str | None = None,
                shares: float | None = None) -> None:
    """ตั้งว่า 'ถืออยู่จริง' พร้อมราคา/วันที่ซื้อ (เพิ่มเข้า watchlist ให้ถ้ายังไม่มี).
    entry_date ไม่ระบุ -> ใช้วันนี้ (แต่ edge vs benchmark จะแม่นเมื่อใส่วันซื้อจริง)."""
    ticker = ticker.upper()
    entry_date = entry_date or date.today().isoformat()
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (ticker, asset_type, added_at) VALUES (?, 'stock', ?)",
            (ticker, datetime.now().isoformat()),
        )
        conn.execute(
            "UPDATE watchlist SET status='holding', entry_price=?, entry_date=?, shares=? WHERE ticker=?",
            (float(entry_price), entry_date, shares, ticker),
        )


def add_shares(ticker: str, price: float, shares: float) -> dict:
    """ซื้อเพิ่มใน position ที่ 'ถืออยู่' แล้ว — คำนวณ entry_price ใหม่เป็น weighted average
    ให้อัตโนมัติ (กันเลขผิดจากการคำนวณมือ). เก็บ entry_date เดิมไว้ (วันที่เริ่มสร้าง position)
    เพื่อให้ 'edge vs benchmark' ยังเทียบตั้งแต่วันแรก — ผลตอบแทนที่ได้จะเป็นของทั้ง position
    รวมกัน (ไม่ใช่แยกราย lot แบบ FIFO/LIFO).
    คืน dict สรุปก่อน/หลัง ไว้ print ให้เห็นเลขที่คำนวณได้ (ตรวจสอบได้ ไม่ใช่กล่องดำ)."""
    ticker = ticker.upper()
    row = get_entry(ticker)
    if row is None or row["status"] != "holding":
        raise ValueError(f"{ticker} ยังไม่ได้ตั้งเป็น holding — ใช้ 'hold' ตั้งครั้งแรกก่อน")
    if row["entry_price"] is None or row["shares"] is None:
        raise ValueError(f"{ticker} ไม่มี entry_price/shares เดิมให้เฉลี่ย — ใช้ 'hold' ตั้งค่าใหม่ทั้งหมดแทน")

    old_price, old_shares = float(row["entry_price"]), float(row["shares"])
    new_shares = old_shares + shares
    new_price = (old_price * old_shares + price * shares) / new_shares

    set_holding(ticker, new_price, entry_date=row["entry_date"], shares=new_shares)
    return {
        "ticker": ticker, "old_price": old_price, "old_shares": old_shares,
        "add_price": price, "add_shares": shares,
        "new_price": new_price, "new_shares": new_shares,
    }


def set_watching(ticker: str) -> None:
    """เปลี่ยนกลับเป็น 'จับตา' (ขายออกแล้ว/ยังไม่ซื้อ) — เก็บ entry เดิมไว้เผื่อดูประวัติ."""
    init_db()
    with _connect() as conn:
        conn.execute("UPDATE watchlist SET status='watching' WHERE ticker=?", (ticker.upper(),))


def set_frozen(ticker: str) -> None:
    """แช่แข็ง — ขายหมดแล้วแต่ยังอยากดูว่า 'ฟื้นหรือยัง' โดยไม่เปลืองโควตา Gemini รายวัน
    (analyze() จะข้าม ticker สถานะนี้เว้นแต่เกิน FROZEN_INTERVAL_DAYS นับจากวิเคราะห์ครั้งล่าสุด
    ดู src/agent/loop.py::_due_for_analysis). ต่างจาก remove() ตรงที่ยังอยู่ใน watchlist และ
    ยังได้รับการวิเคราะห์เป็นระยะ (แค่ถี่น้อยกว่า) แทนที่จะหยุดสนิท."""
    init_db()
    with _connect() as conn:
        conn.execute("UPDATE watchlist SET status='frozen' WHERE ticker=?", (ticker.upper(),))


def get_entry(ticker: str) -> sqlite3.Row | None:
    """คืนแถวเดียวของ ticker (ไว้ให้ performance/edge อ่าน entry_price/date)."""
    init_db()   # idempotent: กันคอลัมน์ Phase 5.5 ขาดบน DB เก่า (เช่น ที่ CI commit ไว้)
    with _connect() as conn:
        return conn.execute("SELECT * FROM watchlist WHERE ticker = ?", (ticker.upper(),)).fetchone()


def list_all() -> list[sqlite3.Row]:
    """คืนทุก ticker ในรายการ (พร้อมคอลัมน์ holding, เรียงตามลำดับที่เพิ่ม)."""
    init_db()   # idempotent: กันคอลัมน์ Phase 5.5 ขาดบน DB เก่า (เช่น ที่ CI commit ไว้)
    with _connect() as conn:
        return conn.execute("SELECT * FROM watchlist ORDER BY added_at").fetchall()


if __name__ == "__main__":
    # CLI จัดการสถานะถือครอง (สะพานก่อนมี UI):
    #   python -m src.watchlist.store list
    #   python -m src.watchlist.store hold DUOL 130.50 --date 2026-01-15 --shares 10
    #   python -m src.watchlist.store add DUOL 140 --shares 5      (ซื้อเพิ่ม -> เฉลี่ยราคาให้อัตโนมัติ)
    #   python -m src.watchlist.store watch DUOL
    #   python -m src.watchlist.store freeze SBUX                 (ขายหมดแต่อยากดูว่าฟื้นไหม -> วิเคราะห์รอบเดือนแทนรายวัน)
    #   python -m src.watchlist.store remove SBUX                 (ขายหมด/เลิกจับตา -> เอาออกจาก watchlist)
    import argparse

    init_db()
    parser = argparse.ArgumentParser(prog="python -m src.watchlist.store", description="จัดการ watchlist/holding")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    h = sub.add_parser("hold")
    h.add_argument("ticker")
    h.add_argument("entry_price", type=float)
    h.add_argument("--date", default=None, help="วันที่ซื้อ YYYY-MM-DD (ไม่ใส่ = วันนี้)")
    h.add_argument("--shares", type=float, default=None)
    a = sub.add_parser("add", help="ซื้อเพิ่มใน position ที่ถืออยู่แล้ว (เฉลี่ยราคาให้อัตโนมัติ)")
    a.add_argument("ticker")
    a.add_argument("price", type=float)
    a.add_argument("--shares", type=float, required=True)
    sub.add_parser("watch").add_argument("ticker")
    sub.add_parser("freeze", help="ขายหมดแล้วแต่อยากดูว่าฟื้นไหม -> วิเคราะห์รอบเดือนแทนรายวัน").add_argument("ticker")
    sub.add_parser("remove").add_argument("ticker")
    args = parser.parse_args()

    if args.cmd == "list":
        TAGS = {"holding": "📌 HOLD", "frozen": "🧊 FROZEN"}
        for r in list_all():
            tag = TAGS.get(r["status"], "👀 watch")
            entry = f" @ {r['entry_price']} ({r['entry_date']})" if r["status"] == "holding" and r["entry_price"] else ""
            print(f"  {tag}  {r['ticker']:6}{entry}")
    elif args.cmd == "hold":
        set_holding(args.ticker, args.entry_price, args.date, args.shares)
        print(f"ตั้ง {args.ticker.upper()} = ถืออยู่ @ {args.entry_price} ({args.date or 'วันนี้'})")
    elif args.cmd == "add":
        r = add_shares(args.ticker, args.price, args.shares)
        print(
            f"{r['ticker']}: เดิม {r['old_shares']:g} หุ้น @ {r['old_price']:.2f} "
            f"+ ซื้อเพิ่ม {r['add_shares']:g} หุ้น @ {r['add_price']:.2f} "
            f"-> รวม {r['new_shares']:g} หุ้น เฉลี่ย {r['new_price']:.2f}"
        )
    elif args.cmd == "watch":
        set_watching(args.ticker)
        print(f"ตั้ง {args.ticker.upper()} = จับตา (watching)")
    elif args.cmd == "freeze":
        set_frozen(args.ticker)
        print(f"ตั้ง {args.ticker.upper()} = แช่แข็ง (frozen) — วิเคราะห์รอบเดือนแทนรายวัน")
    elif args.cmd == "remove":
        remove(args.ticker)
        print(f"เอา {args.ticker.upper()} ออกจาก watchlist (ประวัติ analyses เดิมยังอยู่)")