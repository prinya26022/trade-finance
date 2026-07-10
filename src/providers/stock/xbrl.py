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
}


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


def _annual_values(facts: dict, concept_names: list[str], kind: str) -> list[tuple[str, float]]:
    """ค่ารายปีจาก 10-K ของ concept แรกที่เจอใน concept_names -> [(FY{year}, value), ...] ใหม่ก่อน.
    duration: กรองเฉพาะช่วง >= _MIN_ANNUAL_DAYS (ตัด quarter ที่ปนอยู่ใน 10-K เดียวกันออก).
    instant: เอาทุกแถว form=10-K ตรงๆ (มีแค่ end, ไม่มี duration ให้กรอง)."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for name in concept_names:
        concept = us_gaap.get(name)
        if concept is None:
            continue
        rows = concept.get("units", {}).get("USD", [])
        tenk = [r for r in rows if r.get("form") == "10-K" and r.get("end")]
        if kind == "duration":
            tenk = [
                r for r in tenk
                if r.get("start")
                and (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days >= _MIN_ANNUAL_DAYS
            ]
        by_year = _dedup_latest_filed(tenk)
        if by_year:
            return sorted(((f"FY{y}", v) for y, v in by_year.items()), reverse=True)
    return []


def get_annual_series(ticker: str) -> dict[str, list[tuple[str, float]]]:
    """ทุก concept ใน CONCEPTS -> series รายปี (label ตรงกับ FY{year} เหมือน fundamentals.py).
    {} ทั้งก้อนถ้าดึง companyfacts ไม่ได้เลย (EDGAR ล่ม/ไม่มี CIK) — เรียกยังไงก็ไม่ raise."""
    facts = get_company_facts(ticker)
    if facts is None:
        return {}
    return {key: _annual_values(facts, names, kind) for key, (names, kind) in CONCEPTS.items()}


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