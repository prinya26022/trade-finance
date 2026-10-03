"""มุมมองของ Claude — ความเห็นที่สามวางข้าง count ของผู้ใช้กับของเครื่อง (แบบเดียวกับ Phase 33).

โปรเจกต์นี้ไม่มี API key ของ Claude (LLM หลักคือ Gemini) จึงใช้ทางเดียวกับ Phase 33: ส่งออก
"แพ็ก" ข้อมูลเป็นไฟล์ให้คนแปะในแชท Claude -> นำคำตอบกลับมาเก็บ. ข้อมูลในแพ็กคือรายงานชุดเดียวกับ
ที่ส่ง Discord ทุกตัวอักษร (ไม่เขียน prompt แยก) ความเห็นจึงอ้างตัวเลขชุดเดียวกับอีกสองฝั่ง

ความเห็นเก็บพร้อมราคา/เวลาที่เขียน — คลื่นเปลี่ยนเร็ว ความเห็นเมื่อสามวันก่อนที่ไม่บอกอายุตัวเอง
จะถูกอ่านเหมือนเพิ่งเขียน (บทเรียน Phase 47)
"""
import re
from datetime import datetime, timezone
from pathlib import Path

from src.wave.analysis import Report, fmt

ROOT = Path(__file__).parents[2]
VIEW_DIR = ROOT / "data" / "waves" / "claude"
PACK_DIR = ROOT / "data" / "waves" / "packs"
_META = re.compile(r"^<!--\s*asof:\s*(?P<asof>[^|]+)\|\s*price:\s*(?P<price>[^|]+)\|\s*by:\s*(?P<by>.+?)\s*-->\s*$")

ASK = """คุณคือผู้ช่วยวิเคราะห์ Elliott Wave ที่ซื่อตรง อ่านรายงานด้านล่าง (count ที่ผู้ใช้มาร์ก, ทุก count ที่
เครื่องหาเจอและผ่านกฎเหล็ก, เทรนด์ M/W/D/4H, divergence) แล้วเขียน "มุมมองของคุณ" เป็นภาษาไทย:

1. count ที่คุณให้น้ำหนักมากที่สุด และทำไม (อ้างตัวเลขจากรายงานเท่านั้น ห้ามเดาตัวเลขเพิ่ม)
2. count ทางเลือกที่คุณคิดว่าผู้ใช้อาจมองข้าม
3. หลักฐานที่ขัดกับ count ที่คุณชอบ (ต้องมีอย่างน้อย 2 ข้อ)
4. ราคาที่จะทำให้คุณเปลี่ยนใจ — ทั้งฝั่งขึ้นและฝั่งลง
5. สิ่งที่คุณไม่แน่ใจ

ห้ามให้ความเห็นเป็นเปอร์เซ็นต์โอกาส ห้ามแนะนำซื้อ/ขาย/จุดเข้า — บอกแค่ count, ระดับราคา และเหตุผล
"""


def make_pack(stem: str, rep: Report, report_text: str) -> Path:
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    path = PACK_DIR / f"{stem}_{rep.last.ts:%Y%m%d_%H%M}.md"
    path.write_text(f"{ASK}\n---\n\n{report_text}\n", encoding="utf-8")
    return path


def save_view(stem: str, text: str, price: float, asof: datetime | None = None,
              by: str = "Claude (แปะจากแชท)") -> Path:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    asof = asof or datetime.now(timezone.utc).replace(tzinfo=None)
    path = VIEW_DIR / f"{stem}.md"
    path.write_text(f"<!-- asof: {asof:%Y-%m-%dT%H:%M} | price: {fmt(price)} | by: {by} -->\n"
                    f"{text.strip()}\n", encoding="utf-8")
    return path


def load_view(stem: str, now: datetime | None = None) -> dict | None:
    path = VIEW_DIR / f"{stem}.md"
    if not path.exists():
        return None
    first, _, body = path.read_text(encoding="utf-8").partition("\n")
    m = _META.match(first)
    if not m:
        return {"asof": None, "price": None, "by": "?", "text": path.read_text(encoding="utf-8"), "age_hours": None}
    asof = datetime.fromisoformat(m["asof"].strip())
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return {"asof": asof.isoformat(), "price": m["price"].strip(), "by": m["by"].strip(),
            "text": body.strip(), "age_hours": round((now - asof).total_seconds() / 3600, 1)}
