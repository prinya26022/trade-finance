"""data/journal.db — แยกไฟล์จาก DB อื่น (กติกาเดียวกับ aicapex/technical). self-init ทุกครั้ง.

การ upsert ต้องไม่ทับสิ่งที่คนใส่: ซิงก์จาก OKX อัปเดตได้แค่ตัวเลข (ราคา/สถานะ/กำไร) ส่วน tags,
note และบริบทกราฟที่คำนวณไว้ตอนเข้าไม้ อยู่ถาวร — ไม่งั้นซิงก์รอบถัดไปจะลบเหตุผลที่ผู้ใช้เพิ่งแตะ
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "journal.db"

NUMERIC = ("inst", "side", "status", "opened_at", "closed_at", "entry", "exit", "contracts", "ct_val",
           "lever", "margin", "pnl", "fee", "liquidated")
FIRST_SEEN = ("sl", "tp", "equity", "sl_source")          # ค่า ณ ตอนเข้าไม้ — เห็นครั้งแรกแล้วไม่เปลี่ยน
JSON_COLS = ("context", "tags")


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT NOT NULL UNIQUE,
            source      TEXT NOT NULL,           -- okx | sheet
            inst TEXT, side TEXT, status TEXT,
            opened_at TEXT, closed_at TEXT,
            entry REAL, exit REAL, contracts REAL, ct_val REAL, lever REAL, margin REAL,
            pnl REAL, fee REAL, liquidated INTEGER,
            sl REAL, tp REAL, equity REAL,
            sl_source   TEXT,                    -- entry | algo | seen (มาจากไหน — ดู stops.py)
            context     TEXT,                    -- บริบทกราฟ ณ เวลาเข้าไม้ (json)
            tags        TEXT,                    -- ปุ่มเหตุผลที่ผู้ใช้แตะ (json)
            note        TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)")}
    for col, decl in (("sl_source", "TEXT"), ("check_id", "INTEGER")):
        if col not in cols:              # DB ที่สร้างก่อนมีคอลัมน์นี้ (เครื่องผู้ใช้มีอยู่แล้ว 116 ไม้)
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")
    # เช็กลิสต์ก่อนเข้า — ทุกครั้งที่กดเช็ก ไม่ว่าจะเข้าจริงหรือไม่ (ไม่เข้าก็เป็นข้อมูล)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            side TEXT NOT NULL, entry REAL, sl REAL, tp REAL,
            result TEXT NOT NULL,
            trade_id INTEGER                     -- ไม้จริงบน OKX ที่จับคู่ได้ (check.link_checks)
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT, updated_at TEXT)")
    conn.commit()
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _val(v):
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if isinstance(v, bool):
        return int(v)
    return v


def upsert(t: dict, db_path: Path | None = None) -> tuple[int, str]:
    """คืน (id, "new" | "closed" | "updated" | "same") — "closed" = เพิ่งเปลี่ยนจากเปิดเป็นปิด"""
    with closing(_connect(db_path)) as conn:
        old = conn.execute("SELECT * FROM trades WHERE key = ?", (t["key"],)).fetchone()
        now = _now()
        if old is None:
            cols = ["key", "source", *[c for c in NUMERIC + FIRST_SEEN if c in t]]
            vals = [_val(t[c]) for c in cols]
            for c in JSON_COLS:
                if c in t:
                    cols.append(c)
                    vals.append(json.dumps(t[c], ensure_ascii=False, default=str))
            if "note" in t:
                cols.append("note")
                vals.append(t["note"])
            cur = conn.execute(f"INSERT INTO trades ({', '.join(cols)}, created_at, updated_at) "
                               f"VALUES ({', '.join('?' * len(cols))}, ?, ?)", (*vals, now, now))
            conn.commit()
            return cur.lastrowid, "new"
        sets, vals = [], []
        for c in NUMERIC:
            if c in t and t[c] is not None and _val(t[c]) != old[c]:
                sets.append(f"{c} = ?")
                vals.append(_val(t[c]))
        for c in FIRST_SEEN:
            if old[c] is None and t.get(c) is not None:
                sets.append(f"{c} = ?")
                vals.append(t[c])
        if not sets:
            return old["id"], "same"
        conn.execute(f"UPDATE trades SET {', '.join(sets)}, updated_at = ? WHERE id = ?", (*vals, now, old["id"]))
        conn.commit()
        state = "closed" if old["status"] == "open" and t.get("status") == "closed" else "updated"
        return old["id"], state


def set_stops(trade_id: int, sl: float | None, tp: float | None, source: str,
              db_path: Path | None = None) -> None:
    """เขียนทับ stop/TP ด้วยค่าที่น่าเชื่อกว่า — ใช้โดย stops.py เท่านั้น (upsert ปกติไม่ทับ)"""
    with closing(_connect(db_path)) as conn:
        conn.execute("UPDATE trades SET sl = ?, tp = COALESCE(?, tp), sl_source = ?, updated_at = ? WHERE id = ?",
                     (sl, tp, source, _now(), trade_id))
        conn.commit()


def set_context(trade_id: int, context: dict, db_path: Path | None = None) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute("UPDATE trades SET context = ? WHERE id = ?",
                     (json.dumps(context, ensure_ascii=False, default=str), trade_id))
        conn.commit()


def set_tags(trade_id: int, tags: dict, note: str | None, db_path: Path | None = None) -> bool:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute("UPDATE trades SET tags = ?, note = ?, updated_at = ? WHERE id = ?",
                           (json.dumps(tags, ensure_ascii=False), note, _now(), trade_id))
        conn.commit()
        return cur.rowcount > 0


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for c in JSON_COLS:
        d[c] = json.loads(d[c]) if d[c] else ({} if c == "tags" else None)
    d["liquidated"] = bool(d["liquidated"])
    return d


def all_trades(db_path: Path | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY COALESCE(opened_at, created_at) DESC, id DESC")
        return [_row(r) for r in rows]


def get(trade_id: int, db_path: Path | None = None) -> dict | None:
    with closing(_connect(db_path)) as conn:
        r = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return _row(r) if r else None


# ---------- เช็กลิสต์ก่อนเข้า ----------

def save_check(result: dict, db_path: Path | None = None) -> int:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute("INSERT INTO checks (created_at, side, entry, sl, tp, result) VALUES (?, ?, ?, ?, ?, ?)",
                           (result.get("asof") or _now(), result["side"], result.get("entry"), result.get("sl"),
                            result.get("tp"), json.dumps(result, ensure_ascii=False, default=str)))
        conn.commit()
        return cur.lastrowid


def all_checks(db_path: Path | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        return [dict(r) for r in conn.execute("SELECT id, created_at, side, entry, sl, tp, trade_id FROM checks")]


def link_check(check_id: int, trade_id: int, db_path: Path | None = None) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute("UPDATE checks SET trade_id = ? WHERE id = ?", (trade_id, check_id))
        conn.execute("UPDATE trades SET check_id = ? WHERE id = ?", (check_id, trade_id))
        conn.commit()


def set_meta(k: str, v, db_path: Path | None = None) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute("INSERT INTO meta (k, v, updated_at) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET "
                     "v = excluded.v, updated_at = excluded.updated_at", (k, json.dumps(v), _now()))
        conn.commit()


def get_meta(k: str, db_path: Path | None = None):
    with closing(_connect(db_path)) as conn:
        r = conn.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return json.loads(r["v"]) if r else None


def checks_since(db_path: Path | None = None) -> str | None:
    """เวลาเช็กครั้งแรก — ไม้ก่อนหน้านั้นไม่นับในกลุ่ม 'เช็กก่อนเข้า / ไม่ได้เช็ก'"""
    with closing(_connect(db_path)) as conn:
        r = conn.execute("SELECT MIN(created_at) AS m FROM checks").fetchone()
        return r["m"] if r else None
