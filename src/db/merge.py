"""รวมไฟล์ SQLite สองฝั่งที่แตกกิ่งกัน — แบบเทียบทีละแถว ไม่ใช่เลือกทั้งไฟล์.

ทำไมต้องมี: `data/watchlist.db` ถูกเขียนจากสองที่ที่ไม่เห็นกัน — CI commit ผลรอบรายวัน
ทุกวัน ส่วนเราแก้ watchlist/thesis/decision ผ่านหน้าเว็บ. พอ commit ค้างข้ามวัน git จะชน
ที่ไฟล์นี้ทุกครั้ง และเพราะเป็น binary ทางออกที่ git มีให้คือ "เอาของฝั่งใดฝั่งหนึ่ง"
ซึ่งแปลว่าทิ้งงานของอีกฝั่งเสมอ. รอบก่อนรอดมาได้เพราะบังเอิญ local เป็นสับเซตของ CI พอดี
— พอเริ่มแก้ DB ผ่าน UI ความบังเอิญนั้นหมดอายุทันที.

หลักการ: เทียบสามทาง (base = จุดที่ยังเหมือนกัน, ours, theirs) ทีละแถว
  - ฝั่งเดียวแก้                -> เอาฝั่งที่แก้
  - ฝั่งเดียวลบ                 -> ลบจริง (ลบใน UI ต้องมีผล ไม่ใช่ถูก CI เขียนกลับมา)
  - ต่างฝั่งต่างเพิ่มแถวใหม่      -> เอาทั้งคู่; ถ้า id ชนกันก็ย้าย id ให้ตัวใหม่ แล้วตามแก้
                                 คอลัมน์ที่อ้าง id นั้นให้ด้วย (claude_analyses.analysis_id)
  - แถวเดียวกันแก้ทั้งสองฝั่งคนละแบบ -> ตัดสินด้วยคอลัมน์เวลา (ใหม่ชนะ) เสมอกันเอา ours
    แล้ว **รายงานออกมาทุกครั้ง** — งานนี้ห้ามเงียบ ตัดสินแทนคนใช้แล้วไม่บอกก็ไม่ต่างจากทำข้อมูลหาย

ไม่มี base (เช่นสั่งรวมสองไฟล์เฉยๆ) ก็ยังทำงานได้ แต่จะกลายเป็น union ล้วน —
"ลบ" แยกไม่ออกจาก "ยังไม่เคยมี" จึงไม่ลบอะไรเลย. โหมดนี้จะถูกทำเครื่องหมายไว้ในรายงาน.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ตารางที่รู้จัก: บอก "ตัวตนจริง" ของแถว ซึ่งไม่ใช่ id เสมอไป.
#   id_col = surrogate key ที่ย้ายเลขได้ (AUTOINCREMENT) — สองฝั่งแจกเลขกันเองจึงชนกันได้
#   key    = สิ่งที่ทำให้แถวเป็นแถวเดิม แม้เลข id จะเปลี่ยน
#   newest = คอลัมน์เวลาไว้ตัดสินตอนชนกันจริงๆ
#   refs   = คอลัมน์ที่อ้าง id ของตารางอื่น -> ต้องตามแก้เมื่อ id ถูกย้าย
@dataclass(frozen=True)
class TableSpec:
    id_col: str | None = None
    key: tuple[str, ...] = ()
    newest: str | None = None
    refs: dict[str, str] = field(default_factory=dict)


SPECS: dict[str, TableSpec] = {
    # log รายวัน: ซ้ำ ticker ได้ แต่ (ticker, run_at) เดียวกันคือรอบเดียวกัน
    "analyses": TableSpec(id_col="id", key=("ticker", "run_at"), newest="run_at"),
    # ผลจากแชท: 1 แถวต่อ (หุ้น, งวด, โมเดล) — และผูกกลับไปที่แถว analyses ด้วย id
    "claude_analyses": TableSpec(id_col="id", key=("ticker", "period", "model"),
                                 newest="run_at", refs={"analysis_id": "analyses"}),
    "decisions": TableSpec(id_col="id", key=("ticker", "decided_at", "action"),
                           newest="decided_at"),
    "investigations": TableSpec(id_col="id", key=("ticker", "run_at"), newest="run_at"),
    # ตารางที่คนแก้ผ่าน UI: PK คือตัวตน ไม่มี id ให้ย้าย
    "watchlist": TableSpec(key=("ticker",)),
    "theses": TableSpec(key=("ticker",), newest="updated_at"),
    "settings": TableSpec(key=("key",)),
    "timeline_narratives": TableSpec(key=("ticker",), newest="run_at"),
    "macro_seen": TableSpec(key=("series_key",), newest="updated_at"),
}

OURS, THEIRS, BASE = "ours", "theirs", "base"


# ---------- อ่านโครงสร้าง ----------

def _connect(path: str | os.PathLike | None) -> sqlite3.Connection:
    """ไฟล์ที่ไม่มี/ว่าง = ฝั่งนั้นไม่มีข้อมูล — เปิดเป็น DB ในหน่วยความจำ ไม่สร้างไฟล์ทิ้งไว้."""
    if path is None:
        return sqlite3.connect(":memory:")
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return sqlite3.connect(":memory:")
    conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def _aux_sql(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('index','view','trigger') "
        "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    return {r[1]: (r[2] or "") for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _pk_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = [r for r in conn.execute(f'PRAGMA table_info("{table}")') if r[5]]
    rows.sort(key=lambda r: r[5])
    return tuple(r[1] for r in rows)


def spec_for(table: str, conn: sqlite3.Connection) -> TableSpec:
    """ตารางที่ยังไม่ได้ลงทะเบียนก็ต้องรวมได้ ไม่ใช่ถูกข้ามเงียบๆ ตอนมีคนเพิ่มตารางใหม่."""
    if table in SPECS:
        return SPECS[table]
    ddl = _tables(conn).get(table, "")
    pk = _pk_columns(conn, table)
    cols = _columns(conn, table)
    if len(pk) == 1 and "AUTOINCREMENT" in ddl.upper():
        others = tuple(c for c in cols if c != pk[0])
        return TableSpec(id_col=pk[0], key=others)
    if pk:
        return TableSpec(key=pk)
    return TableSpec(key=tuple(cols))       # ไม่มี PK -> ทั้งแถวคือตัวตน (union แบบ set)


# ---------- สร้างโครง out ----------

def _build_schema(out: sqlite3.Connection, sides: list[tuple[str, sqlite3.Connection]]) -> None:
    """โครงของ out = ยูเนียนของทั้งสามฝั่ง.

    จำเป็นเพราะ schema ก็แตกกิ่งได้เหมือนข้อมูล: ฝั่งเราอาจรัน migration ที่เพิ่ม
    คอลัมน์ framework_version ไปแล้ว ขณะที่ DB ของ CI ยังเป็นของก่อนหน้า. ถ้าเลือกโครง
    ของฝั่งใดฝั่งหนึ่ง ข้อมูลของอีกฝั่งจะหายทั้งคอลัมน์โดยไม่มีใครเห็น.
    """
    best: dict[str, tuple[str, int]] = {}          # table -> (ddl, จำนวนคอลัมน์)
    for _, conn in sides:
        for name, ddl in _tables(conn).items():
            n = len(_columns(conn, name))
            if name not in best or n > best[name][1]:
                best[name] = (ddl, n)

    for name, (ddl, _) in best.items():
        out.execute(ddl)
        have = _columns(out, name)
        for _, conn in sides:
            for col, ctype in _columns(conn, name).items():
                if col not in have:
                    # คอลัมน์ที่มาจาก migration ของอีกฝั่ง — เติมแบบ nullable ล้วน
                    # (constraint เดิมจะกลับมาเองตอน init_db() ของโปรเจกต์รันครั้งหน้า)
                    out.execute(f'ALTER TABLE "{name}" ADD COLUMN "{col}" {ctype}')
                    have[col] = ctype

    for _, conn in sides:
        for sql in _aux_sql(conn):
            try:
                out.execute(sql)
            except sqlite3.OperationalError:
                pass                                # มีอยู่แล้วจากอีกฝั่ง


# ---------- รวมทีละแถว ----------

def _read(conn: sqlite3.Connection, table: str, cols: list[str]) -> list[dict[str, Any]]:
    if table not in _tables(conn):
        return []
    have = _columns(conn, table)
    picked = [c for c in cols if c in have]
    missing = {c: None for c in cols if c not in have}   # คอลัมน์ที่ฝั่งนี้ยังไม่ได้ migrate
    quoted = ", ".join(f'"{c}"' for c in picked)
    rows = conn.execute(f'SELECT {quoted} FROM "{table}"')
    return [{c: r[i] for i, c in enumerate(picked)} | missing for r in rows]


def _key_of(row: dict, key: tuple[str, ...]) -> tuple:
    return tuple(row.get(c) for c in key)


def _same(a: dict | None, b: dict | None, cols: Iterable[str]) -> bool:
    if a is None or b is None:
        return a is b
    return all(a.get(c) == b.get(c) for c in cols)


def _newer(a: dict, b: dict, spec: TableSpec) -> bool:
    """a ใหม่กว่า b ไหม — เวลาเป็น ISO string จึงเทียบตรงๆ ได้. ไม่มีข้อมูลเวลา = ไม่ใหม่กว่า."""
    if not spec.newest:
        return False
    va, vb = a.get(spec.newest), b.get(spec.newest)
    if va is None or vb is None:
        return False
    return str(va) > str(vb)


class _Report:
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, int]] = {}
        self.conflicts: list[dict] = []

    def bump(self, table: str, what: str, n: int = 1) -> None:
        self.tables.setdefault(table, {}).setdefault(what, 0)
        self.tables[table][what] += n

    def conflict(self, table: str, key: tuple, kind: str, chose: str, detail: str = "") -> None:
        self.conflicts.append({"table": table, "key": key, "kind": kind,
                               "chose": chose, "detail": detail})
        self.bump(table, "conflicts")


def _resolve(b: dict | None, o: dict | None, t: dict | None, *,
             spec: TableSpec, cols: list[str], table: str, key: tuple,
             rep: _Report) -> tuple[dict | None, str]:
    """หัวใจของสามทาง: คืน (แถวที่เลือก | None ถ้าลบ, มาจากฝั่งไหน)."""
    if o is None and t is None:
        if b is not None:
            rep.bump(table, "deleted")
        return None, OURS
    if _same(o, t, cols):                       # สองฝั่งลงเอยเหมือนกัน ไม่ต้องตัดสินอะไร
        if b is None:
            rep.bump(table, "added_ours")
        return o, OURS

    if b is None:                               # ไม่เคยมีมาก่อน = ต่างฝั่งต่างเพิ่ม
        if o is None:
            rep.bump(table, "added_theirs")
            return t, THEIRS
        if t is None:
            rep.bump(table, "added_ours")
            return o, OURS
        win, side = (t, THEIRS) if _newer(t, o, spec) else (o, OURS)
        rep.conflict(table, key, "เพิ่มแถวเดียวกันทั้งสองฝั่ง คนละเนื้อหา", side)
        return win, side

    if o is None:
        if _same(t, b, cols):                   # เราลบ อีกฝั่งไม่แตะ -> ลบจริง
            rep.bump(table, "deleted")
            return None, OURS
        # ลบฝั่งหนึ่ง แก้อีกฝั่ง: เก็บไว้ก่อน แล้วบอก — คืนข้อมูลง่ายกว่ากู้ข้อมูลที่หายไป
        rep.conflict(table, key, "ฝั่งเราลบ แต่อีกฝั่งแก้", THEIRS, "เก็บแถวไว้ ลบเองได้ถ้ายังตั้งใจลบ")
        return t, THEIRS
    if t is None:
        if _same(o, b, cols):
            rep.bump(table, "deleted")
            return None, OURS
        rep.conflict(table, key, "อีกฝั่งลบ แต่ฝั่งเราแก้", OURS, "เก็บแถวไว้ ลบเองได้ถ้ายังตั้งใจลบ")
        return o, OURS

    if _same(o, b, cols):                       # ฝั่งเดียวแก้ -> เอาฝั่งที่แก้
        rep.bump(table, "updated_theirs")
        return t, THEIRS
    if _same(t, b, cols):
        rep.bump(table, "updated_ours")
        return o, OURS

    win, side = (t, THEIRS) if _newer(t, o, spec) else (o, OURS)
    changed = [c for c in cols if o.get(c) != t.get(c)]
    rep.conflict(table, key, "แก้ทั้งสองฝั่งคนละแบบ", side, "คอลัมน์: " + ", ".join(changed[:6]))
    return win, side


def _merge_table(table: str, spec: TableSpec, cols: list[str],
                 base: list[dict], ours: list[dict], theirs: list[dict],
                 rep: _Report) -> tuple[list[tuple[dict, str]], dict[tuple[str, Any], Any]]:
    """คืนแถวที่รวมแล้ว (พร้อมบอกว่ามาจากฝั่งไหน) และตารางแปลง id ที่ถูกย้าย."""
    out: list[tuple[dict, str]] = []
    remap: dict[tuple[str, Any], Any] = {}

    if not spec.id_col:
        idx = [{_key_of(r, spec.key): r for r in side} for side in (base, ours, theirs)]
        for key in dict.fromkeys([k for m in idx for k in m]):
            row, side = _resolve(idx[0].get(key), idx[1].get(key), idx[2].get(key),
                                 spec=spec, cols=cols, table=table, key=key, rep=rep)
            if row is not None:
                out.append((dict(row), side))
                rep.bump(table, "rows")
        return out, remap

    # ตารางที่มี id: แถวที่เคยมีใน base ใช้ id จับคู่ได้ตรงๆ (เลขเดิมหมายถึงแถวเดิมทั้งสองฝั่ง)
    idc = spec.id_col
    b_id = {r[idc]: r for r in base}
    o_id = {r[idc]: r for r in ours}
    t_id = {r[idc]: r for r in theirs}

    # id ที่ "เคยมี" ทุกตัวถูกจองไว้ แม้แถวจะถูกลบไปแล้ว — ถ้าเอาเลขที่ลบแล้วไปใช้ซ้ำ
    # แถวอื่นที่ยังอ้างเลขนั้นค้างอยู่จะกลายเป็นชี้ผิดแถวเงียบๆ แทนที่จะถูกจับได้ว่าสายขาด
    used: set[Any] = set(b_id)
    for rid, brow in b_id.items():
        row, side = _resolve(brow, o_id.get(rid), t_id.get(rid),
                             spec=spec, cols=cols, table=table,
                             key=_key_of(brow, spec.key), rep=rep)
        if row is not None:
            row = dict(row)
            row[idc] = rid                      # id ของแถวเก่าห้ามขยับ มีคนอ้างถึงอยู่
            out.append((row, side))
            used.add(rid)
            rep.bump(table, "rows")

    # แถวใหม่: id เป็นเลขที่แต่ละฝั่งแจกเอง จึงจับคู่ด้วย "ตัวตนจริง" แทน
    new_o = [r for r in ours if r[idc] not in b_id]
    new_t = [r for r in theirs if r[idc] not in b_id]
    by_key: dict[tuple, tuple[dict, str]] = {}
    for r in new_o:
        by_key[_key_of(r, spec.key)] = (r, OURS)
        rep.bump(table, "added_ours")
    for r in new_t:
        key = _key_of(r, spec.key)
        if key in by_key:                       # เหตุการณ์เดียวกันถูกบันทึกทั้งสองฝั่ง -> ไม่ทำซ้ำ
            other = by_key[key][0]
            if not _same(r, other, [c for c in cols if c != idc]):
                win = (r, THEIRS) if _newer(r, other, spec) else by_key[key]
                rep.conflict(table, key, "แถวใหม่ตัวตนเดียวกัน เนื้อหาต่างกัน", win[1])
                by_key[key] = win
            rep.bump(table, "deduped")
            continue
        by_key[key] = (r, THEIRS)
        rep.bump(table, "added_theirs")

    next_id = max([*used, 0]) + 1
    for row, side in by_key.values():
        row = dict(row)
        old = row[idc]
        if old in used or old is None:
            while next_id in used:
                next_id += 1
            remap[(side, old)] = next_id
            row[idc] = next_id
            rep.bump(table, "remapped")
        used.add(row[idc])
        next_id = max(next_id, (row[idc] or 0) + 1)
        out.append((row, side))
        rep.bump(table, "rows")

    return out, remap


# ---------- ตัวหลัก ----------

def merge_db(base: str | os.PathLike | None,
             ours: str | os.PathLike,
             theirs: str | os.PathLike,
             out_path: str | os.PathLike) -> dict:
    """รวม ours+theirs โดยใช้ base เป็นจุดอ้างอิง แล้วเขียนผลลง out_path."""
    conns = [(OURS, _connect(ours)), (THEIRS, _connect(theirs)), (BASE, _connect(base))]
    by_side = dict(conns)
    two_way = not _tables(by_side[BASE])

    out_file = Path(out_path)
    if out_file.exists():
        out_file.unlink()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(out_file)
    rep = _Report()

    try:
        _build_schema(out, conns)

        names = list(_tables(out))

        def _side_with(name: str) -> sqlite3.Connection:
            """อ่านโครงจากฝั่งที่มีตารางนั้นจริง — ตารางที่เหลืออยู่แค่ใน base ก็ยังต้องรวมถูก."""
            for label in (OURS, THEIRS, BASE):
                if name in _tables(by_side[label]):
                    return by_side[label]
            return out

        specs = {n: spec_for(n, _side_with(n)) for n in names}
        # ตารางที่ถูกอ้างถึงต้องรวมก่อน ไม่งั้นยังไม่รู้ว่า id ปลายทางย้ายไปไหน
        referenced = {t for s in specs.values() for t in s.refs.values()}
        names.sort(key=lambda n: (n not in referenced, n))

        merged: dict[str, list[tuple[dict, str]]] = {}
        remaps: dict[str, dict[tuple[str, Any], Any]] = {}
        cols_of: dict[str, list[str]] = {}

        for name in names:
            spec, cols = specs[name], list(_columns(out, name))
            cols_of[name] = cols
            rows, remap = _merge_table(
                name, spec, cols,
                _read(by_side[BASE], name, cols),
                _read(by_side[OURS], name, cols),
                _read(by_side[THEIRS], name, cols),
                rep,
            )
            merged[name], remaps[name] = rows, remap

        final_ids = {n: {r[specs[n].id_col] for r, _ in merged[n]}
                     for n in names if specs[n].id_col}

        for name in names:
            spec, cols = specs[name], cols_of[name]
            for row, side in merged[name]:
                for col, target in spec.refs.items():
                    val = row.get(col)
                    if val is None:
                        continue
                    new = remaps.get(target, {}).get((side, val), val)
                    if target in final_ids and new not in final_ids[target]:
                        # แถวที่ถูกอ้างถึงหายไปตอนรวม — ตัดสายทิ้งดีกว่าปล่อยให้ชี้ผิดแถว
                        rep.conflict(name, _key_of(row, spec.key), f"{col} ชี้ไปแถวที่ไม่มีแล้ว",
                                     "ล้างค่าเป็นว่าง")
                        new = None
                    row[col] = new

            q = ", ".join(f'"{c}"' for c in cols)
            out.executemany(
                f'INSERT INTO "{name}" ({q}) VALUES ({", ".join("?" * len(cols))})',
                [[row.get(c) for c in cols] for row, _ in merged[name]],
            )

        out.commit()
        out.execute("VACUUM")                   # ไฟล์เล็กและนิ่ง -> diff ใน git ไม่บวมเกินจำเป็น
        out.commit()
    finally:
        out.close()
        for _, c in conns:
            c.close()

    return {"out": str(out_file), "two_way": two_way,
            "tables": rep.tables, "conflicts": rep.conflicts}


def render_text(report: dict) -> str:
    lines: list[str] = []
    if report["two_way"]:
        lines.append("! ไม่มีจุดอ้างอิงร่วม (base) — รวมแบบยูเนียน จะไม่ลบแถวใดๆ ทั้งสิ้น")
        lines.append("")

    head = f'{"ตาราง":22} {"แถว":>6} {"+เรา":>6} {"+เขา":>6} {"แก้":>5} {"ลบ":>4} {"ย้าย id":>8} {"ชน":>4}'
    lines.append(head)
    lines.append("-" * len(head))
    for name in sorted(report["tables"]):
        t = report["tables"][name]
        upd = t.get("updated_ours", 0) + t.get("updated_theirs", 0)
        lines.append(f'{name:22} {t.get("rows", 0):6} {t.get("added_ours", 0):6} '
                     f'{t.get("added_theirs", 0):6} {upd:5} {t.get("deleted", 0):4} '
                     f'{t.get("remapped", 0):8} {t.get("conflicts", 0):4}')

    if report["conflicts"]:
        lines.append("")
        lines.append(f'ต้องดูด้วยตา {len(report["conflicts"])} จุด (รวมให้แล้ว แต่เป็นการตัดสินแทน):')
        for c in report["conflicts"]:
            key = "/".join(str(k) for k in c["key"] if k is not None)
            detail = f'  [{c["detail"]}]' if c["detail"] else ""
            lines.append(f'  {c["table"]}:{key} — {c["kind"]} -> เอา {c["chose"]}{detail}')
    else:
        lines.append("")
        lines.append("ไม่มีจุดที่ต้องตัดสินแทน — ทุกแถวมีคำตอบเดียว")
    return "\n".join(lines)
