"""โหลดไฟล์ count (data/waves/*.json) -> ดึงแท่ง -> รายงาน (พร้อมระดับใหญ่ถ้ามี).

ไฟล์ count เป็น JSON ที่ commit ได้ — ประวัติ git ของไฟล์นี้คือประวัติว่าเคยนับยังไง และเปลี่ยนใจ
ตอนไหน ซึ่งเป็นสิ่งที่ปกติหายไปพร้อมเส้นที่ลบทิ้งบน TradingView
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.wave import trend as T
from src.wave.analysis import Evidence, Report, analyze, fmt, resolve
from src.wave.auto import find_counts, pick
from src.wave.candles import Candle, fetch, resample_4h
from src.wave.pivots import snap

TREND_DAILY_PERIOD = "10y"     # แท่ง Month ต้องย้อนยาวพอให้เห็นยอด/ก้นสองรอบ
RECENT_DIV_BARS = 30           # divergence ที่ยืนยันภายใน 30 แท่งล่าสุดของ TF นั้นถึงรายงาน


def _marks(raw: list[list[str]]) -> list[tuple[str, datetime]]:
    return [(label, datetime.fromisoformat(at)) for label, at in raw]


def build(spec: dict, fetcher=fetch, now: datetime | None = None) -> Report:
    """fetcher(symbol, interval, period) -> list[Candle] | None — ใส่ตัวปลอมได้ = เทสต์ได้"""
    candles = fetcher(spec["symbol"], spec.get("interval", "1h"), spec.get("period", "60d"))
    if candles is None:
        raise RuntimeError(f"ดึงราคา {spec['symbol']} ไม่ได้")
    pivots = resolve(candles, _marks(spec["marks"]), spec["direction"], spec.get("snap_hours", 12))
    rep = analyze(spec["name"], spec["symbol"], spec["direction"], pivots, candles,
                  spec.get("wave4"), now)


    parent = spec.get("parent")
    if parent:
        pc = fetcher(spec["symbol"], parent.get("interval", "1d"), parent.get("period", "1y"))
        if pc is not None:
            pp = resolve(pc, _marks(parent["marks"]), spec["direction"], parent.get("snap_hours", 72))
            rep.parent = analyze(parent["name"], spec["symbol"], spec["direction"], pp, pc)
            rep.parent_note = _parent_note(rep, rep.parent)
            rep.parent.auto = _auto(pc, pp)

    # เครื่องนับเองบนแท่ง 4H (ระดับย่อย) โดยเริ่มจากจุด 0 เดียวกับที่ผู้ใช้มาร์ก — ถ้าเริ่มคนละจุด
    # จะเทียบกันไม่ได้ว่า "เห็นต่างตรงไหน"
    rep.auto = _auto(resample_4h(candles), pivots)

    # หลังระดับใหญ่ — การเทียบแรงส่งคลื่น 3 กับ 5 ใช้จุดของระดับใหญ่
    daily = fetcher(spec["symbol"], "1d", TREND_DAILY_PERIOD)
    if daily is not None:
        asof = now or datetime.now(timezone.utc).replace(tzinfo=None)
        tfs = T.timeframes(daily, candles, asof, crypto=spec["symbol"].endswith("-USD"))
        rep.trend = T.ladder(tfs)
        _add_divergences(rep, tfs, spec["direction"])
    return rep


def _auto(candles: list[Candle], user: list) -> list:
    anchor = snap(candles, "0", user[0].ts, user[0].kind, 24 * 3)
    return pick(find_counts(candles, anchor, user=user)) if anchor else []


def _add_divergences(rep: Report, tfs: dict[str, list[Candle]], direction: str) -> None:
    """divergence ล่าสุดของ D/4H ตามสคริปต์ TradingView ของผู้ใช้ — เป็นหลักฐาน ไม่ใช่กฎ.
    bear ในขาขึ้น = แรงส่งอ่อนลงที่ยอด -> เข้าทางฉากที่คาดการย่อ (B); ขาลงกลับกัน"""
    for tf in ("D", "4H"):
        cs = tfs.get(tf) or []
        if len(cs) < RECENT_DIV_BARS:
            continue
        cutoff = cs[-RECENT_DIV_BARS].ts
        for ind in ("RSI", "MACD"):
            recent = [d for d in T.divergences(tf, cs, ind) if d.confirmed_ts >= cutoff]
            if not recent:
                continue
            d = recent[-1]
            rep.divergences.append(d)
            against = (d.kind == "bear") == (direction == "up")
            rep.evidence.append(Evidence(
                f"{tf} {ind} {'bearish' if d.kind == 'bear' else 'bullish'} divergence: ราคา "
                f"{fmt(d.price_prev)} → {fmt(d.price_now)} แต่ {ind} {d.ind_prev:,.1f} → "
                f"{d.ind_now:,.1f} (ยอดวันที่ {d.pivot_ts:%d %b}, ยืนยัน {d.confirmed_ts:%d %b} — "
                f"สคริปต์ยืนยันช้า 5 แท่งเสมอ)", "B" if against else "A"))
    if rep.parent is not None and rep.parent.sub:
        _momentum_3_vs_5(rep, tfs.get("D") or [], direction)


def _momentum_3_vs_5(rep: Report, daily: list[Candle], direction: str) -> None:
    """ตำราคลาสสิก: ยอดคลื่น 5 มักมีแรงส่งน้อยกว่ายอดคลื่น 3 — เทียบ RSI/MACD Day ที่ยอดคลื่น 3
    ของระดับใหญ่ กับยอดล่าสุด. รายงานแยก RSI กับ MACD เพราะสองตัวพูดไม่ตรงกันได้ (BTC ต.ค. 2026:
    MACD ลดชัด แต่ RSI แทบเท่าเดิม) — รวมเป็นคำว่า 'มี divergence' คำเดียวจะทำให้ข้อมูลหาย"""
    if not daily:
        return
    closes = [c.close for c in daily]
    rsi, (macd, _) = T.rsi_series(closes), T.macd_series(closes)
    day = lambda ts: next((i for i, c in enumerate(daily) if c.ts.date() == ts.date()), None)
    p3, top = rep.parent.pivots[3], rep.parent.sub["s1_ts"]
    i3, it = day(p3.ts), day(top)
    if i3 is None or it is None or rsi[i3] is None or macd[i3] is None:
        return
    up = direction == "up"
    for name, a, b in (("RSI", rsi[i3], rsi[it]), ("MACD", macd[i3], macd[it])):
        weaker = (b < a) if up else (b > a)
        rep.evidence.append(Evidence(
            f"{name} Day ที่ยอดคลื่น 3 ของ {rep.parent.name} ({p3.ts:%d %b}) = {a:,.1f} · ที่ยอดล่าสุด "
            f"({top:%d %b}) = {b:,.1f} — " + ("แรงส่งน้อยกว่า (ทรงยอดคลื่น 5 ตามตำรา)" if weaker
                                              else "แรงส่งไม่น้อยกว่า"), "B" if weaker else "A"))


def _parent_note(child: Report, parent: Report) -> str:
    """ระดับเล็กจบ = ระดับใหญ่ขยับหนึ่งขั้น — เขียนออกมาให้เห็นว่าฉาก B ของขาว แปลว่าอะไรกับเหลือง"""
    if not parent.valid:
        return f"count {parent.name} ผิดกฎเหล็ก — ดูรายละเอียดด้านล่าง"
    if len(parent.pivots) != 5 or not child.sub:
        return ""
    s = 1 if parent.direction == "up" else -1
    top, start = child.sub["s1"], parent.pivots[0].price
    whole = abs(top - start)
    levels = " / ".join(fmt(top - s * r * whole) for r in (0.382, 0.5, 0.618))
    return (f"ถ้าฉาก B ถูก (ขาวจบ) = คลื่น 5 ของ {parent.name} จบด้วย → ทั้งขาจาก {fmt(start)} "
            f"ครบ 5 คลื่น · เป้าปรับฐาน 38.2 / 50 / 61.8% = {levels}")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
