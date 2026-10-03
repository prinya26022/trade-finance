"""รายวัน -> แท่ง Week / Month ที่ **ปิดแล้วเท่านั้น**.

ทำไมไม่ใช้ yfinance interval="1wk"/"1mo" ตรงๆ: แท่งสุดท้ายที่มันคืนมาคือสัปดาห์/เดือนที่ยัง
ไม่จบ โดยไม่บอกอะไรเลย — คะแนนที่คิดจากแท่งนั้นจะขยับไปมาระหว่างสัปดาห์ และ backtest จะได้ใช้
ราคาที่ตอนนั้นยังไม่เกิด. รวมแท่งเองทำให้ "แท่งนี้ปิดหรือยัง" เป็นกฎที่เขียนเป็นโค้ดและเทสต์ได้

แท่งแทนด้วย (วันสิ้นงวด ISO, ราคาปิด) เรียงเก่า -> ใหม่. "วันสิ้นงวด" คือวันตามปฏิทิน
(ศุกร์/อาทิตย์/วันสุดท้ายของเดือน) ไม่ใช่วันซื้อขายจริงวันสุดท้าย — สัปดาห์ที่ศุกร์เป็นวันหยุด
ก็ยังปิดที่ศุกร์ ราคาปิดคือราคาของวันซื้อขายจริงวันสุดท้ายในงวดนั้น
"""
from calendar import monthrange
from datetime import date, timedelta

Bar = tuple[str, float]

FRIDAY = 4   # หุ้นสหรัฐ: สัปดาห์จบวันศุกร์
SUNDAY = 6   # crypto: เทรด 7 วัน สัปดาห์จบวันอาทิตย์ (UTC)


def week_end_for(asset_type: str) -> int:
    return SUNDAY if asset_type == "crypto" else FRIDAY


def _week_end(d: date, end_weekday: int) -> date:
    return d + timedelta(days=(end_weekday - d.weekday()) % 7)


def _month_end(d: date) -> date:
    return d.replace(day=monthrange(d.year, d.month)[1])


def _resample(daily: list[Bar], period_end, asof: date) -> list[Bar]:
    closes: dict[date, float] = {}
    for iso, close in daily:              # daily เรียงเก่า -> ใหม่ ตัวหลังทับตัวก่อน = ราคาปิดวันสุดท้าย
        closes[period_end(date.fromisoformat(iso))] = close
    # ปิดแล้ว = วันสิ้นงวดผ่านไปแล้วจริง (< asof ไม่ใช่ <=): รันวันศุกร์ระหว่างตลาดเปิด
    # แท่งของศุกร์นั้นยังไม่จบ. ยอมช้าไปหนึ่งวันดีกว่าใช้ราคาที่ยังไม่ปิด
    return [(end.isoformat(), c) for end, c in sorted(closes.items()) if end < asof]


def weekly(daily: list[Bar], asof: date, end_weekday: int = FRIDAY) -> list[Bar]:
    return _resample(daily, lambda d: _week_end(d, end_weekday), asof)


def monthly(daily: list[Bar], asof: date) -> list[Bar]:
    return _resample(daily, _month_end, asof)
