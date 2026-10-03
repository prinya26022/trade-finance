"""เทรนด์หลาย TF (M/W/D/4H) + divergence ของ RSI/MACD — บริบทให้ count ใน TF เล็ก.

**เส้นหลักของ W/M ใช้ตัวเดียวกับ Phase 53** (SMA40W, SMA10M) — ถ้าใช้เส้นต่างกัน วันหนึ่งช่อง
technical จะบอกว่า W ขึ้น ขณะที่ภาพคลื่นบอกว่า W ลง จากราคาเดียวกัน แล้วคนจะเลิกเชื่อทั้งสอง.
D/4H ใช้ EMA50 + EMA200 ตาม indicator ของผู้ใช้

divergence เขียนตามสคริปต์ RSI ของ TradingView ที่ผู้ใช้ใช้ตัวอักษรต่อตัวอักษร: pivot ของ
indicator ซ้าย 5 ขวา 5, เทียบกับ pivot ก่อนหน้าที่ห่าง 5–60 แท่ง, ราคาใช้ high/low ของแท่ง pivot.
ผลคือ **ยืนยันช้า 5 แท่งเสมอ** (Day = 5 วัน) — รายงานวันที่ยืนยันด้วย ไม่ใช่แค่วันที่ยอด
MACD ใช้ EMA12 − EMA26 กับ signal = **SMA 9** ตามสคริปต์ ChrisMoody ที่ผู้ใช้ใช้ (ไม่ใช่ EMA 9)
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from calendar import monthrange

from src.technical.indicators import sma
from src.wave.candles import Candle, resample_4h
from src.wave.pivots import zigzag

PIVOT_LEFT = PIVOT_RIGHT = 5
RANGE_MIN, RANGE_MAX = 5, 60
SLOPE_BARS = 10


@dataclass
class Check:
    text: str
    up: bool | None      # True = ฝั่งขาขึ้น, False = ฝั่งขาลง, None = วัดไม่ได้


@dataclass
class TrendRead:
    tf: str
    state: str           # "up" | "down" | "mixed" | "unknown"
    close: float | None
    lines: dict[str, float] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)


@dataclass
class Divergence:
    tf: str
    indicator: str       # "RSI" | "MACD"
    kind: str            # "bear" | "bull"
    price_prev: float
    price_now: float
    ind_prev: float
    ind_now: float
    pivot_ts: datetime
    confirmed_ts: datetime


# ---------- แท่งปิดแล้วของแต่ละ TF ----------

def _group(daily: list[Candle], key, end_of, asof: datetime) -> list[Candle]:
    g: dict = {}
    for c in daily:
        g.setdefault(key(c.ts), []).append(c)
    out = []
    for k, cs in sorted(g.items()):
        if end_of(cs[0].ts) < asof:              # ปิดแล้วเท่านั้น (กฎเดียวกับ Phase 53)
            out.append(Candle(cs[0].ts, cs[0].open, max(c.high for c in cs),
                              min(c.low for c in cs), cs[-1].close))
    return out


def timeframes(daily: list[Candle], hourly: list[Candle], asof: datetime,
               crypto: bool = True) -> dict[str, list[Candle]]:
    week_end = 6 if crypto else 4
    wk = lambda t: (t + timedelta(days=(week_end - t.weekday()) % 7)).date()
    return {
        "M": _group(daily, lambda t: (t.year, t.month),
                    lambda t: datetime(t.year, t.month, monthrange(t.year, t.month)[1]) + timedelta(days=1), asof),
        "W": _group(daily, wk, lambda t: datetime.combine(wk(t), datetime.min.time()) + timedelta(days=1), asof),
        "D": [c for c in daily if c.ts + timedelta(days=1) <= asof],
        "4H": resample_4h(hourly, asof),
    }


# ---------- indicator ----------

def ema(values: list[float], n: int) -> list[float | None]:
    """Pine ta.ema: ค่าแรก = SMA ของ n ค่าแรก, alpha = 2/(n+1).

    ผลของค่าเริ่มต้นจางเป็น (1−alpha)^k — EMA 200 จางช้ามาก (หลัง 160 แท่งยังเหลือ ~20%) ถ้า
    ข้อมูลสั้นเส้นจะไม่ตรงกับ TradingView ที่มีประวัติยาวกว่า จึงดึง 1H ย้อน 180 วัน / 1D ย้อน 10 ปี"""
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    cur = sum(values[:n]) / n
    out[n - 1] = cur
    a = 2 / (n + 1)
    for i in range(n, len(values)):
        cur = a * values[i] + (1 - a) * cur
        out[i] = cur
    return out


def rsi_series(values: list[float], n: int = 14) -> list[float | None]:
    """RSI แบบ Wilder ทุกแท่ง (ตรงกับ ta.rsi) — ค่าแท่งสุดท้ายเท่ากับ technical.rsi_wilder"""
    out: list[float | None] = [None] * len(values)
    if len(values) < n + 1:
        return out
    d = [b - a for a, b in zip(values, values[1:])]
    g = sum(max(x, 0) for x in d[:n]) / n
    l = sum(max(-x, 0) for x in d[:n]) / n

    def val(g, l):
        return 100.0 if l == 0 else 0.0 if g == 0 else 100 - 100 / (1 + g / l)
    out[n] = val(g, l)
    for i in range(n, len(d)):
        g = (g * (n - 1) + max(d[i], 0)) / n
        l = (l * (n - 1) + max(-d[i], 0)) / n
        out[i + 1] = val(g, l)
    return out


def macd_series(values: list[float]) -> tuple[list[float | None], list[float | None]]:
    """(MACD, signal) — signal = SMA 9 ตามสคริปต์ของผู้ใช้"""
    f, s = ema(values, 12), ema(values, 26)
    m = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    sig: list[float | None] = [None] * len(m)
    for i in range(len(m)):
        win = m[max(0, i - 8):i + 1]
        if len(win) == 9 and None not in win:
            sig[i] = sum(win) / 9
    return m, sig


def _pivots(series: list[float | None], high: bool) -> list[int]:
    out = []
    for i in range(PIVOT_LEFT, len(series) - PIVOT_RIGHT):
        win = series[i - PIVOT_LEFT:i + PIVOT_RIGHT + 1]
        if None in win:
            continue
        v = series[i]
        # ta.pivothigh: ค่ากลางต้องมากกว่าทั้งสองฝั่ง (เท่ากันทางซ้ายไม่นับ)
        if high and all(v > x for x in win[:PIVOT_LEFT]) and all(v >= x for x in win[PIVOT_LEFT + 1:]):
            out.append(i)
        if not high and all(v < x for x in win[:PIVOT_LEFT]) and all(v <= x for x in win[PIVOT_LEFT + 1:]):
            out.append(i)
    return out


def divergences(tf: str, candles: list[Candle], indicator: str = "RSI") -> list[Divergence]:
    closes = [c.close for c in candles]
    series = rsi_series(closes) if indicator == "RSI" else macd_series(closes)[0]
    out = []
    for high in (True, False):
        piv = _pivots(series, high)
        for prev, cur in zip(piv, piv[1:]):
            if not RANGE_MIN <= cur - prev <= RANGE_MAX:
                continue
            if high:
                p0, p1 = candles[prev].high, candles[cur].high
                hit = p1 > p0 and series[cur] < series[prev]        # ราคา HH แต่ indicator LH
            else:
                p0, p1 = candles[prev].low, candles[cur].low
                hit = p1 < p0 and series[cur] > series[prev]        # ราคา LL แต่ indicator HL
            if hit:
                out.append(Divergence(tf, indicator, "bear" if high else "bull", p0, p1,
                                      series[prev], series[cur], candles[cur].ts,
                                      candles[cur + PIVOT_RIGHT].ts))
    return sorted(out, key=lambda d: d.confirmed_ts)


# ---------- เทรนด์ต่อ TF ----------

def _structure(candles: list[Candle]) -> Check:
    """ยอด/ก้นสองชุดล่าสุด — ความละเอียดปรับตามความผันผวนของ TF นั้นเอง (3× ช่วงแท่งเฉลี่ย)
    เพื่อให้ใช้ได้ทั้ง BTC และหุ้นโดยไม่ต้องตั้งเลขต่อสินทรัพย์"""
    recent = candles[-120:]
    if len(recent) < 30:
        return Check("โครงสร้างยอด/ก้น: แท่งไม่พอ", None)
    rng = sorted((c.high - c.low) / c.close for c in recent[-50:])[len(recent[-50:]) // 2]
    z = zigzag(recent, max(3 * rng, 0.005))
    hs = [p.price for p in z if p.kind == "H"][-2:]
    ls = [p.price for p in z if p.kind == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return Check("โครงสร้างยอด/ก้น: ยังไม่มีสวิงพอ", None)
    hh, hl = hs[1] > hs[0], ls[1] > ls[0]
    name = ("ยอดสูงขึ้น" if hh else "ยอดต่ำลง") + " · " + ("ก้นสูงขึ้น" if hl else "ก้นต่ำลง")
    return Check(f"โครงสร้าง: {name}", True if hh and hl else False if not hh and not hl else None)


def read(tf: str, candles: list[Candle]) -> TrendRead:
    closes = [c.close for c in candles]
    if not closes:
        return TrendRead(tf, "unknown", None)
    last = closes[-1]
    r = TrendRead(tf, "unknown", last)
    if tf in ("M", "W"):
        n = 10 if tf == "M" else 40
        name = f"SMA{n}{tf}"
        now, before = sma(closes, n), sma(closes, n, back=SLOPE_BARS)
        if now is not None:
            r.lines[name] = now
            r.checks.append(Check(f"ราคาปิด{'เหนือ' if last > now else 'ใต้'} {name}", last > now))
        if now is not None and before is not None:
            r.checks.append(Check(f"{name} ชี้{'ขึ้น' if now > before else 'ลง'} ({(now / before - 1) * 100:+.1f}% ใน {SLOPE_BARS} แท่ง)",
                                  now > before))
    else:
        e50, e200 = ema(closes, 50), ema(closes, 200)
        if e50[-1] is not None:
            r.lines["EMA50"] = e50[-1]
            r.checks.append(Check(f"ราคาปิด{'เหนือ' if last > e50[-1] else 'ใต้'} EMA50", last > e50[-1]))
            b = e50[-1 - SLOPE_BARS] if len(e50) > SLOPE_BARS else None
            if b is not None:
                r.checks.append(Check(f"EMA50 ชี้{'ขึ้น' if e50[-1] > b else 'ลง'} ({(e50[-1] / b - 1) * 100:+.1f}% ใน {SLOPE_BARS} แท่ง)",
                                      e50[-1] > b))
        if e200[-1] is not None:
            r.lines["EMA200"] = e200[-1]
            r.checks.append(Check(f"ราคาปิด{'เหนือ' if last > e200[-1] else 'ใต้'} EMA200", last > e200[-1]))
    r.checks.append(_structure(candles))
    votes = [c.up for c in r.checks if c.up is not None]
    if votes:
        r.state = "up" if all(votes) else "down" if not any(votes) else "mixed"
    return r


def ladder(tfs: dict[str, list[Candle]]) -> list[TrendRead]:
    return [read(tf, tfs[tf]) for tf in ("M", "W", "D", "4H")]
