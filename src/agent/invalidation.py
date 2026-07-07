"""Invalidation checker (Phase 5).

เช็คว่า 'เงื่อนไขที่จะพิสูจน์ว่าคิดผิด' (invalidation rules ที่ผู้ใช้เขียนไว้ตอนตั้ง thesis)
โดนแตะแล้วหรือยัง — เทียบกับตัวเลขงบล่าสุด แบบ deterministic (ไม่เรียก LLM ไม่กิน quota).

นี่คือหัวใจของ 'thesis stop' ที่ต่างจาก change detection ทั่วไป: change detection บอกว่า
'อะไรเปลี่ยน' (generic), ส่วนอันนี้บอกว่า 'เงื่อนไขออกที่ *คุณ* กำหนดเองโดนแตะ' (personal) —
ตรงกับด่าน 4 (invalidation point) ที่ checklist บอกว่าคนข้ามบ่อยสุด.
"""
import operator

from src.thesis.store import get_thesis
from src.history.store import history
from src.agent.changes import _latest_by_label

# map operator string -> ฟังก์ชันจริง (จำกัดชุดเดียวกับ store.VALID_OPS — ปลอดภัย ไม่ใช้ eval())
_OPS = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}


def check_invalidation(ticker: str) -> dict:
    """เทียบ invalidation rules ของ ticker กับ fact ล่าสุด + fair_value กับราคาล่าสุด.
    คืน dict:
      breaches         : rule ที่โดนแตะ (thesis สั่น -> ควรทบทวน/ออกตามที่วางไว้)
      no_margin_safety : True ถ้าราคาปัจจุบัน >= fair_value ที่ตั้งไว้ (ส่วนเผื่อพลาดหายไป)
      note             : ข้อความอธิบายกรณีเช็คไม่ได้ (ไม่มี thesis / ไม่มีข้อมูล)
    ทุกอย่างว่าง = thesis ยังอยู่ครบ (เงียบไว้)."""
    thesis = get_thesis(ticker)
    if thesis is None:
        return {"ticker": ticker, "breaches": [], "no_margin_safety": False, "note": "ยังไม่ได้ตั้ง thesis"}

    rows = history(ticker, limit=1)
    if not rows:
        return {"ticker": ticker, "breaches": [], "no_margin_safety": False, "note": "ยังไม่มีผลวิเคราะห์"}
    latest = rows[0]

    latest_by_label = _latest_by_label(latest.get("facts", []))   # {label: (period, value)}
    breaches = []
    for rule in thesis["invalidation"]:
        metric = rule["metric"]
        if metric not in latest_by_label:
            continue   # เช็คเมตริกนี้ไม่ได้ (ไม่มีในงบล่าสุด) -> ข้ามเงียบ ๆ ไม่ใช่ breach
        period, current = latest_by_label[metric]
        if _OPS[rule["op"]](current, rule["value"]):
            note = f" — {rule['note']}" if rule.get("note") else ""
            breaches.append({
                "type": "invalidation",
                "metric": metric,
                "detail": f"เงื่อนไขออกโดนแตะ: {metric} {current:g} {rule['op']} {rule['value']:g} ({period}){note}",
                "severity": "alert",
            })

    # fair_value: ราคาปัจจุบันเกินมูลค่าที่ประเมิน = margin of safety หาย (ด่าน 3)
    no_margin_safety = False
    fair = thesis.get("fair_value")
    price = latest.get("price")
    if fair and price is not None and price >= fair:
        no_margin_safety = True
        breaches.append({
            "type": "no_margin_safety",
            "metric": "price",
            "detail": f"ราคา {price:g} ถึง/เกิน fair value ที่ตั้งไว้ ({fair:g}) — margin of safety หาย",
            "severity": "warn",
        })

    return {"ticker": ticker, "breaches": breaches, "no_margin_safety": no_margin_safety, "note": ""}
