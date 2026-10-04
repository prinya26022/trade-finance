"""เติม stop/TP "ตัวแรก ณ ตอนกดเข้า" ให้ไม้ — OKX ไม่ส่งมากับประวัติ position ที่ปิดแล้ว.

ลำดับความน่าเชื่อ:
1. **แนบมากับคำสั่งเปิดไม้** (attachAlgoOrds) — นี่คือสิ่งที่ตั้งใจไว้ตอนกดเข้าจริงๆ
2. **คำสั่ง stop ที่ตั้งแยกหลังเข้าไม้** ตัวแรกที่ตั้งก่อนไม้ปิด — ใกล้เคียง แต่อาจตั้งช้ากว่าตอนเข้า
3. ไม่เจอ = ว่าง (ไม่เดา)

ทำไมต้องเป็น "ตัวแรก" ไม่ใช่ตัวล่าสุด: R:R และความเสี่ยงต้องวัดจากแผนตอนเข้า. เจอจริงกับไม้ที่เปิดอยู่:
stop ตอนกดเข้าคือ 82,200 แต่ระบบเห็นครั้งแรกที่ 82,900 เพราะผู้ใช้เลื่อนขึ้นไปแล้ว — ถ้าใช้ตัวหลัง
ความเสี่ยงตอนเข้าจะดูน้อยกว่าความจริงเกือบครึ่ง
"""
from datetime import datetime, timedelta

ENTRY_TOL = timedelta(minutes=10)      # เวลาจับคู่คำสั่ง กับ เวลาเปิด position ห่างกันได้เท่านี้
ALGO_EARLY = timedelta(minutes=10)     # คำสั่ง stop ที่ตั้งก่อน position เปิดเล็กน้อย (ตั้งรอไว้) ยังนับ


def _at(x) -> datetime | None:
    return datetime.fromisoformat(x) if isinstance(x, str) else x


def match(trade: dict, entry_orders: list[dict], algos: list[dict]) -> dict | None:
    """{"sl", "tp", "source"} หรือ None"""
    opened, closed = _at(trade.get("opened_at")), _at(trade.get("closed_at"))
    side = trade.get("side")
    if not opened:
        return None
    near = [o for o in entry_orders if o["side"] == side and o["ts"] and abs(o["ts"] - opened) <= ENTRY_TOL]
    if near:
        o = min(near, key=lambda o: abs(o["ts"] - opened))
        return {"sl": o["sl"], "tp": o["tp"], "source": "entry"}
    end = closed or datetime.max
    later = sorted((a for a in algos if a["side"] == side and a["ts"] and opened - ALGO_EARLY <= a["ts"] <= end),
                   key=lambda a: a["ts"])
    if later:
        first = later[0]
        tp = first["tp"] or next((a["tp"] for a in later if a["tp"]), None)
        return {"sl": first["sl"], "tp": tp, "source": "algo"}
    return None
