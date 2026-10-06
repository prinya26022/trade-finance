"""แจ้งเตือนเมื่อแท่ง 4H **ปิด** ผ่านเส้นตาย/เส้นยืนยันของฉากคลื่น — ไม่ต้องเฝ้าจอ.

ทำไมใช้ราคาปิดแท่ง 4H ไม่ใช่ราคาแตะ: ไส้เทียนแทงเส้นแล้วดีดกลับเป็นเรื่องปกติของ BTC และคือสิ่งที่
ทำให้ไม้ของผู้ใช้โดน stop ทั้งที่ทิศถูก. การแจ้งที่เด้งทุกครั้งที่ราคาแตะเส้นจะกลายเป็นเสียงรบกวน

ทำไมเทียบกับเส้นของ "รอบก่อน" ไม่ใช่ของรอบนี้: พอราคาผ่านเส้นตาย รายงานรอบใหม่จะคิดฉากใหม่ไปแล้ว
(ฉากที่ตายหายไป หรือ count เปลี่ยนสถานะ) — ถ้าดูแค่รายงานปัจจุบันจะไม่เคยเห็นช่วงที่ "เพิ่งผ่านเส้น"
จึงเก็บเส้นของรอบก่อนไว้ แล้วตรวจว่าแท่ง 4H ที่ปิดหลังจากนั้นข้ามเส้นไหนบ้าง

รอบแรกบันทึกเส้นเงียบๆ (เหมือนเรดาร์อื่นในโปรเจกต์) — ไม่มี "รอบก่อน" ให้เทียบ

เส้นที่ผู้ใช้ตั้งเอง ("watch" ในไฟล์ count) เช่น "แท่ง 4H ปิดใต้ 116.4 = ขา A เริ่ม" — เส้นที่ไม่ใช่
เส้นตาย/เส้นยืนยันของฉากไหน แต่เป็นจุดที่ผู้ใช้รอเพื่อตัดสินใจ (Phase 54: SOL รอยืนยันขา A)

แจ้งเฉพาะตอน "ข้าม" เส้น: แท่งก่อนหน้ายังอยู่อีกฝั่ง แล้วแท่งนี้ปิดผ่าน. เวอร์ชันแรกแจ้งทุกแท่งที่อยู่
ฝั่งที่ผ่านแล้ว — ไม่เป็นปัญหากับเส้นตาย (ฉากตายแล้วหายจากรายการเอง) แต่เส้นยืนยันและเส้น watch
ไม่หาย ถ้าราคายืนอยู่ฝั่งนั้นต่อจะเด้งซ้ำทุก 4 ชม.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.wave.analysis import Report, fmt
from src.wave.candles import Candle

STATE_DIR = Path(__file__).parents[2] / "data" / "waves" / "snapshots"     # gitignored


@dataclass
class Crossing:
    key: str
    title: str
    kind: str            # kill | confirm | watch
    level: float
    side: str            # below | above — ฝั่งที่ถือว่า "ผ่านเส้น"
    bar_ts: datetime
    close: float


def watch_levels(spec: dict | None) -> list[dict]:
    """เส้นที่ผู้ใช้ตั้งเองในไฟล์ count: "watch": [{"level": 116.4, "side": "below", "text": "ขา A เริ่ม"}]"""
    out = []
    for w in (spec or {}).get("watch", []):
        if w.get("side") not in ("above", "below") or w.get("level") is None:
            raise ValueError(f"watch ต้องมี level และ side เป็น above/below: {w}")
        out.append({"key": "watch", "title": w.get("text", ""), "kind": "watch", "level": float(w["level"]),
                    "side": w["side"]})
    return out


def levels_of(rep: Report, spec: dict | None = None) -> list[dict]:
    out = watch_levels(spec)
    for sc in rep.scenarios:
        if not sc.alive:
            continue
        if sc.kill_level is not None and sc.kill_side:
            out.append({"key": sc.key, "title": sc.title, "kind": "kill", "level": sc.kill_level, "side": sc.kill_side})
        if sc.confirm_level is not None and sc.confirm_side:
            out.append({"key": sc.key, "title": sc.title, "kind": "confirm", "level": sc.confirm_level,
                        "side": sc.confirm_side})
    return out


def crossings(prev: dict | None, closed_4h: list[Candle]) -> list[Crossing]:
    """เส้นของรอบก่อนที่แท่ง 4H ปิด "ข้าม" ไป นับเฉพาะแท่งที่ปิดหลังรอบก่อน (คอมปิดไว้หลายชั่วโมงก็ไม่พลาด)
    — ต่อเส้นรายงานครั้งเดียว ที่แท่งแรกที่ข้าม. ราคาปิดก่อนหน้าเอาจาก state (last_close); state เก่าที่ไม่มี
    ถือว่าแท่งก่อนหน้ายังไม่ผ่าน (พฤติกรรมเดิม)"""
    if not prev:
        return []
    last = datetime.fromisoformat(prev["last_bar"]) if prev.get("last_bar") else None
    new_bars = [c for c in closed_4h if last is None or c.ts > last]
    out = []
    for lv in prev.get("levels", []):
        beyond = (lambda x: x < lv["level"]) if lv["side"] == "below" else (lambda x: x > lv["level"])
        before = prev.get("last_close")
        for c in new_bars:
            if beyond(c.close) and not (before is not None and beyond(before)):
                out.append(Crossing(lv["key"], lv["title"], lv["kind"], lv["level"], lv["side"], c.ts, c.close))
                break
            before = c.close
    return out


def load_state(stem: str, state_dir: Path | None = None) -> dict | None:
    path = (state_dir or STATE_DIR) / f"{stem}_alert_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_state(stem: str, rep: Report, closed_4h: list[Candle], state_dir: Path | None = None,
               spec: dict | None = None) -> None:
    d = state_dir or STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    state = {"last_bar": closed_4h[-1].ts.isoformat() if closed_4h else None,
             "last_close": closed_4h[-1].close if closed_4h else None, "levels": levels_of(rep, spec)}
    (d / f"{stem}_alert_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def format_alert(symbol: str, hits: list[Crossing], rep: Report) -> str:
    L = []
    for h in hits:
        verb = "หลุด" if h.side == "below" else "ทะลุ"
        head = f"🔔 **{symbol}** แท่ง 4H ปิด {h.bar_ts:%d %b %H:%M} UTC ที่ **{fmt(h.close)}** — {verb} {fmt(h.level)}"
        if h.kind == "watch":
            L.append(f"{head} → **{h.title or 'เส้นที่ตั้งไว้'}**")
            continue
        what = "ตายแล้ว — count ตามฉากนี้ใช้ไม่ได้" if h.kind == "kill" else "ชัดขึ้น"
        L.append(f"{head} → **ฉาก {h.key} ({h.title}) {what}**")
    alive = [sc for sc in rep.scenarios if sc.alive]
    if alive:
        L.append("\nฉากที่ยังไม่ตายตอนนี้: " + " · ".join(f"{sc.key} ผิดเมื่อ{sc.kill_text}" for sc in alive))
    if any(h.kind == "kill" for h in hits):
        L.append("_ถ้าเส้นตายของ count ที่มาร์กไว้โดนผ่าน ให้แก้จุดใน data/waves/*.json — ระบบไม่นับใหม่แทน_")
    return "\n".join(L)
