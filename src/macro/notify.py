"""ยิงแจ้งเตือน macro เข้า Discord — เรียกจาก workflow ตามรอบ (เงียบถ้าไม่มีตัวเลขใหม่).

pattern เดียวกับ src/agent/report.py::send_portfolio_alert: ฟังก์ชันเดียว, ช่อง webhook แยก,
เงียบสนิทถ้าไม่มีอะไรใหม่. ใช้ scan_for_alerts() (เทียบกับ macro.db ว่าเดือนไหนแจ้งไปแล้ว)
-> format_alert() (สรุป + base-rate ย้อนหลัง) -> discord.post(). ไม่เรียก LLM.

ช่อง: DISCORD_WEBHOOK_URL_MACRO (แนะนำแยกช่อง เพราะ cadence/หัวข้อต่างจาก #stock-research รายวัน)
      -> fallback DISCORD_WEBHOOK_URL -> ถ้าไม่ตั้งเลย discord.post() ข้ามเงียบๆ.
"""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.macro import geonews, radar, store
from src.notify.discord import post

# คีย์พิเศษใน macro_seen (ไม่ชนกับ fred.SERIES) — จำว่าเตือน 'ระบบมีปัญหา' ไปวันไหนแล้ว
# เพื่อให้เตือนได้มากสุดวันละครั้ง ทั้งที่ workflow รันชั่วโมงละรอบ
_HEALTH_KEY = "__health"

# เดิมไฟล์นี้ไม่เคย load .env เลย (ต่างจาก report.py/summarize.py/timeline.py ที่ทำ) ทำให้
# python -m src.macro.notify รันมือในเครื่องอ่าน FRED_API_KEY/DISCORD_WEBHOOK_URL_MACRO ที่ตั้งไว้
# ใน .env ไม่เห็นเลย (env var ว่างเปล่าเงียบๆ) — ใน CI ไม่กระทบ (workflow set env ตรงๆ ผ่าน
# secrets, ไม่มีไฟล์ .env อยู่แล้ว load_dotenv หาไฟล์ไม่เจอก็แค่ no-op)
load_dotenv(Path(__file__).parents[2] / ".env")


def _webhook() -> str | None:
    return os.environ.get("DISCORD_WEBHOOK_URL_MACRO") or os.environ.get("DISCORD_WEBHOOK_URL")


def send_macro_alert(webhook_url: str | None = None, mark: bool = True,
                     include_geo: bool = True) -> int:
    """สแกนตัวเลข macro เดือนใหม่ -> โพสต์สรุป+base-rate เข้า Discord. คืนจำนวนที่ส่ง.

    mark=True: บันทึกว่าแจ้งแล้ว (กันซ้ำรอบหน้า). include_geo: แนบธงข่าวภูมิรัฐศาสตร์ท้าย
    'เฉพาะเมื่อมีตัวเลขใหม่จริง' (ไม่สแปมข่าวทุกชั่วโมง — ข่าวเป็น context ของ event ไม่ใช่ตัว trigger)."""
    url = webhook_url or _webhook()
    alerts = radar.scan_for_alerts(mark=mark)
    if not alerts:
        return 0   # เงียบ: ไม่มีตัวเลขใหม่

    sent = 0
    for view in alerts:
        if post(radar.format_alert(view), url):
            sent += 1

    if include_geo:
        geo = geonews.fetch_geopolitical(max_items=5)
        if geo:
            post(geonews.format_warn(geo), url)
    return sent


def format_health_warning(rows: list[radar.SeriesStatus]) -> str:
    broken = [r for r in rows if r.state == "fetch_failed"]
    late = [r for r in rows if r.state == "overdue"]
    lines = ["🛠️ **Macro radar: มีบางอย่างไม่ปกติ**"]
    if broken:
        lines.append(f"• ดึงข้อมูลจาก FRED ไม่ได้: {', '.join(r.key for r in broken)} "
                     f"— รอบนี้ตรวจไม่ได้จริง ไม่ใช่ 'ไม่มีข่าว'")
    for r in late:
        lines.append(f"• {r.label}: คาดว่าประกาศ {r.due_on} แต่เลยมา {r.overdue_days} วันแล้ว "
                     f"FRED ยังมีถึงเดือน {r.latest_ref[:7]}")
    lines.append("")
    lines.append("_แจ้งวันละครั้ง จนกว่าจะกลับเป็นปกติ_")
    return "\n".join(lines)


def send_health_warning(webhook_url: str | None = None, mark: bool = True,
                        today: date | None = None,
                        rows: list[radar.SeriesStatus] | None = None) -> bool:
    """เตือนเมื่อ radar เอง 'ตรวจไม่ได้' — ไม่ใช่เมื่อตลาดไม่มีข่าว. คืน True ถ้าส่งจริง.

    ที่ต้องมีเพราะรอบปกติของ radar คือเงียบ และรอบที่พังก็เงียบเหมือนกัน — เคยเกิดมาแล้วตอน
    FRED บล็อก IP ของ runner แล้วไม่มีสัญญาณอะไรออกมาเลยจนกว่าจะเปิด log อ่านเอง
    """
    today = today or date.today()
    rows = rows if rows is not None else radar.status(today)
    if not any(r.state in ("fetch_failed", "overdue") for r in rows):
        return False
    if store.get_seen(_HEALTH_KEY) == today.isoformat():     # เตือนไปแล้ววันนี้
        return False
    sent = post(format_health_warning(rows), webhook_url or _webhook())
    if sent and mark:
        store.mark_seen(_HEALTH_KEY, today.isoformat())
    return bool(sent)


if __name__ == "__main__":  # รันมือ/ใน CI: python -m src.macro.notify
    n = send_macro_alert()
    print(f"[macro] ส่งแจ้งเตือน {n} รายการ" if n else "[macro] ไม่มีตัวเลขใหม่ — เงียบ")

    # พิมพ์สถานะทุกรอบ: log ของ workflow กลายเป็นหลักฐานว่า 'เงียบเพราะไม่มีข่าว'
    # ไม่ใช่ 'เงียบเพราะดึงข้อมูลไม่ได้' — สองอย่างนี้เคยหน้าตาเหมือนกันเป๊ะ
    rows = radar.status()
    print()
    print(radar.render_status(rows))
    if send_health_warning(rows=rows):
        print("\n[macro] ส่งเตือนสถานะระบบเข้า Discord แล้ว")