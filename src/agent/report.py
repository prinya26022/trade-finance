"""สร้าง 'daily report' จากผลที่เก็บไว้ แล้วส่งเข้า Discord.

ปรัชญา alert-first: นำด้วย 'สิ่งที่เปลี่ยนแตะ thesis' (สิ่งที่ต้องดู) ก่อน
ตามด้วยสถานะพื้นฐานย่อๆ — Discord ไว้ push เมื่อสำคัญ, เว็บไว้เปิดดูละเอียด/tooltip.
อ่านจาก history store ล้วนๆ (ไม่เรียก LLM) จึงส่งซ้ำได้แม้วันที่ quota หมด.
"""
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.history.store import latest_per_ticker
from src.agent.changes import detect_changes
from src.watchlist.store import list_all
from src.notify.discord import post

load_dotenv(Path(__file__).parents[2] / ".env")   # ให้ DISCORD_WEBHOOK_URL พร้อมใช้

STRENGTH_EMOJI = {"strong": "🟢", "mixed": "🟡", "weak": "🔴"}
SEVERITY_EMOJI = {"alert": "🔴", "warn": "🟠", "info": "🔵"}


def build_report(dashboard_url: str = "http://localhost:3000") -> str:
    analyses = latest_per_ticker()
    analyzed = {a["ticker"] for a in analyses}
    lines = [f"📊 **Daily Watchlist Report — {date.today().isoformat()}**", ""]

    # (1) สิ่งที่เปลี่ยนแตะ thesis — สำคัญสุด อยู่บนสุด
    change_lines = []
    for a in analyses:
        for c in detect_changes(a["ticker"])["changes"]:
            em = SEVERITY_EMOJI.get(c["severity"], "•")
            change_lines.append(f"{em} **{a['ticker']}** — {c['detail']}")
    if change_lines:
        lines.append("⚠️ **เปลี่ยนแปลงที่ต้องดู**")
        lines += change_lines
    else:
        lines.append("✅ ไม่มีการเปลี่ยนแปลงที่แตะ thesis วันนี้")
    lines.append("")

    # (2) สถานะพื้นฐานย่อ (แข็ง/อ่อน · แพง/ถูก)
    lines.append("**สถานะพื้นฐาน**")
    for a in analyses:
        s = a["summary"]
        em = STRENGTH_EMOJI.get(s["fundamental_strength"], "⚪")
        lines.append(f"{em} `{a['ticker']:<5}` {s['fundamental_strength']} / {s['valuation_view']}")

    # (3) ตัวที่ยังรอวิเคราะห์
    pending = [r["ticker"] for r in list_all() if r["ticker"] not in analyzed]
    if pending:
        lines.append("")
        lines.append("⏳ รอวิเคราะห์: " + ", ".join(pending))

    lines.append("")
    lines.append(f"🔎 รายละเอียด/tooltip: {dashboard_url}")
    return "\n".join(lines)


def send_report() -> bool:
    """สร้าง report แล้วส่งเข้า Discord (ข้ามเงียบๆ ถ้าไม่ตั้ง webhook)."""
    return post(build_report())


if __name__ == "__main__":   # ให้เรียก python -m src.agent.report ได้
    send_report()
