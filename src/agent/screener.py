"""Screener (Phase 21) — ตอบคำถาม 'หาหุ้น US ที่ราคาถูก + พื้นฐานแข็งแรง ได้จากไหนบ้าง' โดยใช้
เอนจิ้นให้คะแนนเดียวกับที่วิเคราะห์ watchlist ทุกวัน (Piotroski /8 + reverse-DCF /3 — ดู
health.py/valuation.py) แต่ข้าม Gemini ไปเลย: fundamental/valuation ทั้งคู่คำนวณจากตัวเลขจริง
ล้วนอยู่แล้ว (ไม่ใช้ LLM summary เลย — sentiment เป็น metadata เท่านั้นตั้งแต่ 19.3.1) จึงสแกน
ได้หลายสิบตัวโดยไม่กินโควตา Gemini/วัน (ปัญหาที่เจอตอนคุยกันเรื่อง rate limit ก่อนหน้านี้).

ข้อจำกัดที่ต้องซื่อสัตย์ (เหมือนหลักที่ยึดมาตลอดโปรเจกต์นี้):
- UNIVERSE เป็น "รายชื่อคัดมือ" หุ้น large-cap ที่คุ้นเคย/สภาพคล่องสูง กระจายหลายเซกเตอร์ —
  ไม่ใช่ S&P 500 เต็มรูปแบบ ไม่ใช่ full market scan. เจตนาให้เป็นจุดเริ่ม 'สำรวจ' ไม่ใช่
  'ไม่มีอะไรดีกว่านี้อีกแล้วนอก list นี้'
- คะแนนที่ได้คือ 'พื้นฐานแข็ง + ราคาถูกกว่าที่ควรเป็น ณ วันนี้' เท่านั้น — ไม่ได้พิสูจน์ว่าเลือกแบบนี้
  แล้วชนะ VT จริง (ปัญหาเดียวกับที่ Phase 20.3 พยายามตอบสำหรับ watchlist เดิม — ตัวนี้ยังไม่มี
  point-in-time tracking ของตัวเอง)
- ตัวที่ข้อมูลไม่พอ (data gate < 6/8 เกณฑ์) หรือ reverse-DCF คำนวณไม่ได้ (ขาดทุน/นอกขอบเขตโมเดล)
  ถูกข้ามเงียบๆ เหมือน health score ทำกับ watchlist — ไม่ fallback ไปเดาคะแนน

ผลลัพธ์ cache ไว้ดิสก์ (data/screener_cache.json, TTL _CACHE_TTL_HOURS ชม.) เพราะสแกนทั้งก้อนต้อง
ยิง yfinance ~4 request/ticker (.info/financials/balance_sheet/cashflow) — ช้าระดับนาที ไม่ใช่
วินาที (เหมือน get_risk_free_rate_pct() แต่สเกลใหญ่กว่ามาก) จึงแยก 'อ่าน cache' (เร็ว) ออกจาก
'สแกนใหม่ทั้งก้อน' (force=True, ช้า) แทนที่จะคำนวณสดทุก request แบบ /api/portfolio.
"""
import json
import time
from pathlib import Path

from src.agent.health import (
    PARTIAL_MAX, _bank_valuation_score, _fundamental_score, _is_bank, _normalize_facts,
    no_valuation_reason, tier_from_score,
)
from src.agent.valuation import reverse_dcf
from src.providers.stock.fundamentals import StockFundamentalsProvider
from src.providers.stock.market import get_risk_free_rate_pct

_CACHE_PATH = Path(__file__).parents[2] / "data" / "screener_cache.json"
_CACHE_TTL_HOURS = 12

# คัดมือ: large/liquid US stocks กระจายหลายเซกเตอร์ — ดู docstring บนสุดสำหรับข้อจำกัดของ list นี้
UNIVERSE = [
    # Tech / software
    "MSFT", "AAPL", "GOOGL", "META", "ADBE", "CRM", "ORCL", "CSCO",
    # Semis
    "NVDA", "AMD", "AVGO", "TXN", "QCOM",
    # Consumer
    "AMZN", "WMT", "COST", "PG", "KO", "PEP", "MCD", "NKE", "HD",
    # Healthcare
    "JNJ", "UNH", "ABBV", "LLY", "TMO", "ABT",
    # Financials
    "JPM", "V", "MA", "GS", "AXP",
    # Industrials
    "HON", "CAT", "UPS",
    # Energy
    "XOM", "CVX",
    # Communication
    "DIS", "NFLX", "VZ",
]


