"""Phase 12: ground-truth eval ที่แท้จริง — เทียบเมตริกที่เราคำนวณ (จาก yfinance) กับตัวเลข
จาก SEC XBRL (บริษัทยื่นเองตามกฎหมาย ใน 10-K, อิสระจาก yfinance 100%).

ต่างจาก check_extraction_accuracy (Phase 4) ที่เทียบ yfinance กับ yfinance เอง — วัดได้แค่
'เราลอกสูตร yfinance ตรงไหม' ไม่ใช่ 'ตัวเลขถูกจริงไหม'. อันนี้จับคู่ปีต่อปี (FY label เดียวกัน)
แล้วคำนวณ ratio จาก raw XBRL เอง (ไม่ใช้ ratio สำเร็จรูปจากที่ไหน) เทียบกับ series ที่เรามีอยู่แล้ว.

ไม่เรียก LLM, ไม่กิน Gemini quota — แต่เรียก EDGAR (network, cache 7 วัน) จึงช้ากว่า Phase 4
เล็กน้อยรอบแรก + อาจดึงไม่ได้บางบริษัท (companyfacts ไม่ครบ/ไม่พบ CIK) -> accuracy=None เงียบๆ,
ไม่ raise (เหมือน pattern เดิมของ eval อื่นในโปรเจกต์).

tolerance เข้มกว่า Phase 4 (5.0 -> 3.0 percentage points) เพราะเทียบปีต่อปีตรงๆ ไม่ผสม TTM/FY
เหมือน Phase 4 ที่ต้องยอมรับความเบี่ยงเบนจาก TTM-vs-FY.
"""
from src.providers.stock.fundamentals import StockFundamentals
from src.providers.stock.xbrl import get_annual_series

TOLERANCE_ABS = 3.0
TOLERANCE_REL = 0.25

# (our series field ใน StockFundamentals, ป้ายไว้ print)
SERIES_CHECKS = [
    ("net_margin_series", "Net Margin"),
    ("operating_margin_series", "Operating Margin"),
]


def _within_tolerance(ours: float, reference: float) -> bool:
    diff = abs(ours - reference)
    return bool(diff <= max(TOLERANCE_ABS, TOLERANCE_REL * abs(reference)))


def _margin_by_period(numer: dict[str, float], denom: dict[str, float]) -> dict[str, float]:
    """margin % ต่อปี จาก raw XBRL ตรงๆ (คำนวณเอง — ไม่ใช้ของสำเร็จรูปจากที่ไหน)."""
    return {p: round(numer[p] / denom[p] * 100, 2) for p in numer if p in denom and denom[p]}


def check_xbrl_accuracy(fundamentals: StockFundamentals, ticker: str) -> dict:
    """เทียบ net/operating margin (รายปี) + ROE (ปีล่าสุด) ที่เราคำนวณ กับค่าที่คำนวณจาก
    ตัวเลข XBRL ดิบตรงๆ. คืน dict มี 'accuracy' (0.0-1.0), None ถ้าดึง XBRL ไม่ได้/ไม่มีปีทับกัน."""
    xbrl = get_annual_series(ticker)
    revenue = dict(xbrl.get("Revenues", []))
    net_income = dict(xbrl.get("NetIncomeLoss", []))
    operating_income = dict(xbrl.get("OperatingIncomeLoss", []))
    equity = dict(xbrl.get("StockholdersEquity", []))

    xbrl_margins = {
        "net_margin_series": _margin_by_period(net_income, revenue),
        "operating_margin_series": _margin_by_period(operating_income, revenue),
    }

    checks: list[dict] = []
    for our_field, label in SERIES_CHECKS:
        ref_by_period = xbrl_margins[our_field]
        for period, ours in getattr(fundamentals, our_field):
            if period not in ref_by_period:
                continue   # ปีนี้ไม่มีใน XBRL (ยังไม่ยื่น/concept ไม่ match) -> ข้ามเงียบๆ
            ref_val = ref_by_period[period]
            checks.append({
                "metric": f"{label} ({period})",
                "ours": ours,
                "reference": ref_val,
                "within_tolerance": _within_tolerance(ours, ref_val),
            })

    # ROE (scalar, ปีล่าสุดของเรา) เทียบกับ NetIncome/StockholdersEquity ปีเดียวกันจาก XBRL
    period = fundamentals.period
    if fundamentals.roe is not None and period in equity and period in net_income and equity[period]:
        ref_val = round(net_income[period] / equity[period] * 100, 2)
        checks.append({
            "metric": f"ROE ({period})",
            "ours": fundamentals.roe,
            "reference": ref_val,
            "within_tolerance": _within_tolerance(fundamentals.roe, ref_val),
        })

    passed = sum(1 for c in checks if c["within_tolerance"])
    return {
        "ticker": ticker,
        "checks": checks,
        "accuracy": round(passed / len(checks), 2) if checks else None,
    }


if __name__ == "__main__":
    # รันข้าม watchlist ทั้งชุด สรุป accuracy % เทียบ SEC XBRL จริง — ไม่เรียก LLM ไม่กิน quota
    #   ใช้:  python -m src.evals.check_xbrl_accuracy
    from src.providers.stock.fundamentals import StockFundamentalsProvider
    from src.watchlist.store import list_all

    provider = StockFundamentalsProvider()
    all_results = []
    for row in list_all():
        tk = row["ticker"]
        if row["asset_type"] != "stock":
            continue
        try:
            f = provider.get_fundamentals(tk)
        except Exception as e:
            print(f"{tk}: ERROR fetching fundamentals - {e}")
            continue
        result = check_xbrl_accuracy(f, tk)
        all_results.append(result)

        acc = result["accuracy"]
        acc_str = f"{acc:.0%}" if acc is not None else "N/A (no XBRL data / no overlapping years)"
        print(f"\n{tk}: xbrl accuracy = {acc_str}")
        for c in result["checks"]:
            mark = "OK" if c["within_tolerance"] else "MISMATCH"
            print(f"  [{mark:8}] {c['metric']:28} ours={c['ours']:>8.2f}  xbrl={c['reference']:>8.2f}")

    scored = [r["accuracy"] for r in all_results if r["accuracy"] is not None]
    if scored:
        print(f"\n=== overall xbrl accuracy: {sum(scored)/len(scored):.1%} across {len(scored)} tickers ===")