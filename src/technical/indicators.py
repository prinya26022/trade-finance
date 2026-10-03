"""indicator พื้นฐาน — รับ list ราคาปิดเรียงเก่า -> ใหม่, คืน None เมื่อข้อมูลไม่พอ (ไม่เดา)."""


def sma(values: list[float], n: int, back: int = 0) -> float | None:
    """ค่าเฉลี่ย n แท่ง ที่สิ้นสุด `back` แท่งก่อนแท่งล่าสุด (back=0 = SMA ของแท่งล่าสุด)."""
    end = len(values) - back
    if n <= 0 or back < 0 or end < n:
        return None
    window = values[end - n:end]
    return sum(window) / n


def rsi_wilder(values: list[float], n: int = 14) -> float | None:
    """RSI แบบ Wilder (ตัวที่ TradingView ใช้) ของแท่งล่าสุด.

    ค่าเริ่มต้นเป็นค่าเฉลี่ยธรรมดาของ n แท่งแรก แล้ว smooth ต่อด้วย (prev*(n-1) + ใหม่)/n.
    ผลของจุดเริ่มต้นจางลงเป็น (13/14)^k — ข้อมูล 3 ปี (~150 แท่ง Week) จางจนไม่มีนัยแล้ว
    """
    if len(values) < n + 1:
        return None
    deltas = [b - a for a, b in zip(values, values[1:])]
    gain = sum(max(d, 0.0) for d in deltas[:n]) / n
    loss = sum(max(-d, 0.0) for d in deltas[:n]) / n
    for d in deltas[n:]:
        gain = (gain * (n - 1) + max(d, 0.0)) / n
        loss = (loss * (n - 1) + max(-d, 0.0)) / n
    # กรณีขอบตาม TradingView ตัวอักษรต่อตัวอักษร (`down == 0 ? 100 : up == 0 ? 0 : ...`) เพื่อให้
    # เลขที่นี่ตรงกับเลขบนจอที่ผู้ใช้ดูอยู่ — รวมถึงราคานิ่งสนิทที่ TV ให้ 100 (ไม่ใช่ 50 ที่ดู
    # สมเหตุสมผลกว่า) เพราะสองเครื่องมือที่ให้คนละเลขจากราคาเดียวกันคือที่มาของความไม่เชื่อทั้งคู่
    if loss == 0:
        return 100.0
    if gain == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def pct_change(a: float, b: float) -> float | None:
    """% เปลี่ยนจาก a ไป b."""
    if a is None or b is None or a <= 0:
        return None
    return (b / a - 1.0) * 100.0
