"""หาจุดกลับตัว: snap (จากที่ผู้ใช้มาร์ก) และ zigzag (นับขาย่อยโดยไม่ต้องมีคนมาร์ก)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.wave.candles import Candle


@dataclass(frozen=True)
class Pivot:
    label: str
    ts: datetime
    price: float
    kind: str          # "H" ยอด | "L" ก้น


def snap(candles: list[Candle], label: str, at: datetime, kind: str, window_h: float) -> Pivot | None:
    """ยอดสูงสุด/ก้นต่ำสุดจริงในช่วง at ± window_h ชั่วโมง.

    ทำไมไม่รับราคาจากผู้ใช้ตรงๆ: ตัวเลขที่อ่านจากจอคลาดได้หลายร้อยดอลลาร์ และกฎเหล็กบางข้อ
    ตัดสินกันที่ระยะแค่นั้น (เช่น ก้นคลื่น 4 ห่างยอดคลื่น 1 แค่ 650) — ให้ผู้ใช้บอกแค่ "ประมาณไหน"
    แล้วให้แท่งราคาบอกว่า "เท่าไหร่"
    """
    lo, hi = at - timedelta(hours=window_h), at + timedelta(hours=window_h)
    near = [c for c in candles if lo <= c.ts <= hi]
    if not near:
        return None
    c = max(near, key=lambda c: c.high) if kind == "H" else min(near, key=lambda c: c.low)
    return Pivot(label, c.ts, c.high if kind == "H" else c.low, kind)


def zigzag(candles: list[Candle], pct: float) -> list[Pivot]:
    """จุดกลับตัวที่ราคาย้อนเกิน pct (0.01 = 1%) — เฉพาะจุดที่ยืนยันแล้ว (มีการย้อนเกินเกณฑ์ตามมา).

    แท่งเดียวเป็นได้แค่ยอดหรือก้นอย่างเดียว: ใช้ high ต่อเส้นขึ้น/low ต่อเส้นลง ไม่บันทึกทั้งคู่ใน
    แท่งเดียว (เวอร์ชันแรกที่ลองตอนสำรวจข้อมูลพลาดตรงนี้ ได้ยอดและก้นซ้อนกันในชั่วโมงเดียว)
    """
    if not candles:
        return []
    out: list[Pivot] = []
    direction = None
    hi_i = lo_i = 0
    for i, c in enumerate(candles):
        if direction is None:
            if c.high > candles[hi_i].high:
                hi_i = i
            if c.low < candles[lo_i].low:
                lo_i = i
            if lo_i < hi_i and candles[hi_i].high >= candles[lo_i].low * (1 + pct):
                out.append(Pivot("", candles[lo_i].ts, candles[lo_i].low, "L"))
                direction = "up"
            elif hi_i < lo_i and candles[lo_i].low <= candles[hi_i].high * (1 - pct):
                out.append(Pivot("", candles[hi_i].ts, candles[hi_i].high, "H"))
                direction = "down"
        elif direction == "up":
            if c.high >= candles[hi_i].high:
                hi_i = i
            elif c.low <= candles[hi_i].high * (1 - pct):
                out.append(Pivot("", candles[hi_i].ts, candles[hi_i].high, "H"))
                direction, lo_i = "down", i
        else:
            if c.low <= candles[lo_i].low:
                lo_i = i
            elif c.high >= candles[lo_i].low * (1 + pct):
                out.append(Pivot("", candles[lo_i].ts, candles[lo_i].low, "L"))
                direction, hi_i = "up", i
    return out
