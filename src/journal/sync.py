"""รอบซิงก์: OKX -> สมุด -> บริบทกราฟของไม้ใหม่ -> แจ้ง Discord เฉพาะไม้ที่เพิ่งเปิด/เพิ่งปิด.

แจ้งเฉพาะตอนสถานะเปลี่ยน (เหมือนเรดาร์อื่นในโปรเจกต์) — ข้อความของไม้ที่ยังเปิดอยู่เดิมไม่ส่งซ้ำ
ทุกชั่วโมง ไม่งั้นช่องจะกลายเป็นสิ่งที่ถูกเลื่อนผ่าน
"""
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.journal import context as C
from src.journal import okx, stops, store

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_JOURNAL"
NEWS_HOURS = 48     # แจ้งเฉพาะไม้ที่เปิด/ปิดภายในช่วงนี้ — ไม้ย้อนหลังที่เพิ่งดึงมาครั้งแรกคือประวัติ ไม่ใช่ข่าว
WEB_URL_ENV = "JOURNAL_WEB_URL"            # ลิงก์ในข้อความ Discord (ค่าเริ่มต้น = เว็บในเครื่อง)


@dataclass
class SyncReport:
    opened: list[dict] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    error: str | None = None


def _candles():
    from src.wave.candles import fetch
    # 730 วัน = สูงสุดที่ yfinance ให้แท่ง 1H — ซิงก์ครั้งแรกดึงประวัติย้อนหลังได้เป็นปี
    return fetch("BTC-USD", "1h", "730d"), fetch("BTC-USD", "1d", "10y")


def sync(client: okx.Client, db_path: Path | None = None, candles=None, ct_val: float | None = None) -> SyncReport:
    rep = SyncReport()
    first_run = not any(t["source"] == "okx" for t in store.all_trades(db_path))
    ct = ct_val or okx.contract_value()
    equity = client.equity()
    if equity:
        store.set_meta("equity", equity, db_path)      # หน้าเช็กลิสต์ใช้คิด % ความเสี่ยง
    stops = client.stops()
    seen = []
    for t in client.open_positions():
        s = stops.get(t["side"], {})
        seen.append({**t, "ct_val": ct, "sl": s.get("sl"), "tp": s.get("tp"), "equity": equity,
                     "sl_source": "seen" if s.get("sl") else None})
    seen += [{**t, "ct_val": ct} for t in client.closed_positions()]

    fresh = []
    for t in seen:
        tid, state = store.upsert(t, db_path)
        if state == "new":
            fresh.append(tid)
            (rep.opened if t["status"] == "open" else rep.closed).append(store.get(tid, db_path))
        elif state == "closed":
            rep.closed.append(store.get(tid, db_path))

    # บริบทกราฟ ณ เวลาเข้า: คิดครั้งเดียวต่อไม้ (ค่าของอดีตไม่เปลี่ยน) — ดึงแท่งเฉพาะเมื่อมีไม้ใหม่
    need = [t for t in store.all_trades(db_path) if t["context"] is None and t["opened_at"]]
    if need:
        hourly, daily = candles or _candles()
        if hourly and daily:
            for t in need:
                at = datetime.fromisoformat(t["opened_at"])
                if at < hourly[0].ts + timedelta(days=60):
                    continue           # เก่ากว่าข้อมูล 1H ที่มี — ไม่เดาบริบท
                store.set_context(t["id"], C.build(hourly, daily, at, t["side"], t["entry"], t["sl"], t["tp"]),
                                  db_path)
    backfill_stops(client, db_path, pages=1 if not first_run else 30)
    from src.journal.check import link_checks
    for check_id, trade_id in link_checks(store.all_trades(db_path), store.all_checks(db_path)):
        store.link_check(check_id, trade_id, db_path)
    rep.opened = [store.get(t["id"], db_path) for t in rep.opened]
    rep.closed = [store.get(t["id"], db_path) for t in rep.closed]
    return rep


