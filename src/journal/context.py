"""บริบทกราฟ ณ เวลาที่เข้าไม้ — คำนวณจากแท่งที่ปิดแล้วก่อนเวลาเข้าเท่านั้น (ไม่ใช้ข้อมูลอนาคต).

ทุกค่าเป็นตัวเลขที่ indicator บนจอ TradingView ของผู้ใช้จะให้ ณ ตอนนั้น (EMA ชุดเดียวกัน, RSI Wilder,
MACD signal SMA 9, histogram 4 สี) — แทนช่อง "MACD: ไม่ชัด" ที่ชีตเดิมกรอก 14 จาก 15 ไม้

ข้อที่ข้อมูลของผู้ใช้เองชี้ว่าสำคัญที่สุดอยู่ที่นี่: **stop แคบกว่าระยะแกว่งปกติของแท่ง 4H หรือไม่**.
ในชีตเดิม ไม้ที่ stop แคบกว่า 2% แพ้ทั้ง 8 ไม้ — ระยะแกว่งวัดเป็นค่ากลางของ (high−low)/close
ของแท่ง 4H 50 แท่งล่าสุด ให้รู้ว่า stop อยู่ในระยะที่ราคาแกว่งเป็นปกติหรือเปล่า
"""
from datetime import datetime, timedelta

from src.wave import trend as T
from src.wave.candles import Candle, resample_4h

EMAS = (7, 15, 25, 50, 100, 200)
NOISE_BARS = 50


def _hist_state(hist: list[float | None]) -> str | None:
    """สี histogram แบบสคริปต์ CM_MacD ของผู้ใช้"""
    if len(hist) < 2 or hist[-1] is None or hist[-2] is None:
        return None
    h, p = hist[-1], hist[-2]
    if h > 0:
        return "เหนือศูนย์ แรงขึ้น (ฟ้า)" if h > p else "เหนือศูนย์ แรงลด (น้ำเงิน)"
    return "ใต้ศูนย์ แรงลงเพิ่ม (แดง)" if h < p else "ใต้ศูนย์ แรงลงลด (น้ำตาลแดง)"


def _momentum(candles: list[Candle]) -> dict:
    closes = [c.close for c in candles]
    if len(closes) < 40:
        return {}
    m, s = T.macd_series(closes)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(m, s)]
    return {"rsi": T.rsi_series(closes)[-1], "macd_hist": _hist_state(hist)}


def build(hourly: list[Candle], daily: list[Candle], opened_at: datetime, side: str,
          entry: float | None, sl: float | None, tp: float | None) -> dict:
    tfs = T.timeframes(daily, hourly, opened_at, crypto=True)
    h1 = [c for c in hourly if c.ts + timedelta(hours=1) <= opened_at]     # แท่ง 1H ที่ปิดก่อนกดเข้า
    c4 = tfs["4H"]
    want = "up" if side == "long" else "down"
    ladder = {t.tf: t.state for t in T.ladder(tfs)}
    ctx: dict = {"asof": opened_at.isoformat(timespec="minutes"), "trend": ladder,
                 "with_trend": [tf for tf, st in ladder.items() if st == want],
                 "against_trend": [tf for tf, st in ladder.items() if st in ("up", "down") and st != want],
                 "4H": _momentum(c4), "1H": _momentum(h1)}

    if c4:
        closes = [c.close for c in c4]
        last = closes[-1]
        emas = {n: T.ema(closes, n)[-1] for n in EMAS}
        known = {n: v for n, v in emas.items() if v is not None}
        good = sum(1 for v in known.values() if (last > v if side == "long" else last < v))
        ctx["ema_4h"] = {"aligned": good, "of": len(known)}
        recent = c4[-NOISE_BARS:]
        noise = sorted((c.high - c.low) / c.close * 100 for c in recent)[len(recent) // 2]
        ctx["noise_pct_4h"] = round(noise, 2)

    return with_stop(ctx, side, entry, sl, tp)


def with_stop(ctx: dict, side: str, entry: float | None, sl: float | None, tp: float | None) -> dict:
    """ส่วนที่ขึ้นกับ stop/TP — แยกออกมาเพราะ stop ของไม้เก่ามาทีหลังบริบทกราฟ (stops.py)"""
    ctx = {k: v for k, v in ctx.items() if k not in ("stop_pct", "stop_inside_noise", "stop_wrong_side", "rr")}
    if entry and sl:
        stop_pct = abs(entry - sl) / entry * 100
        ctx["stop_pct"] = round(stop_pct, 2)
        if "noise_pct_4h" in ctx:
            ctx["stop_inside_noise"] = stop_pct < ctx["noise_pct_4h"]
        ctx["stop_wrong_side"] = (sl >= entry) if side == "long" else (sl <= entry)
    if entry and sl and tp and abs(entry - sl) > 0:
        ctx["rr"] = round(abs(tp - entry) / abs(entry - sl), 2)
    return ctx


def risk(t: dict) -> dict:
    """เงินที่เสี่ยงจริงต่อไม้ = ระยะถึง stop × ขนาดเป็นเหรียญ — คนละอย่างกับมาร์จินที่วาง.
    (ผู้ใช้วางมาร์จิน ~10% ของพอร์ต แต่เงินที่เสียจริงตอนโดน stop ในชีตเดิมคือ 0.5–2.75%)"""
    entry, sl, n, ct = t.get("entry"), t.get("sl"), t.get("contracts"), t.get("ct_val")
    if not (entry and sl and n and ct):
        return {}
    usd = abs(entry - sl) * n * ct
    out = {"risk_usd": round(usd, 2)}
    if t.get("equity"):
        out["risk_pct"] = round(usd / t["equity"] * 100, 2)
    return out
