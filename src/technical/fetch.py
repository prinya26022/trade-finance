"""ราคารายวันแบบปรับแล้ว — **ที่เดียวในแพ็กเกจนี้ที่แตะเน็ต**.

คืน None เมื่อดึงไม่ได้ ไม่คืน list ว่างที่หน้าตาเหมือน "ไม่มีข้อมูล" — ปลายทางต้องแยกได้ว่า
"เน็ตล่ม" กับ "หุ้นตัวนี้เพิ่ง IPO" (บทเรียน Phase 39)
"""
from src.technical.bars import Bar

HISTORY_PERIOD = "3y"   # ~156 แท่ง Week: พอสำหรับ SMA40 + ย้อน 10 และให้ RSI ลืมจุดเริ่มต้นแล้ว


def daily_closes(ticker: str, period: str = HISTORY_PERIOD) -> list[Bar] | None:
    """(วันที่ ISO, ราคาปิดปรับปันผล/แตกหุ้นแล้ว) เรียงเก่า -> ใหม่."""
    import yfinance as yf

    try:
        df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df:
        return None
    out = []
    for ts, close in df["Close"].items():
        c = float(close)
        if c == c and c > 0:          # ข้าม NaN / ราคาเสีย แทนที่จะปล่อยเข้าไปถึง indicator
            out.append((ts.date().isoformat(), c))
    return out or None
