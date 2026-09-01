"""ยิงรายงาน AI-capex เข้า Discord — แพตเทิร์นเดียวกับ src/macro/notify.py.

ช่อง: DISCORD_WEBHOOK_URL_AICAPEX (แนะนำแยกช่อง — คนละ cadence คนละหัวข้อกับรายงานหุ้นรายวัน)
      -> fallback DISCORD_WEBHOOK_URL -> ไม่ตั้งเลยก็ข้ามเงียบๆ ไม่พัง

**หลักการเขียนข้อความ** (แก้ 2026-09 หลังอ่านฉบับแรกแล้วพบว่า "อ่านลำบาก ไม่จูงใจ"):

1. *บอกว่าให้คิดอะไร ก่อนบอกตัวเลข* — ฉบับแรกเปิดด้วยรายการ 7 ข้อน้ำหนักเท่ากันหมด
   คนอ่านต้องประกอบข้อสรุปเอง ซึ่งแปลว่าส่วนใหญ่จะไม่ประกอบ. ตอนนี้บรรทัดที่สองคือ
   ข้อสรุปเดียวที่สำคัญที่สุดของวันนั้น
2. *เห็นก่อนอ่าน* — แถบ 🔴🔴🔴🔴🔴🟢🟢 อ่านได้ใน 0.2 วินาที ส่วน "5 ใน 7" ต้องแปลก่อน
3. *เรื่องเล่า ไม่ใช่ checklist* — จัดเป็น 4 บท (ลูกหนี้ -> ตลาดหุ้น -> เจ้าหนี้ -> ความต้องการ)
   เรียงตามลำดับที่ความเสียหายจะเดินจริง
4. *ไม่ใช้หน่วยของเครื่องมือ* — "(เส้นที่ 2)" ไม่มีความหมายกับคนอ่าน เปลี่ยนเป็น
   "ห่างเส้น 4.5" หรือ "เกินเส้นมา 2.2" ซึ่งบอกได้ทันทีว่าเฉียดหรือขาดลอย
   (กฎเดียวกับที่เจ้าของตั้งไว้ตั้งแต่ Phase 43: ห้ามใช้หน่วยเครื่องมือในรายงาน)
5. *มุมอับย่อรายวัน เต็มสัปดาห์ละครั้ง* — 5 บรรทัดเดิมทุกวันคือตัวที่ฝึกให้คนเลื่อนผ่าน
   แต่ตัดทิ้งไม่ได้เพราะเป็นส่วนหนึ่งของความซื่อสัตย์ จึงย่อเหลือบรรทัดเดียว แล้วกางเต็ม
   ทุกวันจันทร์ (และทุกครั้งที่มีสถานะเปลี่ยน ซึ่งเป็นวันที่คนจะอ่านจริง)
"""
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from src.aicapex import radar, signals as sig, store
from src.notify.discord import post_chunks

load_dotenv(Path(__file__).parents[2] / ".env")

_ICON = {"alert": "🔴", "watch": "🟡", "ok": "🟢", "unknown": "⚪"}
_WORD = {"alert": "เป็นจริงแล้ว", "watch": "ต้องจับตา", "ok": "ยังปกติ", "unknown": "วัดไม่ได้"}
_TH_MONTH = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
             "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")


def _webhook() -> str | None:
    return os.environ.get("DISCORD_WEBHOOK_URL_AICAPEX") or os.environ.get("DISCORD_WEBHOOK_URL")


def _thai_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {_TH_MONTH[d.month - 1]}"


def _value(s) -> str:
    if s.value is None:
        return "—"
    return f"{s.value:g} {s.unit}".strip()


