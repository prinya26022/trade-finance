"""สร้าง report จากผลที่เก็บไว้ แล้วส่งเข้า Discord — 4 โหมด ตามความถี่ที่เหมาะกับข้อมูลแต่ละแบบ.

- baseline (แทรกอัตโนมัติ) : ภาพเต็มของ ticker ที่เพิ่งวิเคราะห์ครั้งแรก (ยังไม่มีอะไรให้เทียบ)
- daily   : alert-first — เฉพาะสิ่งที่เปลี่ยนตั้งแต่ครั้งก่อน (ค่าเริ่มต้นของ scheduled run รายวัน)
- weekly  : สิ่งที่เปลี่ยนสะสม 7 วัน + สถานะย่อทุกตัว (ทุกวันจันทร์)
- monthly : ทบทวน thesis เต็มรูปแบบทุกตัว + สิ่งที่เปลี่ยนสะสม 30 วัน (วันที่ 1 ของเดือน)

หลักสำคัญ: การ 'วิเคราะห์' (เรียก Gemini) รันรายวันเท่านั้น — โหมดรายงานเป็นแค่มุมมองของ
ข้อมูลที่เก็บไว้แล้ว จึงไม่กินโควตาเพิ่มไม่ว่าจะเลือกโหมดไหน หรือส่งซ้ำกี่ครั้งก็ได้.
เรียก build_report(mode=...) ตรงๆ เพื่อทดสอบ/บังคับโหมด, หรือปล่อย None ให้ pick_mode()
เลือกจากวันที่ปัจจุบัน (ใช้ตอน scheduled run จริงผ่าน send_report()).

แยกอีกช่องหนึ่ง: build_quality_report()/send_quality_report() — คนละหัวข้อกับข้างบน (นั่นคือ
"ระบบคำนวณของเราเองยังแม่นอยู่ไหม" ไม่ใช่ "หุ้นตัวนี้น่าสนใจไหม") จึงส่งไปช่อง Discord แยก
(DISCORD_WEBHOOK_URL_QUALITY) ไม่ปนกับ report หลัก.
"""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.history.store import latest_per_ticker, history
from src.agent.changes import detect_changes, changes_over_window
from src.watchlist.store import list_all
from src.notify.discord import post_chunks

load_dotenv(Path(__file__).parents[2] / ".env")   # ให้ DISCORD_WEBHOOK_URL พร้อมใช้

STRENGTH_EMOJI = {"strong": "🟢", "mixed": "🟡", "weak": "🔴"}
SEVERITY_EMOJI = {"alert": "🔴", "warn": "🟠", "info": "🔵"}
WINDOW_DAYS = {"daily": None, "weekly": 7, "monthly": 30}   # None = เทียบแค่คู่ล่าสุด
EXTRACTION_WARN_THRESHOLD = 0.8   # ต่ำกว่านี้ = การคำนวณของเราเองน่าสงสัย ควรเปิดดู debug tool
TITLE = {
    "daily": "📊 Daily Watchlist Report",
    "weekly": "📅 Weekly Watchlist Report",
    "monthly": "🗓️ Monthly Thesis Review",
}


def pick_mode(today: date | None = None) -> str:
    """เลือกโหมดจากวันที่ (ใช้ตอน scheduled run รายวัน):
    วันที่ 1 ของเดือน -> monthly, วันจันทร์ -> weekly, วันอื่นๆ -> daily."""
    d = today or date.today()
    if d.day == 1:
        return "monthly"
    if d.weekday() == 0:   # Monday
        return "weekly"
    return "daily"


def _status_line(a: dict) -> str:
    s = a["summary"]
    em = STRENGTH_EMOJI.get(s["fundamental_strength"], "⚪")
    return f"{em} `{a['ticker']:<5}` {s['fundamental_strength']} / {s['valuation_view']}"


def _full_picture(a: dict, header_prefix: str = "") -> list[str]:
    """ภาพเต็มของ ticker หนึ่ง: verdict + beginner_summary + จุดอ่อนเด่น 2 อันดับแรก.
    ใช้ทั้งกับ (ก) baseline ตอนวิเคราะห์ครั้งแรก และ (ข) monthly thesis review — โครงเดียวกัน
    เพราะทั้งคู่ต้องการ 'สรุปทั้งภาพ' ไม่ใช่แค่ diff."""
    s = a["summary"]
    em = STRENGTH_EMOJI.get(s["fundamental_strength"], "⚪")
    lines = [f"{header_prefix}**{a['ticker']}**  {em} {s['fundamental_strength']} / {s['valuation_view']}"]
    if s.get("beginner_summary"):
        lines.append(s["beginner_summary"])
    for w in s.get("weak_points", [])[:2]:
        lines.append(f"  ⚠️ [{w['area']}] {w['detail']}")
    return lines


