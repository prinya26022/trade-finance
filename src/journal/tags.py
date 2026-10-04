"""ปุ่มเหตุผล — ที่เดียวที่กำหนด (หน้าเว็บอ่านจาก API ไม่เขียนลิสต์ซ้ำ).

หมวดมาจากคอลัมน์ในชีตเดิมของผู้ใช้ เพื่อให้สถิติไม้เก่ากับไม้ใหม่ต่อกันได้. "single" = เลือกได้ข้อเดียว
"""
GROUPS: list[dict] = [
    {"key": "time", "label": "มีเวลาดูไม้นี้ไหม", "single": True, "options": ["มีเวลาดู", "ไม่มีเวลาดู"]},
    {"key": "plan", "label": "เข้าแบบไหน", "single": True, "options": ["ตามแผน", "ด้นสด"]},
    {"key": "trend", "label": "เทียบเทรนด์ (ความเห็นคุณ)", "single": True, "options": ["ตามเทรนด์", "สวนเทรนด์"]},
    {"key": "wave", "label": "นับเป็นคลื่น", "single": True,
     "options": ["1", "2", "3", "4", "5", "A", "B", "C", "ไม่นับ"]},
    {"key": "why", "label": "เหตุผล", "single": False,
     "options": ["นับคลื่น", "divergence", "แนวรับ/แนวต้าน", "pattern เคยได้ผล", "สามเหลี่ยม",
                 "HH/HL TF เล็ก", "ราคาลงมาเยอะ", "เห็นว่าสวย", "หวังว่าจะไป"]},
    {"key": "size", "label": "ขนาดไม้", "single": True, "options": ["ปกติ", "มั่นใจ เข้าใหญ่"]},
]

OPTIONS = {g["key"]: set(g["options"]) for g in GROUPS}
SINGLE = {g["key"] for g in GROUPS if g["single"]}


def clean(tags: dict) -> dict:
    """ทิ้งค่าที่ไม่อยู่ในลิสต์ — ข้อมูลมาจากหน้าเว็บ จะเชื่อไม่ได้ว่าส่งมาเฉพาะค่าที่ถูก"""
    out = {}
    for k, v in (tags or {}).items():
        if k not in OPTIONS:
            continue
        vals = [x for x in (v if isinstance(v, list) else [v]) if x in OPTIONS[k]]
        if vals:
            out[k] = vals[:1] if k in SINGLE else sorted(set(vals), key=list(OPTIONS[k]).index)
    return out
