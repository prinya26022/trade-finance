"""Technical Score /6 — นับเงื่อนไข ไม่ฟันธง (สเปก TECHNICAL_LAYER.md ข้อ 4).

ทุกข้อเป็น binary หาร 6 เสมอ. แต่ binary อย่างเดียวซ่อนว่า "ผ่าน" นั้นผ่านขาดหรือเฉียดเส้น
(บทเรียน Phase 48) จึงเก็บ `margin` ทุกข้อ: **+ = ผ่านไปไกลจากเส้นเท่าไหร่, − = ตกห่างเท่าไหร่**
ในหน่วยของข้อนั้นเอง และ `borderline` เมื่ออยู่ใกล้เส้นกว่า BORDERLINE ของข้อนั้น

ทำไม borderline เป็นค่าต่อข้อ ไม่ใช่ "10% ของเส้น" แบบเรดาร์ Phase 49: เส้นของที่นี่มีหน่วยต่างกัน
(% ห่างจาก SMA, pp ชนะ VT, จุด RSI) — 10% ของ RSI 75 คือ 7.5 จุด แต่ 10% ของ "ห่าง SMA 0%"
คือศูนย์. ตั้งเป็นตัวเลขตรงๆ ต่อข้อ แล้วให้คนเห็นตัวเลขนั้น ดีกว่าสูตรที่ดูเป็นระบบแต่ไม่มีความหมาย
"""
from dataclasses import asdict, dataclass
from datetime import date

from src.technical import bars as B
from src.technical.indicators import pct_change, rsi_wilder, sma

MAX_SCORE = 6
MIN_WEEKS = 52     # SMA40 + ย้อน 10 แท่ง + เผื่อ = 51 ขั้นต่ำจริง, 52 ให้ T5 มองครบปี
MIN_MONTHS = 13    # 12-1 momentum ต้องการแท่ง m[-13]

SMA_WEEKS = 40
SLOPE_LOOKBACK_WEEKS = 10
SMA_MONTHS = 10
MAX_DRAWDOWN_PCT = -25.0
RSI_PERIOD = 14
RSI_MAX = 75.0

# ระยะที่นับว่า "เฉียดเส้น" — หน่วยตามคอลัมน์ unit ของแต่ละข้อ
BORDERLINE = {
    "T1": 2.0,    # % ห่างจาก SMA40W
    "T2": 1.0,    # % ที่ SMA40W เปลี่ยนใน 10 สัปดาห์
    "T3": 2.0,    # % ห่างจาก SMA10M
    "T4": 2.0,    # pp ชนะ/แพ้ VT
    "T5": 3.0,    # pp จากเส้น −25%
    "T6": 5.0,    # จุด RSI จากเส้น 75
}

TIERS = (  # (คะแนนขั้นต่ำ, tier, ป้าย) — ป้ายไม่มีคำว่าซื้อ/ขาย โดยตั้งใจ
    (5, "trend_up", "แนวโน้มเป็นใจ"),
    (3, "mixed", "สัญญาณปนกัน"),
    (0, "trend_down", "แนวโน้มไม่เป็นใจ"),
)


@dataclass
class Criterion:
    key: str
    label: str
    value: float          # ค่าที่วัดได้ ในหน่วย unit
    threshold: float      # เส้น ในหน่วยเดียวกัน
    unit: str
    passed: bool
    margin: float         # + = ผ่านห่างเส้นเท่านี้, − = ตกห่างเท่านี้
    borderline: bool


def _criterion(key: str, label: str, value: float, threshold: float, unit: str,
               higher_is_pass: bool = True, on_line_passes: bool = False) -> Criterion:
    margin = value - threshold if higher_is_pass else threshold - value
    # ตัดสิน passed จาก margin ตัวเดียวกัน จะได้ไม่มีทางที่ passed กับเครื่องหมาย margin ขัดกันเอง.
    # on_line_passes: เส้นที่เขียนว่า "ไม่เกิน" (T5, T6) นับค่าที่อยู่บนเส้นพอดีว่าผ่าน
    passed = margin >= 0 if on_line_passes else margin > 0
    return Criterion(key, label, round(value, 2), threshold, unit, passed, round(margin, 2),
                     abs(margin) <= BORDERLINE[key])


def _tier(score: int) -> tuple[str, str]:
    for floor, tier, label in TIERS:
        if score >= floor:
            return tier, label
    raise AssertionError("unreachable")


def _unmeasurable(reason: str, **extra) -> dict:
    return {"score": None, "max": MAX_SCORE, "status": "unmeasurable", "tier": "unmeasurable",
            "label": "วัดไม่ได้", "reason": reason, "criteria": [], **extra}


