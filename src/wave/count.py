"""โหลดไฟล์ count (data/waves/*.json) -> ดึงแท่ง -> รายงาน (พร้อมระดับใหญ่ถ้ามี).

ไฟล์ count เป็น JSON ที่ commit ได้ — ประวัติ git ของไฟล์นี้คือประวัติว่าเคยนับยังไง และเปลี่ยนใจ
ตอนไหน ซึ่งเป็นสิ่งที่ปกติหายไปพร้อมเส้นที่ลบทิ้งบน TradingView
"""
import json
from datetime import datetime
from pathlib import Path

from src.wave.analysis import Report, analyze, fmt, resolve
from src.wave.candles import Candle, fetch


def _marks(raw: list[list[str]]) -> list[tuple[str, datetime]]:
    return [(label, datetime.fromisoformat(at)) for label, at in raw]


def build(spec: dict, fetcher=fetch, now: datetime | None = None) -> Report:
    """fetcher(symbol, interval, period) -> list[Candle] | None — ใส่ตัวปลอมได้ = เทสต์ได้"""
    candles = fetcher(spec["symbol"], spec.get("interval", "1h"), spec.get("period", "60d"))
    if candles is None:
        raise RuntimeError(f"ดึงราคา {spec['symbol']} ไม่ได้")
    pivots = resolve(candles, _marks(spec["marks"]), spec["direction"], spec.get("snap_hours", 12))
    rep = analyze(spec["name"], spec["symbol"], spec["direction"], pivots, candles,
                  spec.get("wave4"), now)

    parent = spec.get("parent")
    if parent:
        pc = fetcher(spec["symbol"], parent.get("interval", "1d"), parent.get("period", "1y"))
        if pc is not None:
            pp = resolve(pc, _marks(parent["marks"]), spec["direction"], parent.get("snap_hours", 72))
            rep.parent = analyze(parent["name"], spec["symbol"], spec["direction"], pp, pc)
            rep.parent_note = _parent_note(rep, rep.parent)
    return rep


def _parent_note(child: Report, parent: Report) -> str:
    """ระดับเล็กจบ = ระดับใหญ่ขยับหนึ่งขั้น — เขียนออกมาให้เห็นว่าฉาก B ของขาว แปลว่าอะไรกับเหลือง"""
    if not parent.valid:
        return f"count {parent.name} ผิดกฎเหล็ก — ดูรายละเอียดด้านล่าง"
    if len(parent.pivots) != 5 or not child.sub:
        return ""
    s = 1 if parent.direction == "up" else -1
    top, start = child.sub["s1"], parent.pivots[0].price
    whole = abs(top - start)
    levels = " / ".join(fmt(top - s * r * whole) for r in (0.382, 0.5, 0.618))
    return (f"ถ้าฉาก B ถูก (ขาวจบ) = คลื่น 5 ของ{parent.name}จบด้วย → ทั้งขาจาก {fmt(start)} "
            f"ครบ 5 คลื่น · เป้าปรับฐาน 38.2 / 50 / 61.8% = {levels}")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