def backfill_stops(client, db_path: Path | None = None, pages: int = 30) -> dict:
    """เติม stop ตัวแรกให้ไม้ที่ยังไม่มี หรือมีแค่ค่าที่ 'เห็นทีหลัง' — แล้วคิดส่วนที่ขึ้นกับ stop ใหม่.
    ซิงก์ปกติดูแค่หน้าแรก (ไม้ใหม่), ครั้งแรก/สั่งเองไล่ย้อนหลังได้หลายหน้า"""
    todo = [t for t in store.all_trades(db_path)
            if t["source"] == "okx" and t["sl_source"] not in ("entry", "algo")]
    if not todo:
        return {"checked": 0, "entry": 0, "algo": 0}
    orders, algos = client.entry_orders(pages=pages), client.algo_history()
    found = {"checked": len(todo), "entry": 0, "algo": 0}
    for t in todo:
        m = stops.match(t, orders, algos)
        if not m or not m["sl"]:
            continue
        store.set_stops(t["id"], m["sl"], m["tp"], m["source"], db_path)
        found[m["source"]] += 1
        if t["context"]:
            store.set_context(t["id"], C.with_stop(t["context"], t["side"], t["entry"], m["sl"], m["tp"] or t["tp"]),
                              db_path)
    return found


def _past_line(label: str, s: dict | None) -> str:
    if not s or not s.get("n"):
        return f"• {label}: ยังไม่มีไม้แบบนี้ในอดีต"
    thin = " _(น้อยเกิน สรุปไม่ได้)_" if s["thin"] else ""
    warn = "⚠️ " if s["net"] < 0 and not s["thin"] else ""
    return f"• {warn}{label}: ในอดีต {s['n']} ไม้ ชนะ {s['wins']} ({s['win_rate']:.0%}) · {s['net']:+,.2f}${thin}"


def auto_check(t: dict, trades: list[dict], wave: dict | None = None) -> list[str]:
    """เช็กลิสต์ /check ที่รันให้เองตอนไม้เข้าสมุด (Phase 56) — ผู้ใช้ไม่เคยเปิด /check ก่อนกดเข้าเลย (0 ครั้ง)
    เพราะต้องกรอก ซึ่งขัดกับนิสัย "ขี้เกียจกรอก" ที่ผู้ใช้บอกเอง ที่นี่จึงตอบคำถามเดียวกันจากคำสั่งจริงบน OKX:
    ไม้หน้าตาแบบนี้ในอดีตของคุณได้ผลยังไง + เป็นไม้ที่เท่าไรของสัปดาห์ + stop อยู่ตรงไหนเทียบเส้นตายคลื่น.
    ไม่บันทึกเป็นรายการเช็ก — สถิติ "เช็กก่อนเข้า vs กดเข้าเลย" ต้องนับเฉพาะเช็กที่ผู้ใช้ทำเองก่อนเข้า"""
    from src.journal import stats as S
    from src.journal.check import _wave_lines
    others = [x for x in trades if x.get("id") != t.get("id")]
    groups = S.compute(others)["groups"]
    L = ["**ไม้หน้าตาแบบนี้ในอดีตของคุณ**"]
    if t["status"] == "open":
        for title, b in (("R:R ที่วางไว้", S._rr_bucket(t)), ("stop เทียบระยะแกว่ง", S._stop_bucket(t)),
                         ("เทรนด์จริงตอนเข้า", S._trend_bucket(t))):
            if b:
                L.append(_past_line(b, groups.get(title, {}).get(b)))
        if t.get("opened_at"):
            n = S.week_count(trades, t["opened_at"])
            b = S.week_bucket(n)
            L.append(_past_line(f"ไม้ที่ {n} ของสัปดาห์นี้ ({b})", groups.get("จำนวนไม้ในสัปดาห์นั้น", {}).get(b)))
        if wave and (t.get("inst") or "").startswith("BTC"):
            rows = _wave_lines(t["side"], t.get("sl"), wave)
            mine = [r for r in rows if r["with_trade"]]
            if mine:
                L += [f"• คลื่น: ฉาก {r['key']} ({r['title']}) — {r.get('stop_vs_kill', 'ไม่มี stop ให้เทียบ')}"
                      for r in mine]
            elif rows:
                L.append("• ⚠️ คลื่น: ไม่มีฉากที่ยังไม่ตายอยู่ฝั่งเดียวกับไม้นี้ ("
                         + " · ".join(f"{r['key']} {r['title']}" for r in rows) + ")")
    else:
        b = S.hold_bucket(t)
        if b:
            L.append(_past_line(b, groups.get("เวลาถือ", {}).get(b))
                     + " _(เวลาถือเป็นผลด้วย: ไม้ที่โดน stop มักสั้นเอง)_")
    return L if len(L) > 1 else []