def _is_first_run(ticker: str) -> bool:
    """True ถ้านี่คือผลวิเคราะห์ครั้งแรกของ ticker นี้ (ยังไม่มีของก่อนหน้าให้เทียบ)."""
    return len(history(ticker, limit=2)) == 1


BREACH_TYPES = {"invalidation", "no_margin_safety"}   # เงื่อนไขออก/มูลค่า ที่ผู้ใช้ตั้งเอง (ด่าน 4)


def _gather_changes(tickers: list[str], window_days: int | None) -> dict[str, list[dict]]:
    """คืน {ticker: [changes]} — window_days=None ใช้คู่ล่าสุด (daily), ใส่เลข = สะสมทั้งช่วง."""
    out: dict[str, list[dict]] = {}
    for tk in tickers:
        changes = (
            detect_changes(tk)["changes"] if window_days is None else changes_over_window(tk, window_days)
        )
        if changes:
            out[tk] = changes
    return out


def build_report(mode: str | None = None, dashboard_url: str = "http://localhost:3000") -> str:
    mode = mode or pick_mode()
    analyses = latest_per_ticker()
    analyzed = {a["ticker"] for a in analyses}
    newcomers = [a for a in analyses if _is_first_run(a["ticker"])]
    veterans = [a for a in analyses if a["ticker"] not in {n["ticker"] for n in newcomers}]

    lines = [f"**{TITLE[mode]} — {date.today().isoformat()}**", ""]

    # (0) ตัวที่เพิ่งวิเคราะห์ครั้งแรก -> baseline เต็ม (ทุกโหมด เพราะยังไม่มีอะไรให้เทียบ)
    if newcomers:
        lines.append("🆕 **เริ่มติดตามใหม่**")
        for a in newcomers:
            lines += _full_picture(a)
        lines.append("")

    # (1) สิ่งที่เปลี่ยน — เฉพาะตัวที่มีประวัติให้เทียบ (veterans)
    if veterans:
        changes_by_ticker = _gather_changes([a["ticker"] for a in veterans], WINDOW_DAYS[mode])
        assessment_by_ticker = {a["ticker"]: a["summary"].get("thesis_assessment", "") for a in veterans}

        # (1a) THESIS พัง — เงื่อนไขออกที่ผู้ใช้ตั้งเองโดนแตะ (สำคัญสุด อยู่บนสุด) + LLM ว่ายัง support ไหม
        breach_lines: list[str] = []
        for tk, changes in changes_by_ticker.items():
            breaches = [c for c in changes if c["type"] in BREACH_TYPES]
            if not breaches:
                continue
            breach_lines.append(f"🔴 **{tk}**")
            for c in breaches:
                breach_lines.append(f"   • {c['detail']}")
            if assessment_by_ticker.get(tk):
                breach_lines.append(f"   🤖 {assessment_by_ticker[tk]}")
        if breach_lines:
            lines.append("🚨 **THESIS พัง — เงื่อนไขออกของคุณโดนแตะ**")
            lines += breach_lines
            lines.append("")

        # (1b) การเปลี่ยนแปลงอื่น ๆ (ไม่ใช่ breach)
        other_lines: list[str] = []
        for tk, changes in changes_by_ticker.items():
            for c in changes:
                if c["type"] in BREACH_TYPES:
                    continue
                em = SEVERITY_EMOJI.get(c["severity"], "•")
                other_lines.append(f"{em} **{tk}** — {c['detail']}")
        if other_lines:
            lines.append("⚠️ **เปลี่ยนแปลงที่ต้องดู**")
            lines += other_lines
            lines.append("")
        elif not breach_lines:
            lines.append("✅ ไม่มีการเปลี่ยนแปลงที่แตะ thesis ในช่วงนี้")
            lines.append("")

    # (2) เนื้อหาหลักตามโหมด
    if mode == "monthly":
        lines.append("**ทบทวน Thesis รายตัว**")   # monthly = ภาพเต็มทุกตัว ไม่ใช่แค่บรรทัดเดียว
        for a in veterans:
            lines += _full_picture(a)
    else:
        lines.append("**สถานะพื้นฐาน**")           # daily/weekly = สถานะย่อพอ
        for a in veterans:
            lines.append(_status_line(a))

    # (3) ตัวที่ยังไม่เคยถูกวิเคราะห์เลย (เพิ่งเพิ่มผ่าน UI แต่ยัง pending)
    pending = [r["ticker"] for r in list_all() if r["ticker"] not in analyzed]
    if pending:
        lines.append("")
        lines.append("⏳ รอวิเคราะห์: " + ", ".join(pending))

    lines.append("")
    lines.append(f"🔎 รายละเอียด/tooltip: {dashboard_url}")
    return "\n".join(lines)


