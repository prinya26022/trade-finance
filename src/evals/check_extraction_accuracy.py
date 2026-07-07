"""Phase 4: วัดความแม่นของ 'การคำนวณ' ของเราเอง (ไม่ใช่ของ LLM) เป็น % — ground-truth eval

ต่างจาก check_grounding/check_facts_grounding (เช็คว่า LLM พูดตรงกับ Fact ที่เราให้ไหม)
eval นี้เช็คว่า 'Fact ที่เราคำนวณเอง' ถูกต้องจริงไหม — เทียบกับค่าที่ yfinance คำนวณเอง
อิสระ (ผ่าน info dict) ซึ่งไม่ได้มาจากไปป์ไลน์ fundamentals.py ของเราเลย

ทำไมใช้ yfinance เป็น ground truth แทน EDGAR: ยังไม่มีตัวแปลงงบจริงจาก 10-K (Phase หลัง)
yfinance's info dict คือแหล่งอิสระที่ใกล้เคียงที่สุดตอนนี้ — คำนวณ ROE/margin ของมันเอง
คนละโค้ดกับเรา ถ้าค่าของเราเบี่ยงเบนไปมาก (เกินกว่าที่ TTM vs FY ต่างช่วงเวลาจะอธิบายได้)
แปลว่ามีบั๊กจริงในการคำนวณของเรา (แบบเดียวกับที่เจอ TTM/FY mislabeling ใน fundamentals.py) —
ไม่ใช่ LLM มั่ว เพราะ eval นี้ไม่เรียก LLM เลย เทียบแค่ 2 แหล่งข้อมูลดิบ ไม่กิน Gemini quota
รันกี่ครั้งก็ได้ฟรี.

ยอมรับส่วนเบี่ยงเบนจาก TTM-vs-FY (yfinance's info มักเป็น TTM, ของเราส่วนใหญ่เป็น FY สิ้นปีงบ)
ด้วย tolerance ที่กว้างพอ — เป้าหมายคือจับ 'ผิดชัดเจน' (สูตรผิด/แถวผิด/สลับเครื่องหมาย)
ไม่ใช่จับความต่างเล็กน้อยจากคนละช่วงเวลา.
"""
import yfinance as yf

from src.providers.stock.fundamentals import StockFundamentals

TOLERANCE_ABS = 5.0    # หน่วยเปอร์เซ็นต์ (percentage points) สำหรับเมตริกที่เป็น %
TOLERANCE_REL = 0.40   # หรือ 40% ของค่าอ้างอิง (relative) — เอาตัวที่ 'หลวมกว่า'

# (field ของเรา, key ใน yfinance info, ค่าที่ info คืนเป็นสัดส่วน 0.xx ไหม -> ต้อง *100)
SCALAR_CHECKS = [
    ("roe", "returnOnEquity", True),
    ("current_ratio", "currentRatio", False),
]

# (field series ของเรา, key ใน info) — เทียบเฉพาะปีล่าสุด (series[0]) กับค่า TTM ของ yfinance
SERIES_CHECKS = [
    ("gross_margin_series", "grossMargins"),
    ("operating_margin_series", "operatingMargins"),
    ("net_margin_series", "profitMargins"),
]


def _within_tolerance(ours: float, reference: float) -> bool:
    diff = abs(ours - reference)
    # bool(...) กัน numpy.bool_ หลุดออกไป (ถ้า ours/reference เป็น numpy scalar จากที่อื่น) —
    # numpy.bool_ ไม่ใช่ subclass ของ bool ปกติ ทำให้ json.dumps() serialize ไม่ได้ตอนบันทึกลง DB
    return bool(diff <= max(TOLERANCE_ABS, TOLERANCE_REL * abs(reference)))


def check_extraction_accuracy(fundamentals: StockFundamentals, ticker: str) -> dict:
    """เทียบเมตริกที่เราคำนวณเอง กับค่าที่ yfinance คำนวณเองอิสระ (คนละโค้ดกับเรา).
    คืน dict มี 'accuracy' = สัดส่วนเมตริกที่ผ่าน tolerance (0.0-1.0), None ถ้าไม่มีคู่เทียบเลย."""
    info = yf.Ticker(ticker).info
    checks: list[dict] = []

    for our_field, info_key, is_pct in SCALAR_CHECKS:
        ours = getattr(fundamentals, our_field)
        ref = info.get(info_key)
        if ours is None or ref is None:
            continue
        ref_val = round(ref * 100, 2) if is_pct else round(ref, 2)
        checks.append({
            "metric": our_field,
            "ours": ours,
            "reference": ref_val,
            "within_tolerance": _within_tolerance(ours, ref_val),
        })

    for series_field, info_key in SERIES_CHECKS:
        series = getattr(fundamentals, series_field)
        ref = info.get(info_key)
        if not series or ref is None:
            continue
        ours = series[0][1]               # ค่าปีล่าสุด (FY)
        ref_val = round(ref * 100, 2)      # yfinance info เก็บเป็นสัดส่วน (0.32) -> %
        checks.append({
            "metric": series_field,
            "ours": ours,
            "reference": ref_val,
            "within_tolerance": _within_tolerance(ours, ref_val),
        })

    passed = sum(1 for c in checks if c["within_tolerance"])
    return {
        "ticker": ticker,
        "checks": checks,
        "accuracy": round(passed / len(checks), 2) if checks else None,
    }


if __name__ == "__main__":
    # รันข้าม watchlist ทั้งชุด สรุป accuracy % รวม — ไม่เรียก LLM ไม่กิน quota
    #   ใช้:  python -m src.evals.check_extraction_accuracy
    from src.providers.stock.fundamentals import StockFundamentalsProvider
    from src.watchlist.store import list_all

    provider = StockFundamentalsProvider()
    all_results = []
    for row in list_all():
        tk = row["ticker"]
        try:
            f = provider.get_fundamentals(tk)
        except Exception as e:
            print(f"{tk}: ERROR fetching fundamentals - {e}")
            continue
        result = check_extraction_accuracy(f, tk)
        all_results.append(result)

        acc = result["accuracy"]
        acc_str = f"{acc:.0%}" if acc is not None else "N/A (no comparable metrics)"
        print(f"\n{tk}: accuracy = {acc_str}")
        for c in result["checks"]:
            mark = "OK" if c["within_tolerance"] else "MISMATCH"
            print(f"  [{mark:8}] {c['metric']:24} ours={c['ours']:>10.2f}  yfinance={c['reference']:>10.2f}")

    scored = [r["accuracy"] for r in all_results if r["accuracy"] is not None]
    if scored:
        print(f"\n=== overall extraction accuracy: {sum(scored)/len(scored):.1%} across {len(scored)} tickers ===")