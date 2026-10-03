"""แท่ง OHLC + ดึงจาก yfinance (ที่เดียวในแพ็กเกจที่แตะเน็ต) + รวม 1H -> 4H.

เวลาเป็น UTC แบบ naive ทั้งหมด — แท่ง 4H ของ crypto บน TradingView ตัดที่ 00/04/08/12/16/20 UTC
เราตัดแบบเดียวกันเพื่อให้แท่งตรงกับจอที่ผู้ใช้ดูอยู่
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    ts: datetime      # เวลาเปิดแท่ง (UTC)
    open: float
    high: float
    low: float
    close: float


def resample_4h(hourly: list[Candle], now: datetime | None = None) -> list[Candle]:
    """1H -> 4H; ตัดแท่ง 4H ที่ยังไม่ปิดทิ้งเมื่อให้ now (ไว้คิด RSI ตอนแท่งปิดแล้ว)."""
    groups: dict[datetime, list[Candle]] = {}
    for c in hourly:
        groups.setdefault(c.ts.replace(hour=c.ts.hour - c.ts.hour % 4, minute=0, second=0), []).append(c)
    out = []
    for start, cs in sorted(groups.items()):
        out.append(Candle(start, cs[0].open, max(c.high for c in cs), min(c.low for c in cs), cs[-1].close))
    if now is not None:
        out = [c for c in out if (now - c.ts).total_seconds() >= 4 * 3600]
    return out


def fetch(symbol: str, interval: str = "1h", period: str = "60d") -> list[Candle] | None:
    """None เมื่อดึงไม่ได้ — ไม่คืน list ว่างที่หน้าตาเหมือน "ไม่มีข้อมูล"."""
    import yfinance as yf

    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    out = []
    for ts, r in df.iterrows():
        vals = (float(r.Open), float(r.High), float(r.Low), float(r.Close))
        if all(v == v and v > 0 for v in vals):
            t = ts.tz_convert(timezone.utc).to_pydatetime().replace(tzinfo=None)
            out.append(Candle(t, *vals))
    return out or None
