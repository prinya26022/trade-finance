"""ไล่ระดับ 0.0-1.0 เชิงเส้นรอบ threshold แทน step function เป๊ะๆ — ตัวช่วยกลางที่ health.py (19.3)
และ valuation.py (20.1) ใช้ร่วมกัน (ดึงออกมาจาก health.py เพราะ health.py import valuation.py
อยู่แล้ว ถ้า valuation.py import กลับจาก health.py จะเกิด circular import).

หลักการ: threshold+band = ผ่านเต็ม (1.0), threshold-band = ไม่ผ่านเลย (0.0), ตรง threshold พอดี
= กึ่งกลาง (0.5), ไล่เชิงเส้นระหว่างนั้น — กันตัวเลขขยับเศษเสี้ยวใกล้ threshold แล้วพลิกคะแนนเต็มจุด
(root ของปัญหา "score กระโดด" ที่เจอทั้งฝั่ง fundamental และ valuation)."""


def graded_above(value: float, threshold: float, band: float) -> float:
    """ไล่ระดับ 0.0-1.0 เชิงเส้น: 1.0 ที่ value>=threshold+band, 0.0 ที่ value<=threshold-band
    (ยิ่งค่ามากยิ่งดี — ROIC, margin, revenue growth ฯลฯ)."""
    return max(0.0, min(1.0, (value - (threshold - band)) / (2 * band)))


def graded_below(value: float, threshold: float, band: float) -> float:
    """เหมือน graded_above แต่กลับทิศ (ยิ่งน้อยยิ่งดี — leverage ratio, dilution %, valuation gap)."""
    return graded_above(-value, -threshold, band)
