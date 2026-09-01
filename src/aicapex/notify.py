"""ยิงรายงาน AI-capex เข้า Discord — แพตเทิร์นเดียวกับ src/macro/notify.py.

ช่อง: DISCORD_WEBHOOK_URL_AICAPEX (แนะนำแยกช่อง — คนละ cadence คนละหัวข้อกับรายงานหุ้นรายวัน)
      -> fallback DISCORD_WEBHOOK_URL -> ไม่ตั้งเลยก็ข้ามเงียบๆ ไม่พัง

**หลักการเขียนข้อความ:** พาดหัวคือ "วันนี้อะไรเปลี่ยน" ไม่ใช่ "สถานะทั้งหมด" — เพราะรายงาน
รายวันที่ทวนของเดิมทุกวันจะถูกเลื่อนผ่านภายในสัปดาห์เดียว แล้ววันที่มีของจริงก็จะถูกเลื่อนผ่าน
ไปด้วย (หลักเดียวกับที่โปรเจกต์นี้ตัด sentiment ออกจากคะแนน: ของที่ขยับทุกวันไม่ใช่สัญญาณ)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from src.aicapex import radar, store
from src.notify.discord import post_chunks

load_dotenv(Path(__file__).parents[2] / ".env")

_ICON = {"alert": "🔴", "watch": "🟡", "ok": "🟢", "unknown": "⚪"}
_WORD = {"alert": "เป็นจริงแล้ว", "watch": "ต้องจับตา", "ok": "ยังปกติ", "unknown": "วัดไม่ได้"}


def _webhook() -> str | None:
    return os.environ.get("DISCORD_WEBHOOK_URL_AICAPEX") or os.environ.get("DISCORD_WEBHOOK_URL")


def _fmt_value(s) -> str:
    if s.value is None:
        return "—"
    return f"{s.value:g} {s.unit}".strip()


def format_report(report: radar.Report, db_path: Path | None = None) -> str:
    """ข้อความ Discord หนึ่งฉบับ (markdown). ยาวได้ — post_chunks แบ่งให้เอง"""
    icon = _ICON[report.overall]
    lines = [f"{icon} **เรดาร์ห่วงโซ่การเงิน AI** — {report.run_at[:10]}",
             f"_{report.summary_line()}_", ""]

    # ── พาดหัว: อะไรเปลี่ยน ──────────────────────────────────────────────
    if report.first_run:
        lines += ["**รอบแรก** — ยังไม่มีของเมื่อวานให้เทียบ "
                  "(เงียบรอบนี้ไม่ได้แปลว่านิ่ง แปลว่ายังไม่รู้)", ""]
    elif report.changes:
        lines.append("**เปลี่ยนจากรอบก่อน**")
        for c in report.changes:
            arrow = "แย่ลง" if c.worsened else "ดีขึ้น"
            lines.append(f"{_ICON[c.after]} {c.label}: {_WORD[c.before]} → "
                         f"**{_WORD[c.after]}** ({arrow})")
        lines.append("")
    else:
        lines += ["**ไม่มีเงื่อนไขไหนเปลี่ยนสถานะจากรอบก่อน**", ""]

    # ── เงื่อนไขที่เป็นจริงแล้ว ────────────────────────────────────────────
    if report.triggered:
        lines.append("**เงื่อนไขที่เป็นจริงอยู่ตอนนี้**")
        for s in report.triggered:
            days = store.days_in_state(s.key, s.state, db_path=db_path)
            age = f" · เป็นแบบนี้มา {days} วัน" if days else ""
            close = " · **เฉียดเส้น**" if s.borderline else ""
            lines.append(f"{_ICON[s.state]} **{s.label}** — {_fmt_value(s)} "
                         f"(เส้นที่ {s.watch_at:g}){age}{close}")
            lines.append(f"    {s.detail}")
        lines.append("")

    ok = [s for s in report.signals if s.state == "ok"]
    if ok:
        lines.append("🟢 **ยังปกติ:** " + " · ".join(f"{s.label} ({_fmt_value(s)})" for s in ok))
        lines.append("")

    unknown = [s for s in report.signals if s.state == "unknown"]
    if unknown:
        lines.append("⚪ **วัดไม่ได้รอบนี้:** "
                     + " · ".join(f"{s.label} ({s.missing or 'ไม่ทราบสาเหตุ'})" for s in unknown))
        lines.append("")

    # ── มุมอับ: ติดไปกับทุกฉบับ ไม่ใช่เชิงอรรถ ────────────────────────────
    lines.append("**สิ่งที่เรดาร์นี้มองไม่เห็น** (ไม่ใช่ว่าไม่มี — แต่วัดไม่ได้)")
    lines += [f"• {b}" for b in radar.BLIND_SPOTS]
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