def send_report(mode: str | None = None) -> bool:
    """สร้าง report (auto เลือกโหมดจากวันที่ถ้าไม่ระบุ mode) แล้วส่งเข้า Discord.
    ใช้ post_chunks กัน monthly report ยาวเกิน 2000 ตัวอักษรแล้วโดนตัดทอนเงียบๆ."""
    return post_chunks(build_report(mode))


# ─────────────────────────────────────────────────────────────────────────────
# Quality report (Phase 4) — คนละหัวข้อกับ daily/weekly/monthly ข้างบน (นั่นคือ
# "หุ้นตัวนี้น่าสนใจไหม", อันนี้คือ "ระบบคำนวณของเราเองยังทำงานถูกไหม") จึงแยกส่งไปช่อง
# Discord อื่น (DISCORD_WEBHOOK_URL_QUALITY) ไม่ปนกับ report หลัก
# ─────────────────────────────────────────────────────────────────────────────
def build_quality_report(threshold: float = EXTRACTION_WARN_THRESHOLD) -> str | None:
    """สรุป ticker ที่ extraction accuracy ต่ำกว่าเกณฑ์ — alert-only เหมือน daily report:
    คืน None ถ้าทุกตัวปกติ (เงียบไว้ ไม่ใช่ error ไม่ต้องส่งอะไร)."""
    flagged = []
    for a in latest_per_ticker():
        extraction = a.get("extraction")
        if not extraction or extraction.get("accuracy") is None:
            continue
        acc = extraction["accuracy"]
        if acc < threshold:
            mismatches = [c for c in extraction["checks"] if not c["within_tolerance"]]
            detail = "; ".join(
                f"{c['metric']} ours={c['ours']:.2f} vs yfinance={c['reference']:.2f}"
                for c in mismatches
            )
            flagged.append(f"🔴 **{a['ticker']}** — extraction accuracy {acc:.0%} ({detail})")

    if not flagged:
        return None   # ไม่มีอะไรผิดปกติ = ไม่ต้องส่ง (เงียบตามหลัก alert-only)

    lines = [f"🔬 **Extraction Accuracy Alert — {date.today().isoformat()}**", ""]
    lines += flagged
    lines.append("")
    lines.append("ตรวจสอบเพิ่ม: `python -m src.providers.stock.fundamentals <TICKER>`")
    return "\n".join(lines)


def send_quality_report() -> bool:
    """ส่ง quality alert เข้าช่อง Discord แยก (DISCORD_WEBHOOK_URL_QUALITY).
    ไม่มีอะไรผิดปกติ หรือไม่ได้ตั้ง webhook นี้ไว้ -> ข้ามเงียบๆ (ไม่ถือว่า fail)."""
    report = build_quality_report()
    if report is None:
        return True
    webhook = os.environ.get("DISCORD_WEBHOOK_URL_QUALITY")
    if not webhook:
        print("[quality-report] ไม่มี DISCORD_WEBHOOK_URL_QUALITY — ข้ามการส่ง")
        return False
    return post_chunks(report, webhook_url=webhook)


if __name__ == "__main__":
    # ทดสอบ:  python -m src.agent.report --mode weekly   |   python -m src.agent.report --quality
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--quality":
        ok = send_quality_report()
        print("quality report:", "sent" if ok else "skipped/failed")
    else:
        forced_mode = sys.argv[2] if len(sys.argv) > 1 and sys.argv[1] == "--mode" else None
        send_report(forced_mode)
