"""สถิติจากสมุด — "ไม้แบบไหนชนะ" ด้วยตัวเลขของผู้ใช้เอง ไม่ใช่ความจำ.

แบ่งกลุ่มสองแบบวางคู่กัน: ตามปุ่มที่ผู้ใช้แตะ (สิ่งที่คิดตอนเข้า) และตามที่ระบบวัดเอง (เทรนด์จริง,
stop เทียบระยะแกว่ง, R:R ที่วาง) — ตรงที่สองฝั่งไม่ตรงกันคือที่น่าดู เช่น แตะ "ตามเทรนด์" แต่ D เป็นขาลง

กลุ่มที่มีไม่ถึง MIN_N ไม้ติดธง "น้อยเกิน" ไว้เสมอ — 4 ใน 4 ฟังดูเด็ดขาด แต่มันคือ 4 ไม้
"""
from collections import defaultdict

from src.journal.context import risk
from src.journal.tags import GROUPS

MIN_N = 10
UNTAGGED_LINKS = 5      # ลิงก์ไม้ที่ยังไม่แตะเหตุผลในสรุปรายสัปดาห์ — ห้าอันพอทำจบในครั้งเดียว


def _rr_bucket(t: dict) -> str | None:
    e, sl, tp = t.get("entry"), t.get("sl"), t.get("tp")
    if not (e and sl and tp) or e == sl:
        return None
    rr = abs(tp - e) / abs(e - sl)
    return "R:R ไม่เกิน 3" if rr <= 3 else "R:R 3–5" if rr <= 5 else "R:R เกิน 5"


def _stop_bucket(t: dict) -> str | None:
    ctx = t.get("context") or {}
    if "stop_inside_noise" in ctx:
        return "stop แคบกว่าระยะแกว่ง 4H" if ctx["stop_inside_noise"] else "stop กว้างกว่าระยะแกว่ง 4H"
    e, sl = t.get("entry"), t.get("sl")
    if e and sl:          # ไม้เก่าที่ไม่มีบริบท ใช้เกณฑ์ 2% ที่เห็นจากชีตเดิม
        return "stop แคบกว่า 2%" if abs(e - sl) / e * 100 < 2 else "stop 2% ขึ้นไป"
    return None


def _trend_bucket(t: dict) -> str | None:
    ctx = t.get("context") or {}
    tr = ctx.get("trend") or {}
    if "D" not in tr:
        return None
    want = "up" if t.get("side") == "long" else "down"
    st = tr["D"]
    return "ตามเทรนด์ D (ระบบวัด)" if st == want else "สวนเทรนด์ D (ระบบวัด)" if st in ("up", "down") else "D ปนกัน"


def _check_bucket(t: dict, since: str | None) -> str | None:
    """เช็กก่อนเข้าหรือกดเข้าเลย — นับเฉพาะไม้ที่เปิดหลังเริ่มมีเช็กลิสต์ (ไม้ก่อนหน้านั้นไม่มีทางได้เช็ก
    ถ้านับรวมจะดูเหมือน 'ไม่ได้เช็ก' แพ้เยอะ ทั้งที่เป็นแค่ไม้ยุคก่อน)"""
    if not since or not t.get("opened_at") or t["opened_at"] < since:
        return None
    return "เช็กก่อนเข้า" if t.get("check_id") else "กดเข้าโดยไม่ได้เช็ก"


def _week_of(iso: str):
    from datetime import date, timedelta
    d = date.fromisoformat(iso[:10])
    return d - timedelta(days=d.weekday())          # สัปดาห์จันทร์–อาทิตย์ ตามวันที่เปิดไม้ (UTC)


def week_count(trades: list[dict], opened_at: str) -> int:
    """ไม้นี้เป็นไม้ที่เท่าไรของสัปดาห์ (นับทุกไม้ที่เปิดในสัปดาห์เดียวกันจนถึงไม้นี้)"""
    w = _week_of(opened_at)
    return sum(1 for t in trades if t.get("opened_at") and _week_of(t["opened_at"]) == w
               and t["opened_at"] <= opened_at)


def week_bucket(n: int) -> str:
    # ข้อมูลจริง ณ Phase 56: สัปดาห์ที่เปิด 5+ ไม้ ชนะ 1/16 สุทธิ −276$ · 1–2 ไม้ +7.5$ — เกณฑ์แบ่ง
    # คงที่ แต่ผลของแต่ละกลุ่มคิดสดจากสมุดทุกครั้ง (บทเรียนชีต: ห้ามฝังผลไว้ในโค้ด)
    return "สัปดาห์ที่เปิด 1–2 ไม้" if n <= 2 else "สัปดาห์ที่เปิด 3–4 ไม้" if n <= 4 else "สัปดาห์ที่เปิด 5 ไม้ขึ้นไป"


