"""ตัวเลขที่หายๆ โผล่ๆ ข้ามวัน — ตัวจับ 'ข้อมูลไม่นิ่ง' ที่ต้นทาง (Phase 38).

ทำไมต้องมี: สมุดพก (Phase 32) บอกได้ว่า "ASML คะแนนขยับ 7 จุดเพราะข้อมูลฝั่งเรา" แต่บอกไม่ได้ว่า
*ตัวเลขไหน* — กว่าจะรู้ต้องนั่งไล่ facts ทีละวัน และกว่าจะเห็นก็สะสมมาหลายสัปดาห์แล้ว. ไฟล์นี้ตอบ
ตรงๆ ว่าอินพุตตัวไหนหายๆ โผล่ๆ อ่านจาก `analyses` ล้วน ไม่แตะเครือข่าย ไม่เรียก LLM

ประวัติของบั๊กชนิดนี้ในโปรเจกต์ (สามครั้งแล้ว ทุกครั้งใช้เวลาเป็นสัปดาห์กว่าจะเจอ):
  33.3  GOOGL: D&A หายบางรอบ -> sustainable growth คำนวณไม่ได้ -> lens สลับเงียบๆ
  33.3  `_first()` หยุดที่ชื่อแถวแรกที่ 'มีอยู่' แม้ช่องล่าสุดจะเป็น NaN
  38    ASML: yfinance เรียก CFO ว่า `Cash Flow From Continuing Operating Activities` บางรอบ
        -> เกณฑ์ #3 พลิกคำนวณได้/ไม่ได้ 6 ครั้งใน 17 วัน

**แยก "แกว่ง" ออกจาก "เปลี่ยนครั้งเดียว" คือหัวใจ** — ถ้านับทุกการเปลี่ยนแปลง รายงานจะเต็มไปด้วย
วันที่เราเพิ่ม/ตัด Fact ด้วยตัวเอง (Phase 17/18 เพิ่ม 10 ตัวรวด, Phase 33.2 ตัด P/S,P/B ของ ADR
ทิ้ง) ซึ่งไม่ใช่ข้อมูลไม่นิ่งเลย มันคือเราแก้โค้ด. ตัวเลขที่ **กลับมา** หลังจากหายไปแล้วเท่านั้นที่
เป็นอาการของแหล่งข้อมูลไม่นิ่ง — ของที่เราตัดทิ้งเองไม่เคยกลับมาเอง
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

# แกว่งกี่ครั้งขึ้นไปถึงจะรายงาน — 2 = 'หายแล้วกลับมา' อย่างน้อยหนึ่งรอบ (ต่ำกว่านี้คือเปลี่ยน
# ทางเดียว ซึ่งอธิบายได้ด้วยการที่เราเพิ่ม/ตัด Fact เอง)
MIN_FLIPS = 2

# ป้ายที่ 'ควร' เปลี่ยนตามงวด ไม่ใช่ความไม่นิ่ง — เก็บไว้ที่เดียวพร้อมเหตุผล
IGNORED_LABELS = {
    "FCF CAGR (long-run)",   # โผล่เมื่อประวัติ ก.ล.ต. ยาวพอ (Phase 36) = ตั้งใจให้เป็นแบบนั้น
}


# หน้าต่างเริ่มต้นของรายงานอัตโนมัติ (วัน) — ดูทั้งประวัติได้จาก CLI แต่ห้ามส่ง Discord แบบนั้น:
# รายการที่เคยเกิดจะค้างอยู่ในประวัติตลอดไป แล้วแจ้งเตือนเดิมจะถูกส่งซ้ำทุกวันจนไม่มีใครอ่าน
# (หลักเดียวกับ macro grace window และ METHOD_NOISE ของ scorecard)
DEFAULT_WINDOW_DAYS = 14


def _daily(rows: list[dict], since_days: int | None = None) -> dict[str, list[dict]]:
    """{ticker: [แถวเรียงตามวัน]} 1 จุด/วัน (รอบล่าสุดของวัน) — เกณฑ์เดียวกับ scorecard.snapshots
    เพราะการรันมือซ้ำในวันเดียวไม่ใช่ 'ข้อมูลเปลี่ยนข้ามวัน'.

    หน้าต่างวัดจาก **รอบล่าสุดที่มีในข้อมูล** ไม่ใช่ date.today() — รอบ CI ตกบ้าง ข้อมูลจึงตาม
    หลังปฏิทินได้หลายวัน ถ้าอิงนาฬิกา รายงานจะกลายเป็นว่างเปล่าในวันที่ CI ไม่ได้รัน ซึ่งอ่านผิด
    เป็น 'ทุกอย่างนิ่งดี' พอดี
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        run_at = r.get("run_at") or ""
        if run_at:
            by_day[r["ticker"]][run_at[:10]] = r

    if since_days is not None:
        newest = max((d for days in by_day.values() for d in days), default=None)
        if newest:
            cutoff = (date.fromisoformat(newest) - timedelta(days=since_days)).isoformat()
            by_day = {t: {d: r for d, r in days.items() if d >= cutoff}
                      for t, days in by_day.items()}

    return {t: [days[d] for d in sorted(days)] for t, days in by_day.items() if days}