def score_from_bars(week: list[B.Bar], month: list[B.Bar], bench_month: list[B.Bar],
                    benchmark: str = "VT") -> dict:
    """คะแนน /6 จากแท่งที่ **ปิดแล้ว** (เรียงเก่า -> ใหม่).

    ข้อมูลไม่พอ -> score=None พร้อมเหตุผล ไม่ใช่ 0/6: "IPO ไม่ถึงปี" กับ "วัดแล้วแย่ทุกข้อ"
    เป็นคนละคำกล่าว (Phase 39)
    """
    meta = {"last_week": week[-1][0] if week else None,
            "last_month": month[-1][0] if month else None, "benchmark": benchmark}
    if len(week) < MIN_WEEKS:
        return _unmeasurable(f"มีแท่ง Week ที่ปิดแล้ว {len(week)} แท่ง ต้องการ {MIN_WEEKS}", **meta)
    if len(month) < MIN_MONTHS:
        return _unmeasurable(f"มีแท่ง Month ที่ปิดแล้ว {len(month)} แท่ง ต้องการ {MIN_MONTHS}", **meta)

    # momentum ต้องเทียบ "เดือนเดียวกัน" กับ benchmark — จับคู่ด้วยวันสิ้นเดือน ไม่ใช่ตำแหน่ง
    # เพราะถ้า benchmark ขาดไปหนึ่งเดือน การจับตามตำแหน่งจะเทียบผิดเดือนแบบเงียบๆ
    bench = dict(bench_month)
    start_key, end_key = month[-13][0], month[-2][0]
    if start_key not in bench or end_key not in bench:
        return _unmeasurable(f"ไม่มีราคา {benchmark} ของเดือน {start_key} หรือ {end_key}", **meta)

    wc = [c for _, c in week]
    mc = [c for _, c in month]
    sma40 = sma(wc, SMA_WEEKS)
    sma40_before = sma(wc, SMA_WEEKS, back=SLOPE_LOOKBACK_WEEKS)
    sma10m = sma(mc, SMA_MONTHS)
    own_ret = pct_change(mc[-13], mc[-2])
    bench_ret = pct_change(bench[start_key], bench[end_key])
    high52 = max(wc[-52:])
    rsi = rsi_wilder(wc, RSI_PERIOD)
    if None in (own_ret, bench_ret, rsi):
        return _unmeasurable("คำนวณ momentum หรือ RSI ไม่ได้ (ราคาเป็นศูนย์/ติดลบ)", **meta)

    criteria = [
        _criterion("T1", "ปิด Week เหนือเส้นเฉลี่ย 40 สัปดาห์",
                   pct_change(sma40, wc[-1]), 0.0, "% ห่างเส้น"),
        _criterion("T2", "เส้นเฉลี่ย 40 สัปดาห์ยังชันขึ้น (เทียบ 10 สัปดาห์ก่อน)",
                   pct_change(sma40_before, sma40), 0.0, "% เปลี่ยน"),
        _criterion("T3", "ปิด Month เหนือเส้นเฉลี่ย 10 เดือน",
                   pct_change(sma10m, mc[-1]), 0.0, "% ห่างเส้น"),
        _criterion("T4", f"ผลตอบแทน 12-1 เดือน ชนะ {benchmark}",
                   own_ret - bench_ret, 0.0, f"pp เทียบ {benchmark}"),
        _criterion("T5", "ห่างจุดสูงสุด 52 สัปดาห์ไม่เกิน 25%",
                   pct_change(high52, wc[-1]), MAX_DRAWDOWN_PCT, "% จากยอด",
                   on_line_passes=True),
        _criterion("T6", "RSI รายสัปดาห์ยังไม่ร้อนเกิน (≤ 75)",
                   rsi, RSI_MAX, "RSI", higher_is_pass=False, on_line_passes=True),
    ]

    score = sum(c.passed for c in criteria)
    tier, label = _tier(score)
    return {"score": score, "max": MAX_SCORE, "status": "ok", "tier": tier, "label": label,
            "reason": None, "criteria": [asdict(c) for c in criteria],
            "own_return_12_1": round(own_ret, 2), "bench_return_12_1": round(bench_ret, 2),
            **meta}


def evaluate(daily: list[B.Bar], bench_daily: list[B.Bar], asof: date,
             asset_type: str = "stock", benchmark: str = "VT") -> tuple[list[B.Bar], list[B.Bar], dict]:
    """รายวัน -> (แท่ง Week, แท่ง Month, คะแนน). คืนแท่งด้วยเพื่อให้ภาพวาดจากชุดเดียวกับที่คิดคะแนน
    — ถ้าภาพไปรวมแท่งเอง วันไหนที่สองทางไม่ตรงกันจะมีภาพที่ขัดกับตัวเลขข้างๆ มัน"""
    week = B.weekly(daily, asof, B.week_end_for(asset_type))
    month = B.monthly(daily, asof)
    bench_month = B.monthly(bench_daily, asof)
    out = score_from_bars(week, month, bench_month, benchmark)
    out["asof"] = asof.isoformat()
    out["asset_type"] = asset_type
    return week, month, out


def score_from_daily(daily: list[B.Bar], bench_daily: list[B.Bar], asof: date,
                     asset_type: str = "stock", benchmark: str = "VT") -> dict:
    """ทางเข้าหลักเมื่อต้องการแค่คะแนน. asof คือ "วันนี้" ของการรัน (ใส่เองได้ = เทสต์ได้)."""
    return evaluate(daily, bench_daily, asof, asset_type, benchmark)[2]
