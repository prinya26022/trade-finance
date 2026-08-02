"""สมุดพกของเอเจนต์เอง (Phase 32) — เอาเกณฑ์ที่ Phase 30/31 ใช้จับข้ออ้างคนอื่น มาจับตัวเอง.

Phase 31 ทำตัวแปลข้ออ้างเพื่อบอกว่าข้อไหน 'พิสูจน์ผิดไม่ได้' แต่คะแนนสุขภาพของเราเองไม่เคยถูก
พิสูจน์ผิดเลยสักครั้ง — ไฟล์นี้แก้ความไม่สมมาตรนั้น. ใช้แค่ข้อมูลที่เก็บ point-in-time ไว้แล้วใน
analyses (health_reasons_json ทุกแถวมี fundamental.criteria + valuation ครบ) ไม่เรียก LLM
ไม่กิน Gemini quota.

แยกเป็น 2 คำถาม เพราะ 'ตอบได้ตอนนี้' ไม่เท่ากัน — และการเอามารวมกันคือวิธีหลอกตัวเองที่ง่ายที่สุด:

  (1) คะแนน "นิ่ง" พอจะเชื่อได้ไหม  -> ตอบได้ทันที
      ถ้าคะแนนพื้นฐานของบริษัทเดิมขยับ 3 จุดใน 1 เดือนโดยไม่มีงบใหม่มาคั่น แปลว่าเรากำลังวัด
      ความพร้อมของ 'ข้อมูลฝั่งเรา' ไม่ใช่ความแข็งแรงของธุรกิจ — และคะแนนที่ไม่นิ่งจะทำนายอะไร
      ไม่ได้อยู่แล้ว จึงต้องผ่านด่านนี้ก่อนถึงจะไปด่าน (2) ได้อย่างมีความหมาย.

  (2) คะแนนสูงให้ผลตอบแทนดีกว่าคะแนนต่ำจริงไหม  -> ยังตอบไม่ได้ ต้องรอเวลา
      ต้องมี snapshot ที่ 'แก่พอ' จะวัดผลล่วงหน้าได้จริง ไม่ใช่เอาคะแนนวันนี้ไปคู่กับราคาวันนี้
      (นั่นคือ look-ahead bias เต็มๆ). โค้ดคำนวณพร้อมแล้ว แต่จะรายงานว่า 'ยังไม่พอ' จนกว่าจะถึง
      วัน — ตัวเลขที่คำนวณจากกลุ่มตัวอย่าง 0 จุดแล้วเอาไปโชว์ แย่กว่าไม่โชว์เลย.

การแบ่ง bucket ของการขยับคะแนน (หัวใจของด่าน 1) — ทุกอันคำนวณตรงจาก snapshot ไม่ได้เดา:
  business  = เกณฑ์ที่คำนวณได้ทั้งสองรอบ แล้วค่าขยับ            -> ธุรกิจเปลี่ยนจริง (ควรมี)
  data      = เกณฑ์ที่พลิก null <-> ตัวเลข หรือ valuation เปลี่ยน lens -> ข้อมูล/วิธีคิดฝั่งเราเปลี่ยน
  estimate  = realistic_growth ที่เราประมาณเอง ถูกแก้             -> ความเห็นเราเปลี่ยน ไม่ใช่บริษัท
  price     = implied_growth ขยับเพราะราคา/EV                    -> ควรขยับ นี่คือหน้าที่ของขา valuation
  other     = ส่วนที่เหลือ (breach penalty, ปัดเศษ)               -> ไม่ยัดเข้า bucket อื่นให้ตัวเลขสวย

"น่ากังวล" = data + estimate เท่านั้น. business กับ price ขยับได้เป็นเรื่องปกติ — business คือสิ่งที่
เราตั้งใจวัด ส่วน price คือสิ่งที่ขา valuation ออกแบบมาให้ตอบสนอง. ปนสองอันนี้เข้าไปด้วยจะได้
ข้อสรุปว่า "คะแนนไม่นิ่ง" ทุกตัวจนตัวเลขไม่มีความหมาย.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

# ใช้ฟังก์ชันแปลง gap -> คะแนนตัวเดียวกับที่ valuation.py ใช้ตอนให้คะแนนจริง (แม้ชื่อขึ้นต้นด้วย _)
# เพราะการแยก 'ราคาขยับ' ออกจาก 'ประมาณการขยับ' ต้องคำนวณคะแนนของ gap สมมติ ถ้าลอกสูตรมาไว้
# ที่นี่แล้ววันหลัง valuation.py ปรับ threshold การแบ่ง bucket จะเพี้ยนเงียบๆ โดยไม่มีเทสต์ไหนจับได้.
from src.agent.valuation import _gap_to_score
from src.history.store import all_rows

# ขยับเกินเท่านี้ (จุด, สะสมตลอดช่วง) โดยไม่ได้มาจากธุรกิจหรือราคา = ตั้งธงว่าคะแนนตัวนี้ยังไม่นิ่ง
NOISE_POINTS = 1.0

# ช่วงเวลาที่จะวัดผลล่วงหน้า (วันปฏิทิน) — 90 วันคือช่วงสั้นสุดที่พอมีความหมายกับ thesis ระยะยาว
HORIZONS = (90, 180, 365)

BUCKETS = ("business", "data", "estimate", "price", "other")

BUCKET_LABELS = {
    "business": "ธุรกิจเปลี่ยนจริง",
    "data": "ข้อมูล/วิธีคิดฝั่งเราเปลี่ยน",
    "estimate": "ประมาณการของเราเปลี่ยน",
    "price": "ราคาขยับ",
    "other": "อื่นๆ (ปรับ/ปัดเศษ)",
}

EXPECTED_BUCKETS = ("business", "price")      # ขยับได้ ไม่ถือว่าผิดปกติ


def _zero() -> dict[str, float]:
    return {b: 0.0 for b in BUCKETS}


# ---------------------------------------------------------------- snapshots

def snapshots(rows: list[dict] | None = None) -> dict[str, list[dict]]:
    """{ticker: [snapshot เก่า->ใหม่]} — 1 จุด/วันปฏิทิน (ถ้าวันไหนรันหลายรอบใช้รอบล่าสุด เหมือน
    health_trends) เพราะการรันมือซ้ำในวันเดียวไม่ใช่ 'คะแนนขยับ' แต่จะกลายเป็น pair ที่ delta=0
    มาถ่วงสถิติให้ดูนิ่งเกินจริง.

    อ่านคะแนนจาก health dict ไม่ใช่คอลัมน์ health_score เพราะคอลัมน์นั้นเก็บ comparable_score
    (เป็น None สำหรับหุ้น partial อย่าง SPCX/TSLA ที่ตี valuation ไม่ได้) — แต่ความนิ่งของ
    'ขาพื้นฐาน' ของหุ้นกลุ่มนั้นก็ยังตรวจได้และควรตรวจ.
    """
    out: dict[str, list[dict]] = {}
    for r in rows if rows is not None else all_rows():
        health = r.get("health")
        if not health or health.get("score") is None or not health.get("fundamental"):
            continue        # แถวก่อน Phase 10 หรือ excluded (คริปโต/แบงก์) — ไม่มีอะไรให้เทียบ
        run_at = r.get("run_at") or ""
        out.setdefault(r["ticker"], []).append({
            "ticker": r["ticker"],
            "date": run_at[:10],
            "run_at": run_at,
            "score": float(health["score"]),
            "max": float(health.get("max") or 11.0),
            "price": r.get("price"),
            "health": health,
        })

    for ticker, snaps in out.items():
        snaps.sort(key=lambda s: s["run_at"])
        by_day: dict[str, dict] = {}
        for s in snaps:
            by_day[s["date"]] = s          # รอบหลังของวันเดียวกันทับรอบก่อน
        out[ticker] = [by_day[d] for d in sorted(by_day)]
    return out


# ---------------------------------------------------------------- attribution

def _fundamental_delta(prev: dict, cur: dict) -> tuple[float, float, list[str]]:
    """(business, data, notes) จากการเทียบเกณฑ์ทีละข้อ.

    คะแนนขาพื้นฐาน = ผลบวกของค่าเกณฑ์ที่คำนวณได้ (เกณฑ์ที่เป็น null ไม่ได้ถูกเฉลี่ยชดเชย — มันแค่
    ไม่ได้แต้มไปเลย) เพราะฉะนั้นเกณฑ์ที่พลิกจาก null เป็น 1.0 = ได้ 1 คะแนนเต็มฟรีๆ จากการที่
    yfinance/EDGAR ส่งข้อมูลมาครบขึ้น ไม่ใช่จากผลประกอบการ. นี่คือช่องที่ทำให้ MSFT ขยับ 6.3 -> 9.1
    ใน 26 วัน และเป็นเหตุผลหลักที่ไฟล์นี้มีอยู่.
    """
    p = dict(prev.get("criteria") or [])
    c = dict(cur.get("criteria") or [])
    business = data = 0.0
    notes: list[str] = []

    for label in sorted({*p, *c}):
        pv, cv = p.get(label), c.get(label)
        if pv is not None and cv is not None:
            business += cv - pv
        else:
            gained = (cv or 0.0) - (pv or 0.0)
            data += gained
            if abs(gained) >= 0.05:
                verb = "เพิ่งคำนวณได้" if pv is None else "คำนวณไม่ได้แล้ว"
                notes.append(f"เกณฑ์ '{label}' {verb} ({gained:+.2f} จุด)")
    return business, data, notes


def _valuation_delta(prev: dict | None, cur: dict | None) -> tuple[float, float, float, list[str]]:
    """(price, estimate, data, notes) จากขา valuation.

    gap = implied − realistic. แยกสองสาเหตุด้วย gap สมมติตรงกลาง (ราคาขยับก่อน ประมาณการยังเดิม)
    แล้วให้คะแนนด้วยฟังก์ชันจริง — ได้ตัวเลขที่บวกกลับได้พอดี ไม่ใช่เฉลี่ยตามสัดส่วนแบบมั่วๆ:
        price    = f(implied_ใหม่ − realistic_เก่า) − f(implied_เก่า − realistic_เก่า)
        estimate = f(implied_ใหม่ − realistic_ใหม่) − f(implied_ใหม่ − realistic_เก่า)

    ถ้า lens เปลี่ยน (standard <-> growth <-> NA) จะไม่แยก เพราะคนละวิธีคิด — เทียบ gap ข้าม lens
    เหมือนเทียบคะแนนสอบคนละข้อสอบ ยัดทั้งก้อนเข้า data พร้อมบอกเหตุผลตรงๆ ดีกว่าแกล้งแยก.
    """
    ps = (prev or {}).get("score")
    cs = (cur or {}).get("score")
    total = (cs or 0.0) - (ps or 0.0)
    if not total:
        return 0.0, 0.0, 0.0, []

    notes: list[str] = []
    p_lens, c_lens = (prev or {}).get("lens"), (cur or {}).get("lens")
    if p_lens != c_lens:
        notes.append(f"วิธีตีมูลค่าเปลี่ยน lens '{p_lens}' -> '{c_lens}' ({total:+.2f} จุด)")
        return 0.0, 0.0, total, notes

    pi, pr = (prev or {}).get("implied_growth"), (prev or {}).get("realistic_growth")
    ci, cr = (cur or {}).get("implied_growth"), (cur or {}).get("realistic_growth")
    if None in (pi, pr, ci, cr):
        notes.append(f"ตีมูลค่าได้/ไม่ได้ไม่เหมือนกันสองรอบ ({total:+.2f} จุด)")
        return 0.0, 0.0, total, notes

    base = _gap_to_score(pi - pr)
    mid = _gap_to_score(ci - pr)
    price = mid - base
    estimate = _gap_to_score(ci - cr) - mid
    # เศษที่เหลือ = ส่วนปรับที่ไม่ได้มาจาก gap ตรงๆ (เช่น Rule of 40 ของ lens='growth') -> data
    data = total - price - estimate

    if abs(cr - pr) >= 1.0:
        notes.append(f"realistic growth ที่เราประมาณเอง {pr:.1f}% -> {cr:.1f}% ({estimate:+.2f} จุด)")
    return price, estimate, data, notes


def attribute(prev: dict, cur: dict) -> dict:
    """แยกที่มาของการขยับคะแนนระหว่าง health dict สองรอบติดกัน.

    ผลรวมทุก bucket ต้องเท่ากับ delta จริงเสมอ — ส่วนที่อธิบายไม่ได้ไปอยู่ 'other' อย่างเปิดเผย
    (breach penalty, การ clamp, ปัดเศษ) ไม่กลืนหายเพื่อให้ตัวเลขดูลงตัว.
    """
    total = float(cur["score"]) - float(prev["score"])
    buckets = _zero()

    if float(cur.get("max") or 0) != float(prev.get("max") or 0):
        # /8 (partial) เทียบกับ /11 คนละฐาน — เคสเดียวกับที่ changes.py กันไว้ไม่ให้แจ้ง health_jump
        buckets["other"] = total
        return {"total": round(total, 2), "buckets": buckets, "basis_changed": True,
                "notes": ["ฐานคะแนนเปลี่ยน (partial <-> เต็ม) เทียบตรงๆ ไม่ได้"]}

    business, f_data, notes = _fundamental_delta(prev["fundamental"], cur["fundamental"])
    price, estimate, v_data, v_notes = _valuation_delta(prev.get("valuation"), cur.get("valuation"))

    buckets["business"] = business
    buckets["data"] = f_data + v_data
    buckets["estimate"] = estimate
    buckets["price"] = price
    buckets["other"] = total - sum(buckets.values())

    return {
        "total": round(total, 2),
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "basis_changed": False,
        "notes": notes + v_notes,
    }


# ---------------------------------------------------------------- ด่าน 1: ความนิ่ง

def stability(snaps: list[dict]) -> dict | None:
    """ความนิ่งของคะแนนหุ้นตัวเดียวตลอดช่วงที่มีข้อมูล.

    วัดแบบ 'สะสมทีละคู่' (gross) ไม่ใช่เทียบหัวกับท้าย เพราะคะแนนที่วิ่งขึ้น 3 แล้วลงกลับ 3 คือ
    อาการไม่นิ่งที่รุนแรงที่สุด แต่หัว-ท้ายจะได้ 0 แล้วดูเหมือนนิ่งที่สุดในตาราง.
    """
    if len(snaps) < 2:
        return None

    gross = _zero()
    net = _zero()
    notes: list[str] = []
    basis_changes = 0

    for prev, cur in zip(snaps, snaps[1:]):
        a = attribute(prev["health"], cur["health"])
        if a["basis_changed"]:
            basis_changes += 1
        for b, v in a["buckets"].items():
            gross[b] += abs(v)
            net[b] += v
        for n in a["notes"]:
            line = f"{cur['date']}: {n}"
            if line not in notes:
                notes.append(line)

    scores = [s["score"] for s in snaps]
    unexplained = sum(gross[b] for b in BUCKETS if b not in EXPECTED_BUCKETS and b != "other")

    return {
        "ticker": snaps[0]["ticker"],
        "points": len(snaps),
        "from": snaps[0]["date"],
        "to": snaps[-1]["date"],
        "first_score": round(scores[0], 2),
        "last_score": round(scores[-1], 2),
        "max": snaps[-1]["max"],
        "low": round(min(scores), 2),
        "high": round(max(scores), 2),
        "swing": round(max(scores) - min(scores), 2),
        "gross": {k: round(v, 2) for k, v in gross.items()},
        "net": {k: round(v, 2) for k, v in net.items()},
        "unexplained": round(unexplained, 2),
        # การพลิกฐาน /8 <-> /11 ก็คือคะแนนไม่นิ่ง แม้ตัวเลข unexplained จะเป็น 0 (delta ทั้งก้อนไป
        # อยู่ 'other' เพราะแยก bucket ข้ามฐานไม่ได้) — MA แกว่ง 2 จุดด้วยเหตุนี้ล้วนๆ ถ้าไม่นับ
        # ตรงนี้ ตัวที่พลิกฐานบ่อยที่สุดจะกลายเป็นตัวที่ดู 'นิ่งที่สุด' ในตาราง
        "trustworthy": unexplained < NOISE_POINTS and basis_changes == 0,
        "basis_changes": basis_changes,
        "notes": notes[:6],
    }


def stability_report(by_ticker: dict[str, list[dict]] | None = None) -> dict:
    """ตารางความนิ่งทุกตัว เรียงตัวที่ขยับโดยอธิบายไม่ได้มากสุดขึ้นก่อน."""
    by_ticker = by_ticker if by_ticker is not None else snapshots()
    rows = [s for s in (stability(v) for v in by_ticker.values()) if s]
    rows.sort(key=lambda r: (-r["unexplained"], -r["basis_changes"]))

    flagged = [r for r in rows if not r["trustworthy"]]
    if not rows:
        headline = "ยังไม่มีหุ้นตัวไหนถูกวิเคราะห์ซ้ำมากพอจะดูความนิ่งได้ (ต้องมีอย่างน้อย 2 วัน)"
    elif not flagged:
        headline = f"คะแนนทั้ง {len(rows)} ตัวขยับจากธุรกิจ/ราคาเป็นหลัก — ยังไม่เจอสัญญาณว่าวัดข้อมูลตัวเอง"
    else:
        worst = flagged[0]
        why = (f"{worst['unexplained']:.1f} จุด" if worst["unexplained"] >= NOISE_POINTS
               else f"พลิกฐานคะแนน {worst['basis_changes']} ครั้ง")
        headline = (f"{len(flagged)} จาก {len(rows)} ตัว คะแนนขยับโดยไม่ได้มาจากธุรกิจหรือราคา "
                    f"— หนักสุดคือ {worst['ticker']} ({why})")

    return {"headline": headline, "flagged": len(flagged), "total": len(rows), "rows": rows}


# ---------------------------------------------------------------- ด่าน 2: ทำนายได้ไหม

def readiness(by_ticker: dict[str, list[dict]] | None = None, today: date | None = None) -> dict:
    """นับ snapshot ที่ 'แก่พอ' จะวัดผลล่วงหน้าได้จริงในแต่ละ horizon.

    เหตุผลที่ต้องมีฟังก์ชันนี้แยกออกมา: กับดักที่เจอง่ายที่สุดของ backtest คือเอาคะแนนทุกจุดมาจับคู่
    กับ 'ผลตอบแทนถึงวันนี้' ซึ่งจุดที่เพิ่งเกิดเมื่อวานจะได้ผลตอบแทน ~0 เสมอ แล้วสถิติจะถูกถ่วงเข้าหา
    ศูนย์จนสรุปว่า 'คะแนนไม่มีความหมาย' ทั้งที่จริงคือเรายังไม่ได้รอ.
    """
    by_ticker = by_ticker if by_ticker is not None else snapshots()
    today = today or date.today()
    all_snaps = [s for v in by_ticker.values() for s in v]
    oldest = min((s["date"] for s in all_snaps), default=None)

    horizons = []
    for h in HORIZONS:
        cutoff = today - timedelta(days=h)
        eligible = [s for s in all_snaps if date.fromisoformat(s["date"]) <= cutoff]
        wait = None
        if not eligible and oldest:
            wait = h - (today - date.fromisoformat(oldest)).days
        horizons.append({
            "days": h,
            "eligible": len(eligible),
            "ready": bool(eligible),
            "days_to_first": max(wait, 0) if wait is not None else None,
            "first_at": (date.fromisoformat(oldest) + timedelta(days=h)).isoformat() if oldest else None,
        })

    return {
        "oldest": oldest,
        "history_days": (today - date.fromisoformat(oldest)).days if oldest else 0,
        "snapshots": len(all_snaps),
        "horizons": horizons,
        "ready": any(h["ready"] for h in horizons),
    }


def _forward_return(prices: list[tuple[str, float]], start: str, horizon: int) -> float | None:
    """ผลตอบแทน % จากราคาปิดวันแรกที่ >= start ถึงวันแรกที่ >= start+horizon (None ถ้าข้อมูลไม่ถึง)."""
    end = (date.fromisoformat(start) + timedelta(days=horizon)).isoformat()
    p0 = next((v for d, v in prices if d >= start and v), None)
    p1 = next((v for d, v in prices if d >= end and v), None)
    if not p0 or not p1:
        return None
    return (p1 / p0 - 1) * 100


def forward_performance(by_ticker: dict[str, list[dict]], prices: dict[str, list[tuple[str, float]]],
                        benchmark: str = "VT", today: date | None = None) -> list[dict]:
    """จับคู่ snapshot กับผลตอบแทนล่วงหน้า แล้วแบ่งกลุ่มตามคะแนน ณ ตอนนั้น.

    วัดเป็น 'ส่วนต่างจาก benchmark' ไม่ใช่ผลตอบแทนดิบ เพราะตลาดขาขึ้นทำให้ทุกกลุ่มดูดีเท่ากันหมด
    ซึ่งตอบคำถาม 'คะแนนเราแยกของดีออกจากของไม่ดีได้ไหม' ไม่ได้เลย.
    """
    today = today or date.today()
    bench = prices.get(benchmark) or []
    out = []

    for h in HORIZONS:
        cutoff = today - timedelta(days=h)
        buckets: dict[str, list[float]] = {}
        for ticker, snaps in by_ticker.items():
            for s in snaps:
                if date.fromisoformat(s["date"]) > cutoff or s["max"] != 11.0:
                    continue        # ยังไม่ครบช่วง หรือ partial (/8) — คนละฐาน ห้ามปนกลุ่ม
                r = _forward_return(prices.get(ticker) or [], s["date"], h)
                b = _forward_return(bench, s["date"], h)
                if r is None or b is None:
                    continue
                buckets.setdefault(_band(s["score"]), []).append(r - b)

        rows = [{"band": b, "n": len(v), "excess": round(sum(v) / len(v), 2)}
                for b, v in sorted(buckets.items()) if v]
        out.append({"days": h, "bands": rows, "n": sum(r["n"] for r in rows)})
    return out


def _band(score: float) -> str:
    if score >= 9.0:
        return "9-11 (แข็งแรง)"
    if score >= 7.0:
        return "7-9 (ดี)"
    if score >= 5.0:
        return "5-7 (พอใช้)"
    return "0-5 (อ่อน)"


CAVEATS = [
    "snapshot ของหุ้นตัวเดียวกันหลายวันไม่ใช่ตัวอย่างอิสระต่อกัน — ช่วงเวลาทับกัน ค่าเฉลี่ยจึงมั่นใจได้น้อยกว่าที่ n บอก",
    "watchlist คัดมาแล้วตั้งแต่ต้น (ไม่มีตัวที่เราไม่สนใจ) ผลจึงบอกได้แค่ 'ในกลุ่มที่เราดูอยู่' ไม่ใช่ทั้งตลาด",
    "ผ่านด่านความนิ่งก่อนถึงจะอ่านด่านนี้ได้ — คะแนนที่ขยับเพราะข้อมูลฝั่งเรา ทำนายอะไรไม่ได้อยู่แล้ว",
]


def scorecard(rows: list[dict] | None = None, today: date | None = None) -> dict:
    """สมุดพกฉบับเต็ม (ที่ API/หน้าเว็บเรียก)."""
    by_ticker = snapshots(rows)
    ready = readiness(by_ticker, today)
    return {
        "stability": stability_report(by_ticker),
        "prediction": {**ready, "caveats": CAVEATS},
        "bucket_labels": BUCKET_LABELS,
        "noise_points": NOISE_POINTS,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":       # python -m src.agent.scorecard  -> ดูสมุดพกในเทอร์มินอล
    sc = scorecard()
    print(sc["stability"]["headline"], "\n")
    for r in sc["stability"]["rows"]:
        mark = "!" if not r["trustworthy"] else " "
        print(f"{mark} {r['ticker']:6} {r['first_score']:5.1f} -> {r['last_score']:5.1f}/{r['max']:.0f}"
              f"  swing {r['swing']:4.1f}  อธิบายไม่ได้ {r['unexplained']:4.1f}  ({r['points']} วัน)")
        for n in r["notes"]:
            print(f"      - {n}")
    p = sc["prediction"]
    print(f"\nประวัติ {p['history_days']} วัน / {p['snapshots']} จุด")
    for h in p["horizons"]:
        print(f"  {h['days']:3}d: " + (f"พร้อม {h['eligible']} จุด" if h["ready"]
              else f"ยังไม่พอ — รออีก {h['days_to_first']} วัน (ครบ {h['first_at']})"))