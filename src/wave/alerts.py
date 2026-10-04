"""แจ้งเตือนเมื่อแท่ง 4H **ปิด** ผ่านเส้นตาย/เส้นยืนยันของฉากคลื่น — ไม่ต้องเฝ้าจอ.

ทำไมใช้ราคาปิดแท่ง 4H ไม่ใช่ราคาแตะ: ไส้เทียนแทงเส้นแล้วดีดกลับเป็นเรื่องปกติของ BTC และคือสิ่งที่
ทำให้ไม้ของผู้ใช้โดน stop ทั้งที่ทิศถูก. การแจ้งที่เด้งทุกครั้งที่ราคาแตะเส้นจะกลายเป็นเสียงรบกวน

ทำไมเทียบกับเส้นของ "รอบก่อน" ไม่ใช่ของรอบนี้: พอราคาผ่านเส้นตาย รายงานรอบใหม่จะคิดฉากใหม่ไปแล้ว
(ฉากที่ตายหายไป หรือ count เปลี่ยนสถานะ) — ถ้าดูแค่รายงานปัจจุบันจะไม่เคยเห็นช่วงที่ "เพิ่งผ่านเส้น"
จึงเก็บเส้นของรอบก่อนไว้ แล้วตรวจว่าแท่ง 4H ที่ปิดหลังจากนั้นข้ามเส้นไหนบ้าง

รอบแรกบันทึกเส้นเงียบๆ (เหมือนเรดาร์อื่นในโปรเจกต์) — ไม่มี "รอบก่อน" ให้เทียบ
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
    kind: str            # kill | confirm
    level: float
    side: str            # below | above — ฝั่งที่ถือว่า "ผ่านเส้น"
    bar_ts: datetime
    close: float


def levels_of(rep: Report) -> list[dict]:
    out = []
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
    """เส้นของรอบก่อนที่แท่ง 4H ปิดผ่านไปแล้ว นับเฉพาะแท่งที่ปิดหลังรอบก่อน (คอมปิดไว้หลายชั่วโมงก็ไม่พลาด)
    — ต่อเส้นรายงานครั้งเดียว ที่แท่งแรกที่ผ่าน"""
    if not prev:
        return []
    last = datetime.fromisoformat(prev["last_bar"]) if prev.get("last_bar") else None
    new_bars = [c for c in closed_4h if last is None or c.ts > last]
    out = []
    for lv in prev.get("levels", []):
        for c in new_bars:
            if (c.close < lv["level"]) if lv["side"] == "below" else (c.close > lv["level"]):
                out.append(Crossing(lv["key"], lv["title"], lv["kind"], lv["level"], lv["side"], c.ts, c.close))
                break
    return out


def load_state(stem: str, state_dir: Path | None = None) -> dict | None:
    path = (state_dir or STATE_DIR) / f"{stem}_alert_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_state(stem: str, rep: Report, closed_4h: list[Candle], state_dir: Path | None = None) -> None:
    d = state_dir or STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    state = {"last_bar": closed_4h[-1].ts.isoformat() if closed_4h else None, "levels": levels_of(rep)}
    (d / f"{stem}_alert_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def format_alert(symbol: str, hits: list[Crossing], rep: Report) -> str:
    L = []
    for h in hits:
        verb = "หลุด" if h.side == "below" else "ทะลุ"
        what = "ตายแล้ว — count ตามฉากนี้ใช้ไม่ได้" if h.kind == "kill" else "ชัดขึ้น"
        L.append(f"🔔 **{symbol}** แท่ง 4H ปิด {h.bar_ts:%d %b %H:%M} UTC ที่ **{fmt(h.close)}** — "
                 f"{verb} {fmt(h.level)} → **ฉาก {h.key} ({h.title}) {what}**")
    alive = [sc for sc in rep.scenarios if sc.alive]
    if alive:
        L.append("\nฉากที่ยังไม่ตายตอนนี้: " + " · ".join(f"{sc.key} ผิดเมื่อ{sc.kill_text}" for sc in alive))
    if any(h.kind == "kill" for h in hits):
        L.append("_ถ้าเส้นตายของ count ที่มาร์กไว้โดนผ่าน ให้แก้จุดใน data/waves/*.json — ระบบไม่นับใหม่แทน_")
    return "\n".join(L)
