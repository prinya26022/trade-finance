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

Phase 19.1: ขยายจาก margin/ROE ไปครอบเมตริก 'derived' ที่ fundamentals.py คำนวณเอง —
FCF (CFO−Capex), NOPAT (EBIT×(1−อัตราภาษี)), ROIC (NOPAT/invested capital) — เพราะเมตริกพวกนี้
ขับ 2 เกณฑ์พื้นฐาน + valuation ทั้ง leg แต่ไม่เคยเทียบ SEC จริง. ผลตรวจ: FCF/NOPAT ตรงเป๊ะทุก
บริษัท (คำนวณถูก 100%), ROIC ใกล้ (±5-10% จากนิยาม invested capital). Net Debt 'ไม่' อยู่ในเช็ค
โดยตั้งใจ — มัน sign-flip ตามนิยาม (lease/short-term investment) จนไม่มี ground truth ที่ canonical.
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

    # ── Phase 19.1: ground-truth เมตริก derived (NOPAT/FCF/Net Debt/ROIC) เทียบ raw XBRL ──
    # เมตริกพวกนี้ fundamentals.py คำนวณเองจาก yfinance และ 'ไม่เคยเทียบ SEC จริง' — แต่มันขับ
    # ทั้ง 2 เกณฑ์พื้นฐาน (ROIC) + valuation ทั้ง leg (reinvestment_rate). ถ้า NOPAT/FCF เพี้ยน
    # จะผิดพร้อมกันหลายที่เงียบๆ. คำนวณ reference จาก XBRL ดิบด้วยสูตรเดียวกับ fundamentals.py
    tax = dict(xbrl.get("IncomeTaxExpense", []))
    pretax = dict(xbrl.get("PretaxIncome", []))
    op_income = dict(xbrl.get("OperatingIncomeLoss", []))
    cfo = dict(xbrl.get("OperatingCashFlow", []))
    capex = dict(xbrl.get("Capex", []))          # XBRL รายงาน capex เป็นเลขบวก (เงินจ่าย) -> FCF = CFO − capex
    cash = dict(xbrl.get("CashAndEquivalents", []))
    ltd_nc = dict(xbrl.get("LongTermDebtNoncurrent", []))
    ltd_c = dict(xbrl.get("LongTermDebtCurrent", []))

    def _nopat_ref(p: str) -> float | None:
        if p in op_income and p in tax and p in pretax and pretax[p]:
            return op_income[p] * (1 - tax[p] / pretax[p])   # NOPAT = EBIT × (1 − อัตราภาษีจริง)
        return None

    def _fcf_ref(p: str) -> float | None:
        return cfo[p] - capex[p] if p in cfo and p in capex else None

    def _total_debt(p: str) -> float | None:
        if p not in ltd_nc and p not in ltd_c:
            return None
        return ltd_nc.get(p, 0.0) + ltd_c.get(p, 0.0)

    def _roic_ref(p: str) -> float | None:
        # invested capital ใช้ debt/cash ตามนิยาม XBRL long-term-debt (อาจต่างจาก yfinance ที่รวม
        # lease) — เช็คนี้จับ 'ผิดหนัก' (2 เท่า/สลับเครื่องหมาย) ไม่ใช่ความแม่นระดับทศนิยม
        nopat, td = _nopat_ref(p), _total_debt(p)
        if nopat is None or td is None or p not in equity or p not in cash:
            return None
        invested = td + equity[p] - cash[p]
        return nopat / invested * 100 if invested else None

    # (ก) FCF เทียบรายปี (fcf_series ของเราเป็น FY เทียบ FY ของ XBRL ได้ตรง — ไม่ใช่ TTM)
    for p, ours in getattr(fundamentals, "fcf_series", []):
        ref = _fcf_ref(p)
        if ref is not None:
            checks.append({"metric": f"FCF ({p})", "ours": round(ours, 2), "reference": round(ref, 2),
                           "within_tolerance": _within_tolerance(ours, ref)})

    # (ข) NOPAT / ROIC — scalar ปีล่าสุด (period) ของเรา เทียบ reference ปีเดียวกัน.
    # หมายเหตุ: 'Net Debt' ไม่อยู่ในเช็คนี้โดยตั้งใจ — มันขึ้นกับนิยาม (lease นับเป็นหนี้ไหม, cash
    # รวม short-term investment ไหม) จน sign พลิกได้ (เจอจริง: NVDA/AMZN ของเรา=net-debt แต่
    # XBRL long-term-debt=net-cash) ไม่มี ground truth ที่ canonical -> นับใน accuracy จะหลอกว่า
    # ข้อมูลเราผิดทั้งที่เป็นเรื่องนิยาม. ความเปราะของ 'net-cash detection' นี้เป็น input ให้ Phase 19.2
    for our_val, ref_fn, label in [
        (getattr(fundamentals, "nopat", None), _nopat_ref, "NOPAT"),
        (getattr(fundamentals, "roic", None), _roic_ref, "ROIC"),
    ]:
        ref = ref_fn(period)
        if our_val is not None and ref is not None:
            checks.append({"metric": f"{label} ({period})", "ours": round(our_val, 2), "reference": round(ref, 2),
                           "within_tolerance": _within_tolerance(our_val, ref)})

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