def _distance(s) -> str:
    """ห่างเส้นแค่ไหน ในภาษาที่ไม่ต้องรู้ว่า 'เส้น' คือเลขอะไร.

    บอกระยะแทนที่จะบอกค่าเกณฑ์ เพราะคนอ่านไม่ได้อยากรู้ว่าเราตั้งเส้นไว้ที่เท่าไร
    เขาอยากรู้ว่า 'ใกล้พังหรือยัง' ซึ่งเป็นคนละคำถาม"""
    m = s.margin
    if m is None:
        return ""
    # สัญญาณที่นับเป็น "ราย" ไม่มีระยะทางที่มีความหมาย — บริษัทเป็นจำนวนเต็ม จะ "เกินเส้นมา
    # 1.5 ราย" ไม่ได้ และ "เกินเส้นมา 1" ก็ไม่ได้บอกอะไรที่บรรทัดรายละเอียดไม่ได้บอกแล้ว
    if s.unit == "ราย":
        return ""
    if s.borderline:
        return "**เฉียดเส้นมาก**"
    return f"เกินเส้นมา {m:g}" if m > 0 else f"ห่างเส้น {abs(m):g}"


def _gauge(signals) -> str:
    """แถบสถานะที่อ่านได้ก่อนสมองเริ่มอ่านหนังสือ — เรียงแย่ไปดี ไม่เรียงตามลำดับสัญญาณ
    เพราะกลุ่มสีที่ติดกันอ่านง่ายกว่าสีสลับ"""
    order = {"alert": 0, "watch": 1, "unknown": 2, "ok": 3}
    return "".join(_ICON[s.state] for s in sorted(signals, key=lambda x: order[x.state]))


def _headline(report) -> list[str]:
    """ข้อสรุปเดียวที่สำคัญที่สุดของวันนี้ — วางไว้บนสุดเพราะถ้าคนอ่านบรรทัดเดียว
    ต้องเป็นบรรทัดนี้ ไม่ใช่ตัวเลขข้อแรกที่บังเอิญอยู่บนสุดของรายการ"""
    decisive = next((s for s in report.signals if s.key == sig.DECISIVE), None)
    if decisive is None:
        return []

    if decisive.state == "ok":
        return [f"> ⭐ **ตัวชี้ขาดยังเขียว** — {decisive.label} {_value(decisive)} "
                f"({_distance(decisive)})",
                f"> {sig.DECISIVE_WHY}"]

    # วัดไม่ได้ ≠ พลิกแล้ว. เจอบั๊กนี้จากเทสต์ (2026-09): เดิมเขียน if ok -> เขียว, else ->
    # "🚨 พลิกแล้ว" ซึ่งแปลว่าวันไหน yfinance คืนราคา HYG/LQD ไม่ได้ พาดหัวจะขึ้นสัญญาณ
    # เตือนแดงเต็มจอทั้งที่ไม่มีอะไรเกิดขึ้น — สัญญาณเตือนเท็จบนบรรทัดที่สำคัญที่สุดของรายงาน
    # คือวิธีที่เร็วที่สุดที่จะทำให้คนเลิกเชื่อทั้งฉบับ
    if decisive.state == "unknown":
        return [f"> ⚪ **ตัวชี้ขาดวัดไม่ได้รอบนี้** — {decisive.label}",
                f"> {decisive.missing or 'ไม่ทราบสาเหตุ'} · "
                f"ไม่ใช่ 'ยังปลอดภัย' แต่คือ 'ไม่รู้' ซึ่งแย่กว่าในแง่การตัดสินใจ"]

    return [f"> 🚨 **ตัวชี้ขาดพลิกแล้ว** — {decisive.label} {_value(decisive)} "
            f"({_distance(decisive)})",
            f"> {sig.DECISIVE_WHY} — ข้อนี้เปลี่ยนสถานะ แปลว่าเรื่องเดินจาก "
            f"'น่ากังวลบนกระดาษ' ไปอีกขั้น"]


