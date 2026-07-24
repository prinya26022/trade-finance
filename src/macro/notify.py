"""ยิงแจ้งเตือน macro เข้า Discord — เรียกจาก workflow ตามรอบ (เงียบถ้าไม่มีตัวเลขใหม่).

pattern เดียวกับ src/agent/report.py::send_portfolio_alert: ฟังก์ชันเดียว, ช่อง webhook แยก,
เงียบสนิทถ้าไม่มีอะไรใหม่. ใช้ scan_for_alerts() (เทียบกับ macro.db ว่าเดือนไหนแจ้งไปแล้ว)
-> format_alert() (สรุป + base-rate ย้อนหลัง) -> discord.post(). ไม่เรียก LLM.

ช่อง: DISCORD_WEBHOOK_URL_MACRO (แนะนำแยกช่อง เพราะ cadence/หัวข้อต่างจาก #stock-research รายวัน)
      -> fallback DISCORD_WEBHOOK_URL -> ถ้าไม่ตั้งเลย discord.post() ข้ามเงียบๆ.
"""
import os

from src.macro import geonews, radar
from src.notify.discord import post


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


if __name__ == "__main__":  # รันมือ/ใน CI: python -m src.macro.notify
    n = send_macro_alert()
    print(f"[macro] ส่งแจ้งเตือน {n} รายการ" if n else "[macro] ไม่มีตัวเลขใหม่ — เงียบ")