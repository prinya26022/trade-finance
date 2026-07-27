"""Decision journal (Phase 27).

จดทุกครั้งที่ตัดสินใจ "ซื้อ/ผ่าน/รอ/ขาย/ลด" ต่อ ticker ตัวหนึ่ง — รวมถึงตอน "ผ่าน" ซึ่งเดิม
หายไปเงียบๆ ไม่มีที่บันทึกเลย (เทียบกับ theses ที่จดแค่ตัวที่ถือ/สนใจจริงจัง).

เหตุผลที่ต้องมี: วิธีลงทุนปัจจุบันมี 2 gate ซ้อนกัน — (1) health score (ระบบคำนวณอัตโนมัติ,
มีบันทึกครบใน analyses อยู่แล้ว) และ (2) กราฟ/Elliott Wave (ตัดสินด้วยตาคน, ไม่เคยถูกบันทึก
ที่ไหนเลย) เมื่อ gate 2 บอก "ไม่เข้า" ทั้งที่ gate 1 คะแนนสูง ระบบไม่มีทางรู้ภายหลังว่าการรอนั้น
ถูกหรือผิด — ตารางนี้จดไว้เพื่อย้อนกลับมาวัด (ดู eval ที่จะต่อยอดทีหลัง เทียบผลตอบแทนของ
"ตะกร้า health อย่างเดียว" กับ "ตะกร้าจริงที่รอ gate 2 ด้วย").

gate2 เป็น free-form note ไม่ใช่ระบบคำนวณ — Elliott Wave/กราฟ analysis เป็นคนละโปรเจกต์ที่
แยกออกไปแล้ว (จงใจ ไม่ผูก schema กับมัน) ที่นี่แค่เก็บว่า "ตอนนั้นเช็คแล้วผลเป็นยังไง" พอ.

ใช้ไฟล์ DB เดียวกับ watchlist (data/watchlist.db) แต่คนละตาราง.
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"

VALID_ACTIONS = {"buy", "pass", "wait", "sell", "trim"}
VALID_GATE2 = {"ready", "not_ready", "n/a"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT NOT NULL,
                decided_at   TEXT NOT NULL,
                action       TEXT NOT NULL,
                health_score REAL,
                price        REAL,
                gate2        TEXT NOT NULL DEFAULT 'n/a',
                gate2_note   TEXT NOT NULL DEFAULT '',
                reason       TEXT NOT NULL DEFAULT '',
                conviction   INTEGER
            )
            """
        )


def log_decision(
    ticker: str,
    action: str,
    health_score: float | None = None,
    price: float | None = None,
    gate2: str = "n/a",
    gate2_note: str = "",
    reason: str = "",
    conviction: int | None = None,
) -> dict:
    """บันทึกการตัดสินใจ 1 ครั้ง (append-only — ไม่ upsert เหมือน thesis เพราะแต่ละครั้งคือ
    เหตุการณ์แยกกัน ไม่ใช่สถานะปัจจุบัน). โยน ValueError ถ้า action/gate2 ไม่อยู่ในชุดที่รองรับ
    หรือ conviction นอกช่วง 1-5."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"action '{action}' ไม่รองรับ (ใช้ได้: {sorted(VALID_ACTIONS)})")
    if gate2 not in VALID_GATE2:
        raise ValueError(f"gate2 '{gate2}' ไม่รองรับ (ใช้ได้: {sorted(VALID_GATE2)})")
    if conviction is not None and not (1 <= conviction <= 5):
        raise ValueError("conviction ต้องอยู่ระหว่าง 1-5")

    init_db()
    ticker = ticker.upper()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions
                (ticker, decided_at, action, health_score, price, gate2, gate2_note, reason, conviction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, now, action, health_score, price, gate2, gate2_note, reason, conviction),
        )
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_decisions(ticker: str | None = None, limit: int = 100) -> list[dict]:
    """ประวัติการตัดสินใจ ใหม่ก่อน — ticker=None คืนทุก ticker (ไว้ทำ eval รวมพอร์ต ทีหลัง)."""
    init_db()
    with _connect() as conn:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT ?",
                (ticker.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY decided_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    # CLI จด decision (สะพานก่อนมี UI):
    #   python -m src.decisions.store log DUOL buy --health 9.9 --price 119.51 \
    #       --gate2 ready --gate2-note "wave 4 จบแล้ว, breakout confirm" --reason "..." --conviction 4
    #   python -m src.decisions.store list [TICKER]
    import argparse

    init_db()
    parser = argparse.ArgumentParser(prog="python -m src.decisions.store", description="จด decision journal")
    sub = parser.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log")
    lg.add_argument("ticker")
    lg.add_argument("action", choices=sorted(VALID_ACTIONS))
    lg.add_argument("--health", type=float, default=None, dest="health_score")
    lg.add_argument("--price", type=float, default=None)
    lg.add_argument("--gate2", choices=sorted(VALID_GATE2), default="n/a")
    lg.add_argument("--gate2-note", default="", dest="gate2_note")
    lg.add_argument("--reason", default="")
    lg.add_argument("--conviction", type=int, default=None, choices=[1, 2, 3, 4, 5])

    ls = sub.add_parser("list")
    ls.add_argument("ticker", nargs="?", default=None)

    args = parser.parse_args()

    if args.cmd == "log":
        d = log_decision(
            args.ticker, args.action, health_score=args.health_score, price=args.price,
            gate2=args.gate2, gate2_note=args.gate2_note, reason=args.reason, conviction=args.conviction,
        )
        print(f"บันทึกแล้ว #{d['id']}: {d['ticker']} {d['action']} @ {d['price']} (health={d['health_score']}, gate2={d['gate2']})")
    elif args.cmd == "list":
        rows = list_decisions(args.ticker)
        print(f"{len(rows)} decisions:")
        for r in rows:
            print(
                f"  #{r['id']:<4} {r['decided_at']} {r['ticker']:6} {r['action']:5} "
                f"health={r['health_score']} price={r['price']} gate2={r['gate2']:9} conv={r['conviction']}"
            )