def hold_bucket(t: dict) -> str | None:
    from datetime import datetime
    if not (t.get("opened_at") and t.get("closed_at")):
        return None
    h = (datetime.fromisoformat(t["closed_at"]) - datetime.fromisoformat(t["opened_at"])).total_seconds() / 3600
    return "ถือไม่ถึง 1 ชม." if h < 1 else "ถือ 1–24 ชม." if h < 24 else "ถือเกิน 1 วัน"


def _summary(trades: list[dict]) -> dict:
    n = len(trades)
    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    net = sum(t.get("pnl") or 0 for t in trades)
    return {"n": n, "wins": wins, "win_rate": wins / n if n else None, "net": round(net, 2),
            "thin": n < MIN_N}


def compute(trades: list[dict], checks_since: str | None = None) -> dict:
    done = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]
    groups: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    per_week: dict = defaultdict(int)
    for t in trades:
        if t.get("opened_at"):
            per_week[_week_of(t["opened_at"])] += 1
    for t in done:
        if t.get("opened_at"):
            groups["จำนวนไม้ในสัปดาห์นั้น"][week_bucket(per_week[_week_of(t["opened_at"])])].append(t)
        hb = hold_bucket(t)
        if hb:
            groups["เวลาถือ"][hb].append(t)
        for g in GROUPS:
            for v in (t.get("tags") or {}).get(g["key"], []):
                groups[g["label"]][v].append(t)
        for title, fn in (("R:R ที่วางไว้", _rr_bucket), ("stop เทียบระยะแกว่ง", _stop_bucket),
                          ("เทรนด์จริงตอนเข้า", _trend_bucket),
                          ("เช็กลิสต์ก่อนเข้า", lambda t: _check_bucket(t, checks_since))):
            b = fn(t)
            if b:
                groups[title][b].append(t)
    wins = [t["pnl"] for t in done if t["pnl"] > 0]
    losses = [-t["pnl"] for t in done if t["pnl"] <= 0]
    risks = [r["risk_pct"] for r in (risk(t) for t in done) if "risk_pct" in r]
    return {
        "overall": {**_summary(done),
                    "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
                    "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
                    "avg_risk_pct": round(sum(risks) / len(risks), 2) if risks else None},
        "groups": {title: {k: _summary(v) for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))}
                   for title, g in groups.items()},
        "untagged": sum(1 for t in trades if not t.get("tags")),
        # Phase 56: ไม้จาก OKX ไม่มีใครแตะเหตุผลเลย (0/101) — สรุปรายสัปดาห์ยื่นลิงก์ไม้ล่าสุดให้กดทีละอัน
        "untagged_recent": [
            {"id": t["id"], "closed_at": t["closed_at"], "side": t["side"], "pnl": t["pnl"]}
            for t in sorted((t for t in done if not t.get("tags") and t.get("closed_at")),
                            key=lambda t: t["closed_at"], reverse=True)[:UNTAGGED_LINKS]
        ],
    }


def format_report(stats: dict) -> str:
    """ภาษาคนอ่าน — สำหรับ Discord รายสัปดาห์"""
    o = stats["overall"]
    if not o["n"]:
        return "**สมุดเทรด** — ยังไม่มีไม้ที่ปิดแล้ว"
    L = [f"**สมุดเทรด** — ปิดแล้ว {o['n']} ไม้ · ชนะ {o['wins']} ({o['win_rate']:.0%}) · สุทธิ {o['net']:+,.2f}$"]
    if o["avg_win"] and o["avg_loss"]:
        L.append(f"ชนะเฉลี่ย {o['avg_win']:,.2f}$ · แพ้เฉลี่ย {o['avg_loss']:,.2f}$ "
                 f"(ชนะหนึ่งไม้ = แพ้ {o['avg_win'] / o['avg_loss']:.1f} ไม้)")
    if o["avg_risk_pct"] is not None:
        L.append(f"เสี่ยงจริงเฉลี่ยต่อไม้ {o['avg_risk_pct']:.2f}% ของพอร์ต")
    for title, g in stats["groups"].items():
        L.append(f"\n**{title}**")
        for k, s in g.items():
            thin = " _(น้อยเกิน สรุปไม่ได้)_" if s["thin"] else ""
            L.append(f"• {k}: {s['n']} ไม้ ชนะ {s['wins']} ({s['win_rate']:.0%}) · {s['net']:+,.2f}${thin}")
    if stats["untagged"]:
        L.append(f"\nยังไม่ได้แตะเหตุผล {stats['untagged']} ไม้ — สถิติ \"ชนะ/แพ้เพราะอะไร\" ยังว่างจนกว่าจะแตะ")
        if stats.get("untagged_recent"):
            import os
            url = os.environ.get("JOURNAL_WEB_URL", "http://localhost:3000").rstrip("/")
            L.append("ไม้ล่าสุดที่ยังไม่แตะ (กดทีละอัน ใช้เวลาไม่ถึงนาที):")
            L += [f"• {u['closed_at'][:10]} {'Long' if u['side'] == 'long' else 'Short'} {u['pnl']:+,.2f}$ → "
                  f"{url}/journal#t{u['id']}" for u in stats["untagged_recent"]]
    return "\n".join(L)
