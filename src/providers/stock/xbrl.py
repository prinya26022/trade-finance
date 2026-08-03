"""SEC EDGAR XBRL companyfacts — ตัวเลขงบจาก 10-K ที่บริษัทยื่นจริงตามกฎหมาย (us-gaap taxonomy).

ทำไมต้องมีอันนี้: Phase 4 (check_extraction_accuracy) เทียบ 'ตัวเลขที่เราคำนวณ' กับ 'ตัวเลขที่
yfinance คำนวณ' — แต่ทั้งคู่มาจาก Yahoo แหล่งเดียวกัน จึงวัดได้แค่ 'เราลอกสูตร yfinance ตรงไหม'
ไม่ใช่ 'ตัวเลขถูกจริงไหม'. โมดูลนี้ดึงตัวเลขจาก XBRL ซึ่งเป็นต้นทางที่บริษัทยื่น ก.ล.ต. จริง —
อิสระจาก yfinance 100% — ให้ eval ชั้นใหม่ (check_xbrl_accuracy) เทียบกับ ground truth ที่แท้จริง.

Concept ที่ครอบ (thin slice — เอาเฉพาะ concept มาตรฐานสูง บริษัทส่วนใหญ่ tag ตรงกัน):
Revenue, Net Income, Operating Income, Stockholders Equity, Total Assets. ยังไม่ครอบทุกเมตริก
ที่ fundamentals.py คำนวณ (ROIC/FCF ต้องผสมหลาย concept + คำนวณภาษี ซับซ้อนกว่านี้).

ใช้ ticker_to_cik/_get_json จาก edgar.py (Phase 8) ซ้ำ — CIK lookup + User-Agent header เดียวกัน.
"""
import json
import time
from datetime import date
from pathlib import Path

from src.providers.stock.edgar import ticker_to_cik, _get_json

_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_CACHE_DIR = Path(__file__).parents[3] / "data" / "sec_facts_cache"
_CACHE_TTL = 7 * 24 * 3600  # งบนิ่งกว่ารายชื่อข่าว -> cache ได้นานกว่า CIK map (30 วัน) ก็ได้ แต่กันพลาดไว้ 7 วัน

_MIN_ANNUAL_DAYS = 350  # duration concept (Revenue ฯลฯ) ต้องครอบ ~1 ปีเต็ม ไม่ใช่ quarter เปรียบเทียบที่แอบอยู่ใน 10-K เดียวกัน

