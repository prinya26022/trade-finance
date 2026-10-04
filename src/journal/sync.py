"""รอบซิงก์: OKX -> สมุด -> บริบทกราฟของไม้ใหม่ -> แจ้ง Discord เฉพาะไม้ที่เพิ่งเปิด/เพิ่งปิด.

แจ้งเฉพาะตอนสถานะเปลี่ยน (เหมือนเรดาร์อื่นในโปรเจกต์) — ข้อความของไม้ที่ยังเปิดอยู่เดิมไม่ส่งซ้ำ
ทุกชั่วโมง ไม่งั้นช่องจะกลายเป็นสิ่งที่ถูกเลื่อนผ่าน
"""
import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from src.journal import context as C
from src.journal import okx, store

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_JOURNAL"
WEB_URL_ENV = "JOURNAL_WEB_URL"            # ลิงก์ในข้อความ Discord (ค่าเริ่มต้น = เว็บในเครื่อง)


@dataclass
class SyncReport:
    opened: list[dict] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    error: str | None = None


def _candles():
    from src.wave.candles import fetch
    return fetch("BTC-USD", "1h", "180d"), fetch("BTC-USD", "1d", "10y")


def sync(client: okx.Client, db_path: Path | None = None, candles=None, ct_val: float | None = None) -> SyncReport:
    rep = SyncReport()
    ct = ct_val or okx.contract_value()
    equity = client.equity()
    stops = client.stops()
    seen = []
    for t in client.open_positions():
        s = stops.get(t["side"], {})
        seen.append({**t, "ct_val": ct, "sl": s.get("sl"), "tp": s.get("tp"), "equity": equity})
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
            from datetime import datetime
            for t in need:
                at = datetime.fromisoformat(t["opened_at"])
                if at < hourly[0].ts + timedelta(days=60):
                    continue           # เก่ากว่าข้อมูล 1H ที่มี — ไม่เดาบริบท
                store.set_context(t["id"], C.build(hourly, daily, at, t["side"], t["entry"], t["sl"], t["tp"]),
                                  db_path)
    rep.opened = [store.get(t["id"], db_path) for t in rep.opened]
    rep.closed = [store.get(t["id"], db_path) for t in rep.closed]
    return rep


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


def notify(rep: SyncReport) -> None:
    from src.notify.discord import post
    url = os.environ.get(WEBHOOK_ENV)
    for t in rep.opened + rep.closed:
        post(describe(t), url)