def _score_shape(row: dict) -> tuple:
    """ลายเซ็นของ 'คะแนนถูกประกอบขึ้นมาแบบไหน' ในรอบนั้น — ใช้ดูว่าตัวเลขที่หายไหลถึงคะแนนไหม.

    ต้องดูสามอย่าง ไม่ใช่แค่จำนวนเกณฑ์ที่คำนวณได้: Market Cap หายไม่ได้ทำให้เกณฑ์พื้นฐานข้อไหน
    หายเลย (มันเป็นอินพุตของขาราคา) แต่มันทำให้ทั้งแถวร่วงไปเป็น partial /8 — ซึ่งคือสิ่งที่ทำให้
    MA แกว่ง 2 จุดใน Phase 32 โดยไม่มีใครอธิบายได้. ตัววัดที่มองไม่เห็นเคสนั้นคือตัววัดที่พลาด
    เคสที่แพงที่สุด
    """
    h = row.get("health") or {}
    return (
        (h.get("fundamental") or {}).get("computable"),
        h.get("max"),
        (h.get("valuation") or {}).get("score") is not None,
    )


def check_one(ticker: str, snaps: list[dict]) -> list[dict]:
    """[{label, flips, missing_days, total_days, events, score_impact}] ของหุ้นตัวเดียว.

    `score_impact` = จำนวนครั้งที่วิธีประกอบคะแนนขยับพร้อมกับตัวเลขนี้หาย/กลับมา — ตัวชี้ว่า
    การหายของมันไหลไปถึงคะแนนจริงหรือแค่หายจาก DATA เฉยๆ (สองอย่างนี้ไม่เท่ากัน)
    """
    if len(snaps) < 2:
        return []

    present: dict[str, list[bool]] = defaultdict(list)
    labels_seen: set[str] = set()
    for r in snaps:
        here = {f["label"] for f in (r.get("facts") or [])}
        labels_seen |= here
    for r in snaps:
        here = {f["label"] for f in (r.get("facts") or [])}
        for label in labels_seen:
            present[label].append(label in here)

    out = []
    for label in sorted(labels_seen):
        if label in IGNORED_LABELS:
            continue
        seq = present[label]
        flips = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        if flips < MIN_FLIPS:
            continue

        events, impact = [], 0
        for i, (a, b) in enumerate(zip(seq, seq[1:]), start=1):
            if a == b:
                continue
            day = (snaps[i].get("run_at") or "")[:10]
            events.append(f"{day} {'กลับมา' if b else 'หาย'}")
            before, after = _score_shape(snaps[i - 1]), _score_shape(snaps[i])
            if any(v is not None for v in before) and before != after:
                impact += 1

        out.append({
            "ticker": ticker,
            "label": label,
            "flips": flips,
            "missing_days": sum(1 for v in seq if not v),
            "total_days": len(seq),
            "events": events,
            "score_impact": impact,
        })
    return sorted(out, key=lambda r: (-r["score_impact"], -r["flips"]))


def check_many(rows: list[dict], since_days: int | None = None) -> list[dict]:
    """ทุก ticker เรียงตัวที่กระทบคะแนนมากสุดขึ้นก่อน. since_days=None = ดูทั้งประวัติ (CLI)."""
    found = [r for t, snaps in _daily(rows, since_days).items() for r in check_one(t, snaps)]
    return sorted(found, key=lambda r: (-r["score_impact"], -r["flips"], r["ticker"]))


def render_text(found: list[dict], limit: int = 15) -> str:
    if not found:
        return "ไม่พบตัวเลขที่หายๆ โผล่ๆ — อินพุตนิ่งทุกตัวในช่วงที่มีข้อมูล"

    hot = [r for r in found if r["score_impact"]]
    head = (f"{len(found)} ตัวเลขหายๆ โผล่ๆ ข้ามวัน — {len(hot)} ตัวลากคะแนนไปด้วย"
            if hot else f"{len(found)} ตัวเลขหายๆ โผล่ๆ ข้ามวัน (ยังไม่กระทบเกณฑ์ข้อไหน)")
    lines = [head, ""]
    for r in found[:limit]:
        mark = "!" if r["score_impact"] else " "
        lines.append(f"{mark} {r['ticker']:6} {r['label']:26} หาย {r['missing_days']}/{r['total_days']} วัน"
                     f"  พลิก {r['flips']}x"
                     + (f"  กระทบคะแนน {r['score_impact']}x" if r["score_impact"] else ""))
        lines.append("      " + ", ".join(r["events"][:5]))
    if len(found) > limit:
        lines.append(f"  ... อีก {len(found) - limit} รายการ")
    return "\n".join(lines)


if __name__ == "__main__":       # python -m src.evals.check_fact_stability
    from src.history.store import all_rows

    print(render_text(check_many(all_rows())))
