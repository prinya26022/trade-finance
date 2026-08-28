"""อัตราแลกเปลี่ยนสำหรับ ADR ต่างชาติ (Phase 45).

ทำไมต้องมี: ADR ต่างชาติยื่นงบสกุลบ้านเกิดแต่ซื้อขายเป็น USD (ASML งบ EUR, TSM งบ TWD) ทำให้
EV = market_cap + net_debt เป็นการบวกคนละสกุล — Phase 33 จึงปฏิเสธทั้งชุด ซึ่งถูกต้องในตอนนั้น
(ตัวเลขที่ผิดแบบดูน่าเชื่อแย่กว่าไม่มีตัวเลข) แต่ผลข้างเคียงคือ **ธุรกิจที่คะแนนพื้นฐานสูงสุด
สองอันดับแรกของทั้ง watchlist ไม่มีคำตอบด้านราคาเลย** ด้วยเหตุผลที่ไม่เกี่ยวกับตัวธุรกิจ

สิ่งที่ต้องแปลงมีตัวเดียว: **market cap** ให้ไปอยู่ในสกุลของงบ แล้ว reverse-DCF ทั้งเส้นทำงาน
ในสกุลเดียวกันหมด (net debt / FCF / รายได้ เป็นสกุลงบอยู่แล้ว) ส่วนผลลัพธ์ที่ออกมา —
implied growth, gap, ส่วนลด, ข้อเรียกร้องต่อขนาดบริษัท — ไม่มีหน่วยเงินอยู่แล้วทั้งนั้น

**อัตราการเติบโตไม่ได้รับผลกระทบจาก FX เลย** — เรตหารกันหายไปใน CAGR ของ series ที่เป็นสกุล
เดียวกันทั้งชุด ที่แปลงคือ *ระดับ* ของ EV/FCF อย่างเดียว จึงใช้ spot rate ได้อย่างมีเหตุผล
(กำลังตีมูลค่าสิทธิ์ ณ วันนี้ ในสกุลที่กระแสเงินสดนั้นเกิดจริง)

เรตที่ใช้ต้องถูก **บันทึกลง facts ณ วันที่วิเคราะห์** (ดู StockFundamentals.to_facts) ไม่งั้น
การคำนวณย้อนหลังจะหยิบเรตวันนี้ไปใช้กับแถวปีที่แล้วเงียบๆ — บั๊กตระกูลเดียวกับที่ Phase 32
(anchor สลับฐานเงียบๆ) และ Phase 36 (หน้าต่างข้อมูลเปลี่ยนความหมาย) เจอมาแล้ว
"""
import json
import time
from pathlib import Path

import yfinance as yf

_CACHE_PATH = Path(__file__).parents[3] / "data" / "fx_cache.json"
_CACHE_TTL = 24 * 3600   # เท่ากับ risk-free rate: ค่าตลาดรวมรายวัน ไม่ใช่ค่าต่อ ticker


def _load() -> dict:
    if not _CACHE_PATH.exists() or (time.time() - _CACHE_PATH.stat().st_mtime) >= _CACHE_TTL:
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}   # cache เสีย -> ดึงใหม่


def _save(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        _CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass   # เขียน cache ไม่ได้ไม่ควรทำให้การวิเคราะห์ล้ม


def get_fx_rate(from_ccy: str | None, to_ccy: str | None) -> float | None:
    """1 หน่วย from_ccy = กี่หน่วย to_ccy — **None ถ้าดึงไม่ได้ ไม่มีการเดา**.

    คืน None แล้วให้ฝั่งเรียกกลับไปปฏิเสธเหมือนเดิม (พฤติกรรมก่อน Phase 45) ตั้งใจ:
    การเดาเรตแล้วให้คะแนนขาราคาออกมาคือการสร้างตัวเลขผิดที่ดูน่าเชื่อ ซึ่งเป็นสิ่งเดียวกับที่
    Phase 33 ปฏิเสธไปแล้ว — ต่างกันแค่ตอนนี้ผิดที่เรตแทนที่จะผิดที่สกุล
    """
    if not from_ccy or not to_ccy:
        return None
    if from_ccy == to_ccy:
        return 1.0

    pair = f"{from_ccy}{to_ccy}=X"
    cache = _load()
    if pair in cache:
        return cache[pair]

    try:
        hist = yf.Ticker(pair).history(period="5d")
        rate = float(hist["Close"].iloc[-1])
    except Exception:
        return None
    if not rate or rate <= 0:
        return None

    cache[pair] = rate
    _save(cache)
    return rate


if __name__ == "__main__":
    # python -m src.providers.stock.fx
    for a, b in (("USD", "EUR"), ("USD", "TWD"), ("USD", "USD")):
        print(f"1 {a} = {get_fx_rate(a, b)} {b}")