def _fact_value(facts: list[dict], label: str) -> float | None:
    return next((f["value"] for f in facts if f["label"] == label), None)


def _partial_reason(dcf: dict | None, obj) -> tuple[str, bool]:
    """(ทำไมไม่มีขาราคา, เป็นปัญหาการดึงข้อมูลไหม) — ยืมจาก health.py ตัวเดียวกันเป๊ะ ไม่เขียนซ้ำ
    เพราะสองไฟล์นี้เคยตอบคนละอย่างสำหรับหุ้นตัวเดียวกันมาแล้วสองรอบ (33.3 แบงก์, 34 ORCL)."""
    return no_valuation_reason(obj, dcf)


def screen_one(ticker: str, risk_free_pct: float) -> dict | None:
    """สแกนหุ้นตัวเดียว -> dict (score/max/tier + เมตริกอ้างอิง) หรือ None ถ้าดึงข้อมูลไม่ได้/
    ฝั่งพื้นฐานคำนวณไม่ได้ — ข้ามเงียบๆ เหมือน loop.py (1 ตัวพังไม่ควรทำทั้ง scan ตาย).

    ขาราคาคำนวณไม่ได้แต่ขาพื้นฐานได้ -> คืนแถว 'พื้นฐานล้วน' (max=8, partial=True) ตามกติกา
    เดียวกับ Phase 29 ใน health.py ไม่ใช่ทิ้งทั้งตัว."""
    try:
        obj = StockFundamentalsProvider().get_fundamentals(ticker)
    except Exception as e:
        print(f"[screener] {ticker}: fundamentals failed - {e}")
        return None

    facts = _normalize_facts(obj.to_facts())
    fundamental = _fundamental_score(facts, risk_free_pct)
    if fundamental["disqualified"]:
        return None

    # Phase 33.3: ธนาคารต้องใช้เลนส์ราคาของตัวเอง (justified P/B) — reverse-DCF ตีความ FCF ของ
    # แบงก์ไม่ได้ (ติดลบมหาศาลจากการปล่อยสินเชื่อ) แล้วจะคืน None ทำให้แบงก์ถูกข้ามเงียบๆ ทั้งที่
    # ฝั่งพื้นฐานเพิ่งให้คะแนนไปแล้วด้วยเกณฑ์ธนาคาร. ปล่อยไว้ = สองพาธที่อ้างว่าใช้ 'เอนจิ้น
    # เดียวกัน' ให้คำตอบคนละอย่างสำหรับหุ้นตัวเดียวกัน (health ให้ JPM 10.6/11 แต่ screener ไม่เห็น)
    if _is_bank(facts):
        dcf = _bank_valuation_score(facts, risk_free_pct)
    else:
        dcf = reverse_dcf(obj, risk_free_pct=risk_free_pct)
    # Phase 34: ขาราคาคำนวณไม่ได้ != วิเคราะห์อะไรไม่ได้เลย. เดิมเคสนี้ถูกทิ้งทั้งตัวเงียบๆ ขณะที่
    # health.py คืนคะแนน 'พื้นฐานล้วน /8' ให้ตั้งแต่ Phase 29 — สองพาธที่อ้างว่าใช้เอนจิ้นเดียวกัน
    # ตอบคนละอย่างกับหุ้นตัวเดียวกันอีกครั้ง (ทรงเดียวกับที่แบงก์เจอใน 33.3 แต่กลับด้าน).
    # เจอจริง: ORCL — FCF เฉลี่ย 3 ปีติดลบจากรอบ capex ดาต้าเซ็นเตอร์ AI -> reverse-DCF ใช้ไม่ได้
    # -> หายจาก screener ทั้งที่ health ให้ 4.8/8. และนี่คือ bias ที่ผิดทิศที่สุดสำหรับ 'เครื่องมือ
    # ค้นหาตัวใหม่': บริษัทที่กำลังลงทุนหนักจนกระแสเงินสดติดลบชั่วคราว คือกลุ่มที่ควรถูกเห็นแล้ว
    # ตัดสินเอง ไม่ใช่กลุ่มที่ถูกซ่อนโดยที่ไม่มีใครรู้ว่าถูกซ่อน
    if dcf is None or dcf.get("score") is None:
        score = round(fundamental["score"], 2)
        tier, label = tier_from_score(score, PARTIAL_MAX)
        reason, data_gap = _partial_reason(dcf, obj)
        return {
            "ticker": ticker,
            "score": score,
            "max": PARTIAL_MAX,
            "tier": tier,
            "label": label,
            "partial": True,
            "partial_reason": reason,
            # แยก "ดึงข้อมูลไม่สำเร็จ" ออกจาก "ประเมินไม่ได้" ให้ฝั่งหน้าเว็บอ่านออกโดยไม่ต้องเดาจากข้อความ
            "data_gap": data_gap,
            "fundamental_score": fundamental["score"],
            "valuation_score": None,
            "implied_growth": None,
            "realistic_growth": None,
            "gap": None,
            "lens": (dcf or {}).get("lens", "NA"),
            "pe": _fact_value(facts, "P/E"),
            "roic": _fact_value(facts, "ROIC"),
            "market_cap": _fact_value(facts, "Market Cap"),
        }

    score = round(fundamental["score"] + dcf["score"], 2)
    tier, label = tier_from_score(score)

    return {
        "ticker": ticker,
        "score": score,
        "max": 11.0,
        "tier": tier,
        "label": label,
        "partial": False,
        "partial_reason": None,
        "data_gap": False,
        "fundamental_score": fundamental["score"],
        "valuation_score": dcf["score"],
        # แบงก์ไม่มี implied/realistic growth (คนละเลนส์) -> None ไม่ใช่ 0 ที่ชวนให้อ่านผิด
        "implied_growth": dcf.get("implied_growth"),
        "realistic_growth": dcf.get("realistic_growth"),
        "gap": dcf.get("gap"),
        "lens": dcf.get("lens", "NA"),
        "pe": _fact_value(facts, "P/E"),
        "roic": _fact_value(facts, "ROIC"),
        "market_cap": _fact_value(facts, "Market Cap"),
    }


