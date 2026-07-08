"""Performance / edge measurement (Phase 5.5).

ตอบคำถามที่ checklist ด่าน 182 บอกว่าเป็น 'สิ่งเดียวที่จะรู้ว่ามี edge หรือแค่โชค':
ตั้งแต่วันที่ซื้อ ผลตอบแทนของหุ้นที่ถือ ชนะ/แพ้ การเอาเงินก้อนเดียวกันไปใส่ benchmark
(เช่น VT) ในช่วงเวลาเดียวกันไหม.

ใช้ราคาย้อนหลังจาก yfinance เท่านั้น — ไม่เรียก LLM ไม่กิน Gemini quota.
"""
from datetime import datetime, timedelta

import yfinance as yf

from src.watchlist.store import get_entry, list_all
from src.settings.store import get_benchmark


def _close_on_or_after(ticker: str, date_str: str) -> float | None:
    """ราคาปิดวันแรกที่ >= date_str (เผื่อวันซื้อเป็นวันหยุด ตลาดไม่เปิด) ภายใน 7 วัน.
    คืน None เงียบๆ ถ้า yfinance ล้ม (network/ticker พัง) — ไม่ raise กัน report ทั้งฉบับพัง."""
    try:
        start = datetime.fromisoformat(date_str).date()
        hist = yf.Ticker(ticker).history(start=start.isoformat(),
                                         end=(start + timedelta(days=7)).isoformat())
        return None if hist.empty else float(hist["Close"].iloc[0])
    except Exception:
        return None


def _latest_close(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        return None if hist.empty else float(hist["Close"].iloc[-1])
    except Exception:
        return None


def compute_edge(ticker: str, benchmark: str | None = None) -> dict | None:
    """ผลตอบแทนของหุ้นที่ถือ vs benchmark ตั้งแต่วันซื้อ.
    คืน None ถ้า ticker ไม่ได้อยู่สถานะ 'holding' หรือข้อมูลไม่พอ (ไม่มี entry/ราคา benchmark)."""
    row = get_entry(ticker)
    if row is None or row["status"] != "holding" or not row["entry_price"] or not row["entry_date"]:
        return None

    benchmark = (benchmark or get_benchmark()).upper()
    entry_price = float(row["entry_price"])
    entry_date = row["entry_date"]

    cur_price = _latest_close(ticker.upper())
    bench_entry = _close_on_or_after(benchmark, entry_date)
    bench_now = _latest_close(benchmark)
    if cur_price is None or bench_entry is None or bench_now is None:
        return None

    your_return = (cur_price - entry_price) / entry_price
    bench_return = (bench_now - bench_entry) / bench_entry
    days = (datetime.now().date() - datetime.fromisoformat(entry_date).date()).days

    return {
        "ticker": ticker.upper(),
        "benchmark": benchmark,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "current_price": round(cur_price, 2),
        "your_return": round(your_return * 100, 2),      # %
        "benchmark_return": round(bench_return * 100, 2),  # %
        "edge": round((your_return - bench_return) * 100, 2),  # % (บวก = ชนะ index)
        "holding_days": days,
    }


def portfolio_edge(benchmark: str | None = None) -> dict:
    """รวมทุกตัวที่ 'holding' — edge รายตัว + สรุปว่ากี่ตัวชนะ benchmark."""
    benchmark = (benchmark or get_benchmark()).upper()
    positions = []
    for r in list_all():
        if r["status"] == "holding":
            edge = compute_edge(r["ticker"], benchmark)
            if edge:
                positions.append(edge)
    beating = sum(1 for p in positions if p["edge"] > 0)
    return {
        "benchmark": benchmark,
        "positions": positions,
        "beating_benchmark": beating,
        "total_positions": len(positions),
    }


if __name__ == "__main__":
    # python -m src.agent.performance          -> edge ของทุก holding เทียบ benchmark ปัจจุบัน
    result = portfolio_edge()
    print(f"benchmark = {result['benchmark']}  ({result['beating_benchmark']}/{result['total_positions']} ชนะ)\n")
    for p in result["positions"]:
        sign = "🟢 ชนะ" if p["edge"] > 0 else "🔴 แพ้"
        print(f"  {p['ticker']:6} you {p['your_return']:+.1f}%  vs  {p['benchmark']} {p['benchmark_return']:+.1f}%"
              f"  ->  edge {p['edge']:+.1f}%  {sign}  ({p['holding_days']}d)")