# concept name หลัก + สำรอง (บริษัทต่างกัน tag concept ไม่เหมือนกันเสมอ, เรียงจากพบบ่อยสุดก่อน)
# kind: "duration" (มี start/end, ต้องกรองช่วงเวลา ~1 ปี) | "instant" (มีแค่ end, ค่า ณ วันนั้น)
CONCEPTS: dict[str, tuple[list[str], str]] = {
    "Revenues": (["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"], "duration"),
    "NetIncomeLoss": (["NetIncomeLoss"], "duration"),
    "OperatingIncomeLoss": (["OperatingIncomeLoss"], "duration"),
    "StockholdersEquity": (["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "instant"),
    "Assets": (["Assets"], "instant"),
    # Phase 19.1: building blocks สำหรับ ground-truth ROIC/NOPAT/Net Debt/FCF (เมตริก derived ที่
    # fundamentals.py คำนวณเองจาก yfinance แต่ไม่เคยเทียบ SEC จริง) — ดู check_xbrl_accuracy
    "IncomeTaxExpense": (["IncomeTaxExpenseBenefit"], "duration"),
    "PretaxIncome": ([
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest",
    ], "duration"),
    "OperatingCashFlow": ([
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ], "duration"),
    "Capex": (["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "duration"),
    "CashAndEquivalents": (["CashAndCashEquivalentsAtCarryingValue"], "instant"),
    "LongTermDebtNoncurrent": (["LongTermDebtNoncurrent", "LongTermDebt"], "instant"),
    "LongTermDebtCurrent": (["LongTermDebtCurrent"], "instant"),
}

# ── Phase 33.5: หุ้นต่างชาติ (ADR) ยื่น **20-F ไม่ใช่ 10-K** และบางรายใช้ taxonomy IFRS ไม่ใช่
# us-gaap — เดิม eval นี้จึงคืน N/A ให้ TSM/ASML ตลอด แปลว่าสองตัวนี้ 'ไม่เคยถูก cross-check
# กับต้นฉบับที่บริษัทยื่นเลย' ทั้งที่เพิ่งพบว่าข้อมูลฝั่ง yfinance ของทั้งคู่มีปัญหาสกุลเงินจริงๆ
# (Phase 33.2) — เป็นคู่ที่ต้องการ ground truth มากที่สุดในพอร์ตแต่กลับไม่มีเลย
#
# ที่พบจากข้อมูลจริง: ASML ใช้ us-gaap แต่ยื่นด้วยฟอร์ม 20-F (แก้แค่ตัวกรองฟอร์มก็พอ)
#                    TSM ใช้ ifrs-full ทั้งชุด และรายงานเป็น TWD (ต้องรองรับทั้ง taxonomy และสกุล)
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}

# ชื่อ concept ฝั่ง IFRS ที่ตรงกับ key เดียวกันของ us-gaap ข้างบน — ตรวจกับ companyfacts จริงของ
# TSM แล้วว่ามีครบทุกตัว. key ไหนไม่มีคู่เทียบที่มั่นใจ ไม่ต้องใส่ (ปล่อยว่างดีกว่าจับคู่มั่ว
# เพราะ eval นี้คือ 'ตัวตัดสินความถูก' — ถ้าตัวอ้างอิงผิดเอง มันจะฟ้องว่าเราผิดทั้งที่เราถูก)
IFRS_CONCEPTS: dict[str, list[str]] = {
    "Revenues": ["Revenue"],
    "NetIncomeLoss": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "OperatingIncomeLoss": ["ProfitLossFromOperatingActivities"],
    "StockholdersEquity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "Assets": ["Assets"],
    "IncomeTaxExpense": ["IncomeTaxExpenseContinuingOperations"],
    "PretaxIncome": ["ProfitLossBeforeTax"],
    "OperatingCashFlow": ["CashFlowsFromUsedInOperatingActivities"],
    "Capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "CashAndEquivalents": ["CashAndCashEquivalents"],
}

# หน่วยที่ไม่ใช่สกุลเงิน — companyfacts ปนหน่วยพวกนี้มาด้วย (อัตราส่วน/จำนวนหุ้น)
_NON_CURRENCY_UNITS = {"pure", "shares", "USD/shares", "TWD/shares", "EUR/shares"}


def _cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"{ticker.upper()}.json"


def get_company_facts(ticker: str) -> dict | None:
    """ดึง companyfacts ทั้งก้อนของ ticker (cache ลงดิสก์ — ไฟล์ใหญ่ ~MB ไม่อยากยิงถี่).
    คืน None เงียบๆ ถ้าไม่พบ CIK หรือ EDGAR ล่ม -> eval ข้ามไปเฉยๆ ไม่ทำ pipeline พัง."""
    path = _cache_path(ticker)
    if path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass   # cache เสีย -> ดึงใหม่

    cik = ticker_to_cik(ticker)
    if cik is None:
        return None
    try:
        data = _get_json(_COMPANYFACTS.format(cik=cik))
    except Exception:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _dedup_latest_filed(rows: list[dict]) -> dict[int, float]:
    """หลาย 10-K มักรายงานปีเดียวกันซ้ำ (เป็นตัวเลขเทียบปีก่อน) — เอาค่าจาก filed ล่าสุดต่อปี
    (เผื่อกรณี restatement, ปกติค่าจะเท่าเดิม)."""
    by_year: dict[int, tuple[str, float]] = {}
    for r in rows:
        end = r.get("end")
        if not end:
            continue
        year = int(end[:4])
        filed = r.get("filed", "")
        if year not in by_year or filed >= by_year[year][0]:
            by_year[year] = (filed, float(r["val"]))
    return {year: val for year, (_, val) in by_year.items()}


def reporting_currency(facts: dict) -> str | None:
    """สกุลเงินที่บริษัทใช้รายงานใน companyfacts — เลือก 'สกุลที่พบบ่อยที่สุด' ครั้งเดียวต่อบริษัท
    แล้วใช้ตัวนั้นทุก concept.

    ทำไมต้องล็อกทั้งบริษัท ไม่ใช่เลือกทีละ concept: TSM รายงานเป็น TWD แต่บาง concept แถม USD
    (ตัวเลขแปลงค่าเพื่อความสะดวก มักมีแค่ปีล่าสุด) — ถ้าปล่อยให้แต่ละ concept เลือกเอง Revenue
    อาจได้ TWD ขณะที่ Net Income ได้ USD แล้ว margin ที่คำนวณจากสองตัวนี้จะกลายเป็นขยะที่ดู
    น่าเชื่อ ซึ่งเป็นบั๊กพันธุ์เดียวกับที่เพิ่งแก้ไปใน Phase 33.2 พอดี
    """
    counts: dict[str, int] = {}
    for taxonomy in ("us-gaap", "ifrs-full"):
        concepts = facts.get("facts", {}).get(taxonomy, {})
        for names, _ in CONCEPTS.values():
            for name in names:
                for unit, rows in (concepts.get(name) or {}).get("units", {}).items():
                    if unit not in _NON_CURRENCY_UNITS:
                        counts[unit] = counts.get(unit, 0) + len(rows)
        for names in IFRS_CONCEPTS.values():
            for name in names:
                for unit, rows in (concepts.get(name) or {}).get("units", {}).items():
                    if unit not in _NON_CURRENCY_UNITS:
                        counts[unit] = counts.get(unit, 0) + len(rows)
    return max(counts, key=counts.get) if counts else None


def _annual_values(facts: dict, key: str, concept_names: list[str], kind: str,
                   currency: str) -> list[tuple[str, float]]:
    """ค่ารายปีจากงบประจำปี (10-K หรือ 20-F) ของ concept แรกที่เจอ -> [(FY{year}, value), ...] ใหม่ก่อน.
    duration: กรองเฉพาะช่วง >= _MIN_ANNUAL_DAYS (ตัด quarter ที่ปนอยู่ในงบเดียวกันออก).
    instant: เอาทุกแถวของฟอร์มรายปีตรงๆ (มีแค่ end, ไม่มี duration ให้กรอง).
    ลอง us-gaap ก่อนแล้วค่อย ifrs-full — บริษัทหนึ่งใช้ taxonomy เดียว ไม่ปนกัน."""
    candidates = [("us-gaap", concept_names), ("ifrs-full", IFRS_CONCEPTS.get(key, []))]
    for taxonomy, names in candidates:
        concepts = facts.get("facts", {}).get(taxonomy, {})
        for name in names:
            concept = concepts.get(name)
            if concept is None:
                continue
            rows = concept.get("units", {}).get(currency, [])
            annual = [r for r in rows if r.get("form") in ANNUAL_FORMS and r.get("end")]
            if kind == "duration":
                annual = [
                    r for r in annual
                    if r.get("start")
                    and (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days >= _MIN_ANNUAL_DAYS
                ]
            by_year = _dedup_latest_filed(annual)
            if by_year:
                return sorted(((f"FY{y}", v) for y, v in by_year.items()), reverse=True)
    return []


def get_annual_series(ticker: str) -> dict[str, list[tuple[str, float]]]:
    """ทุก concept ใน CONCEPTS -> series รายปี (label ตรงกับ FY{year} เหมือน fundamentals.py).
    {} ทั้งก้อนถ้าดึง companyfacts ไม่ได้เลย (EDGAR ล่ม/ไม่มี CIK) — เรียกยังไงก็ไม่ raise.

    ทุก concept ถูกอ่านด้วยสกุลเดียวกันเสมอ (ดู reporting_currency) — eval ที่ใช้ต่อคำนวณเป็น
    'อัตราส่วน' ทั้งหมด (margin/ROE/ROIC) จึงเทียบได้ตรงๆ ไม่ว่าบริษัทจะรายงานสกุลไหน
    """
    facts = get_company_facts(ticker)
    if facts is None:
        return {}
    currency = reporting_currency(facts)
    if currency is None:
        return {}
    return {key: _annual_values(facts, key, names, kind, currency)
            for key, (names, kind) in CONCEPTS.items()}


if __name__ == "__main__":
    # python -m src.providers.stock.xbrl AAPL   -> ตัวเลขงบรายปีจาก 10-K จริง (debug/manual check)
    import sys

    t = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    series = get_annual_series(t)
    if not series:
        print(f"{t}: ดึง companyfacts ไม่ได้ (ไม่พบ CIK หรือ EDGAR ล่ม)")
    for concept, points in series.items():
        print(f"{concept}:")
        for period, val in points:
            print(f"  {period}: {val:,.0f}")