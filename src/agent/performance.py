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

    # dollar figures — เฉพาะเมื่อรู้จำนวนหุ้น (shares) ไม่งั้นเป็น None (โชว์แค่ % ได้)
    shares = float(row["shares"]) if row["shares"] is not None else None
    cost_basis = round(entry_price * shares, 2) if shares is not None else None
    market_value = round(cur_price * shares, 2) if shares is not None else None
    unrealized_pnl = round((cur_price - entry_price) * shares, 2) if shares is not None else None

    return {
        "ticker": ticker.upper(),
        "benchmark": benchmark,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "current_price": round(cur_price, 2),
        "shares": shares,
        "cost_basis": cost_basis,          # เงินต้นที่ลงไป (entry × shares)
        "market_value": market_value,      # มูลค่าตอนนี้ (current × shares)
        "unrealized_pnl": unrealized_pnl,  # กำไร/ขาดทุน $ ที่ยังไม่ realize
        "weight": None,                    # % ของพอร์ต — เติมทีหลังใน portfolio_edge (ต้องรู้ total ก่อน)
        "your_return": round(your_return * 100, 2),      # %
        "benchmark_return": round(bench_return * 100, 2),  # %
        "edge": round((your_return - bench_return) * 100, 2),  # % (บวก = ชนะ index)
        "holding_days": days,
    }


def portfolio_edge(benchmark: str | None = None) -> dict:
    """รวมทุกตัวที่ 'holding' — edge + $ รายตัว + สรุปพอร์ต (มูลค่ารวม/กำไรรวม/กี่ตัวชนะ benchmark).
    weight (% ของพอร์ต) ต้องรู้ market_value รวมก่อน จึงเติมหลังคำนวณครบทุกตัว."""
    benchmark = (benchmark or get_benchmark()).upper()
    positions = []
    for r in list_all():
        if r["status"] == "holding":
            edge = compute_edge(r["ticker"], benchmark)
            if edge:
                positions.append(edge)
    beating = sum(1 for p in positions if p["edge"] > 0)

    # รวม $ เฉพาะตัวที่รู้ shares (มี market_value) — ตัวที่ไม่ใส่ shares จะไม่นับเข้ายอดรวม/weight
    priced = [p for p in positions if p["market_value"] is not None]
    total_value = round(sum(p["market_value"] for p in priced), 2) if priced else None
    total_cost = round(sum(p["cost_basis"] for p in priced), 2) if priced else None
    total_pnl = round(sum(p["unrealized_pnl"] for p in priced), 2) if priced else None
    total_return = round((total_pnl / total_cost) * 100, 2) if total_cost else None
    if total_value:
        for p in priced:
            p["weight"] = round(p["market_value"] / total_value * 100, 1)

    return {
        "benchmark": benchmark,
        "positions": positions,
        "beating_benchmark": beating,
        "total_positions": len(positions),
        "total_value": total_value,      # มูลค่าพอร์ตรวมตอนนี้ ($)
        "total_cost": total_cost,        # เงินต้นรวม ($)
        "total_pnl": total_pnl,          # กำไร/ขาดทุนรวมที่ยังไม่ realize ($)
        "total_return": total_return,    # % ผลตอบแทนรวมของพอร์ต
    }


if __name__ == "__main__":
    # python -m src.agent.performance          -> edge ของทุก holding เทียบ benchmark ปัจจุบัน
    result = portfolio_edge()
    print(f"benchmark = {result['benchmark']}  ({result['beating_benchmark']}/{result['total_positions']} ชนะ)\n")
    for p in result["positions"]:
        sign = "🟢 ชนะ" if p["edge"] > 0 else "🔴 แพ้"
        print(f"  {p['ticker']:6} you {p['your_return']:+.1f}%  vs  {p['benchmark']} {p['benchmark_return']:+.1f}%"
              f"  ->  edge {p['edge']:+.1f}%  {sign}  ({p['holding_days']}d)")