def run_screen(tickers: list[str] = UNIVERSE) -> list[dict]:
    """สแกนทั้ง universe (deterministic, ไม่เรียก LLM) -> list เรียงคะแนนมาก->น้อย.

    แถว partial (/8) ต่อท้ายเป็นก้อนแยก ไม่ปนเข้าอันดับหลัก — 8/8 ไม่ได้แปลว่าดีกว่า 10/11
    (คนละมาตรวัด) การเรียงปนกันจะทำให้ 'อันดับ' โกหกทั้งที่ตัวเลขแต่ละตัวถูกต้อง
    (กติกาเดียวกับ comparable_score() ที่กัน partial ออกจากการเทียบข้ามตัว)"""
    rf = get_risk_free_rate_pct()
    results = [r for r in (screen_one(t, rf) for t in tickers) if r is not None]
    results.sort(key=lambda r: (r.get("partial", False), -r["score"]))
    return results


def screen(force: bool = False) -> dict:
    """คืน {"computed_at": epoch, "results": [...]} — อ่าน cache ดิสก์ถ้ายังไม่หมดอายุ
    (_CACHE_TTL_HOURS ชม.), ไม่งั้นสแกนใหม่ทั้งก้อน (ช้า — นาทีระดับ, ยิง yfinance ~4
    request/ticker) แล้วเขียน cache ทับ."""
    if not force and _CACHE_PATH.exists():
        age_hours = (time.time() - _CACHE_PATH.stat().st_mtime) / 3600
        if age_hours < _CACHE_TTL_HOURS:
            try:
                return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass   # cache เสีย -> สแกนใหม่

    payload = {"computed_at": time.time(), "results": run_screen()}
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    # python -m src.agent.screener [--force]
    import sys

    data = screen(force="--force" in sys.argv)
    results = data["results"]
    print(f"=== Screener: {len(results)}/{len(UNIVERSE)} ผ่านเกณฑ์ข้อมูลพอ "
          f"(computed_at={time.strftime('%Y-%m-%d %H:%M', time.localtime(data['computed_at']))}) ===")
    for r in results:
        # gap เป็น None ได้ (ธนาคารใช้เลนส์ justified P/B ซึ่งไม่มี growth gap)
        gap = f"{r['gap']:+.1f}pp" if r["gap"] is not None else "  n/a "
        print(
            f"  {r['ticker']:6} score={r['score']:.1f}/11 ({r['label']:6}) "
            f"gap={gap} lens={r['lens']:8} P/E={r['pe']}"
        )
