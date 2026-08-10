"""คณิตศาสตร์ของอนุกรมรายปีที่ใช้ร่วมกันทั้ง provider / agent / eval.

มีไฟล์นี้เพราะ CAGR ถูกคำนวณอยู่ 3 ที่และทั้งสามเคยคิดจำนวนปีจาก **จำนวนจุด** (`len(pts) - 1`)
ซึ่งถูกเฉพาะตอนอนุกรมต่อเนื่องไม่ขาดปี. ประวัติจริงจาก SEC ขาดปีกลางได้ (AAPL ไม่มี FY2014,
MSFT ไม่มี FY2014-15, XOM ไม่มี FY2013-14 — แท็ก concept เปลี่ยนปีนั้นพอดี) พอมีรู 12 จุดที่
กินเวลา 13 ปีจะถูกหารด้วย 11 แทน 12 = **CAGR พองขึ้นเงียบๆ** โดยตัวเลขยังดูสมเหตุสมผลทุกประการ

CAGR ที่ถูกต้องคิดจาก 'ช่วงเวลาจริงระหว่างหัวกับท้าย' ไม่ใช่จำนวนตัวอย่างที่บังเอิญมี — ปีที่
ขาดตรงกลางไม่กระทบสูตรที่ใช้แค่ปลายสองข้าง
"""


def fy_year(period: str) -> int | None:
    """ปีจากป้ายงวด ('FY2018' -> 2018). อ่านไม่ออกคืน None ไม่เดา."""
    digits = "".join(ch for ch in str(period) if ch.isdigit())
    return int(digits) if len(digits) == 4 else None


def year_span(points: list[tuple[str, float]]) -> int | None:
    """จำนวนปีระหว่างงวดแรกกับงวดสุดท้าย (เรียงแล้ว). อ่านปีไม่ออก -> None."""
    if len(points) < 2:
        return None
    first, last = fy_year(points[0][0]), fy_year(points[-1][0])
    if first is None or last is None or last <= first:
        return None
    return last - first


def cagr_pct(points: list[tuple[str, float]]) -> float | None:
    """CAGR (%/ปี) จากปลายสองข้างของอนุกรม — sort ให้เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา,
    บั๊กซ้ำซากของโปรเจกต์นี้). None ถ้าปลายทางฝั่งใดไม่เป็นบวก (CAGR ไร้ความหมายทางคณิตศาสตร์)
    หรืออ่านช่วงปีไม่ออก.
    """
    pts = sorted(points or [], key=lambda p: p[0])
    span = year_span(pts)
    if span is None:
        return None
    first, last = pts[0][1], pts[-1][1]
    if first <= 0 or last <= 0:
        return None
    return round(((last / first) ** (1 / span) - 1) * 100, 2)


def missing_years(points: list[tuple[str, float]]) -> list[str]:
    """ปีที่หายไปกลางอนุกรม — ไม่กระทบ cagr_pct (คิดจากปลายสองข้าง) แต่ควรรายงานให้เห็น
    เพราะมันแปลว่าแท็กบัญชีเปลี่ยนกลางทาง ซึ่งเป็นสัญญาณว่านิยามอาจไม่ต่อเนื่อง"""
    years = [fy_year(p) for p, _ in sorted(points or [], key=lambda p: p[0])]
    if not years or any(y is None for y in years):
        return []
    have = set(years)
    return [f"FY{y}" for y in range(min(years), max(years) + 1) if y not in have]