def format_report(report: radar.Report, db_path: Path | None = None,
                  today: date | None = None) -> str:
    """ข้อความ Discord หนึ่งฉบับ (markdown). ยาวได้ — post_chunks แบ่งให้เอง"""
    today = today or date.today()
    n_true = sum(1 for s in report.signals if s.state in ("alert", "watch"))

    lines = [f"{_ICON[report.overall]} **เรดาร์ห่วงโซ่การเงิน AI** · {_thai_date(report.run_at)}",
             f"**{_gauge(report.signals)}  {n_true} ใน {len(report.signals)} เงื่อนไขเป็นจริง**",
             ""]

    # ── สิ่งที่ต้องคิด มาก่อนสิ่งที่ต้องอ่าน ─────────────────────────────
    lines += _headline(report)
    lines.append("")

    # ── อะไรเปลี่ยน ────────────────────────────────────────────────────
    if report.first_run:
        lines += ["▸ **รอบแรก** — ยังไม่มีของเมื่อวานให้เทียบ "
                  "(เงียบไม่ได้แปลว่านิ่ง แปลว่ายังไม่รู้)", ""]
    elif report.changes:
        for c in report.changes:
            lines.append(f"▸ **เปลี่ยน:** {c.label} · {_WORD[c.before]} → "
                         f"**{_WORD[c.after]}** {'📉 แย่ลง' if c.worsened else '📈 ดีขึ้น'}")
        lines.append("")
    else:
        lines += ["▸ ไม่มีข้อไหนเปลี่ยนสถานะจากรอบก่อน", ""]

    # ── 4 บท เรียงตามลำดับที่ความเสียหายจะเดินจริง ──────────────────────
    by_chapter: dict[str, list] = {}
    for s in report.signals:
        by_chapter.setdefault(sig.CHAPTER_OF.get(s.key, "borrower"), []).append(s)

    for idx, (key, title) in enumerate(sig.CHAPTERS, start=1):
        members = by_chapter.get(key, [])
        if not members:
            continue
        hit = sum(1 for s in members if s.state in ("alert", "watch"))
        star = " ⭐" if any(s.key == sig.DECISIVE for s in members) else ""
        lines.append(f"**{idx}. {title} — {hit}/{len(members)} ติด**{star}")
        for s in members:
            days = store.days_in_state(s.key, s.state, db_path=db_path)
            age = f" · {days} วัน" if days else ""
            dist = _distance(s)
            meta = " · ".join(x for x in (dist, age.lstrip(" ·")) if x)
            lines.append(f"{_ICON[s.state]} {s.label} · **{_value(s)}**"
                         + (f"  ({meta})" if meta else ""))
            lines.append(f"　　{s.missing or s.detail}")
        lines.append("")

    # ── มุมอับ: ย่อรายวัน กางเต็มวันจันทร์และวันที่มีอะไรเปลี่ยน ─────────
    expand = today.weekday() == 0 or bool(report.changes) or report.first_run
    if expand:
        lines.append("**สิ่งที่เรดาร์นี้มองไม่เห็น** (ไม่ใช่ว่าไม่มี — แต่วัดไม่ได้)")
        lines += [f"• {b}" for b in radar.BLIND_SPOTS]
    else:
        lines.append(f"_มองไม่เห็น {len(radar.BLIND_SPOTS)} อย่าง "
                     f"(ค่าเช่า GPU, utilization, การต่อสัญญา…) — กางเต็มทุกวันจันทร์_")

    lines += ["", "_นับเงื่อนไขที่ตรวจสอบได้ ไม่ได้ทำนายว่าจะแตกเมื่อไหร่ "
                  "และไม่ใช่คำแนะนำให้ซื้อ/ขาย_"]
    return "\n".join(lines)


def send_aicapex_report(webhook_url: str | None = None, only_on_change: bool = False) -> bool:
    """รันเรดาร์ -> โพสต์ Discord. คืน True ถ้าส่งสำเร็จ.

    only_on_change=True: เงียบสนิทถ้าไม่มีเงื่อนไขไหนเปลี่ยนสถานะ — เผื่อวันไหนอยากลด
    ความถี่ลงโดยไม่ต้องแก้ workflow (ค่าเริ่มต้นคือส่งทุกวันตามที่ตั้งใจไว้)"""
    report = radar.scan()
    if only_on_change and not report.changes and not report.first_run:
        print("[aicapex] ไม่มีอะไรเปลี่ยน — ข้ามการส่ง (only_on_change)")
        return False
    return post_chunks(format_report(report), webhook_url or _webhook())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(radar.build_report()))