def describe(t: dict) -> str:
    """ข้อความสั้นต่อไม้ — ตัวเลขจริง + สิ่งที่ข้อมูลของผู้ใช้เองบอกว่าสำคัญ (stop, R:R, เทรนด์)"""
    side = "Long" if t["side"] == "long" else "Short"
    ctx = t.get("context") or {}
    head = (f"**{'เปิด' if t['status'] == 'open' else 'ปิด'} {t['inst']} {side}** ที่ {t['entry']:,.1f}"
            if t.get("entry") else f"**{t['inst']} {side}**")
    L = [head]
    if t["status"] == "closed" and t.get("pnl") is not None:
        L.append(f"ผล {t['pnl']:+,.2f}$" + (" (โดน liquidate)" if t.get("liquidated") else ""))
    r = C.risk(t)
    if r:
        L.append(f"เสี่ยงจริงถ้าโดน stop: {r['risk_usd']:,.2f}$" + (f" = {r['risk_pct']:.2f}% ของพอร์ต" if "risk_pct" in r else ""))
    elif t["status"] == "open" and not t.get("sl"):
        L.append("⚠️ ไม่เห็นคำสั่ง stop loss ค้างอยู่")
    if "stop_pct" in ctx and "noise_pct_4h" in ctx:
        inside = ctx.get("stop_inside_noise")
        L.append(f"stop ห่าง {ctx['stop_pct']:.2f}% · แท่ง 4H แกว่งปกติ {ctx['noise_pct_4h']:.2f}%"
                 + (" ← stop อยู่ในระยะแกว่งปกติ" if inside else ""))
    if ctx.get("stop_wrong_side"):
        L.append("⚠️ stop อยู่ผิดฝั่งของราคาเข้า")
    if "rr" in ctx:
        L.append(f"R:R ที่วาง {ctx['rr']:.1f}")
    if ctx.get("trend"):
        L.append("เทรนด์ตอนเข้า: " + " · ".join(f"{k} {v}" for k, v in ctx["trend"].items())
                 + (f" → สวน {', '.join(ctx['against_trend'])}" if ctx.get("against_trend") else ""))
    url = os.environ.get(WEB_URL_ENV, "http://localhost:3000").rstrip("/")
    L.append(f"แตะเหตุผล: {url}/journal#t{t['id']}")
    return "\n".join(L)


def is_news(t: dict, now: datetime | None = None) -> bool:
    """ไม้ที่ควรแจ้ง = เปิดหรือปิดภายใน NEWS_HOURS ชม.ล่าสุด.
    ซิงก์ครั้งแรกเคยส่งทุกไม้ย้อนหลัง 101 ไม้จน Discord บล็อก และเข้าช่องหลักเพราะยังไม่ได้ตั้งช่องแยก
    — ประวัติที่เพิ่งถูกดึงมาไม่ใช่เหตุการณ์ที่ต้องรู้ตอนนี้"""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    stamp = t.get("closed_at") if t.get("status") == "closed" else t.get("opened_at")
    if not stamp:
        return False
    return now - datetime.fromisoformat(stamp) <= timedelta(hours=NEWS_HOURS)


def _wave_snapshot() -> dict | None:
    try:
        from src.wave import snapshot
        return snapshot.read("btc")
    except Exception:            # ไม่มี snapshot (ยังไม่เคยรันคลื่น) ก็ยังแจ้งไม้ได้ตามปกติ
        return None


def notify(rep: SyncReport, now: datetime | None = None, trades: list[dict] | None = None,
           wave: dict | None = None) -> int:
    from src.notify.discord import post
    url = os.environ.get(WEBHOOK_ENV)
    news = [t for t in rep.opened + rep.closed if is_news(t, now)]
    if news:
        trades = store.all_trades() if trades is None else trades
        wave = _wave_snapshot() if wave is None else wave
    for t in news:
        post("\n".join([describe(t)] + auto_check(t, trades, wave)), url)
    return len(news)
