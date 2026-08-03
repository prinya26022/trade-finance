"""หุ้นต่างชาติ (ADR) ใน SEC XBRL — Phase 33.5. Offline ล้วน (companyfacts ปลอม ไม่แตะ EDGAR).

เดิม eval นี้อ่านได้เฉพาะ `form == "10-K"` และ taxonomy `us-gaap` หน่วย `USD` เท่านั้น ทำให้
TSM/ASML คืน N/A ตลอด = สองตัวนี้ไม่เคยถูกเทียบกับต้นฉบับที่ยื่น ก.ล.ต. เลยสักครั้ง ทั้งที่เป็น
คู่ที่ข้อมูลฝั่ง yfinance มีปัญหาจริง (สกุลเงินปน — Phase 33.2) จึงต้องการ ground truth มากที่สุด.

ของจริงที่พบตอนแก้: ASML ใช้ us-gaap แต่ยื่นด้วยฟอร์ม 20-F / TSM ใช้ ifrs-full และรายงานเป็น TWD.
"""
from src.providers.stock.xbrl import _annual_values, get_annual_series, reporting_currency


def _fact(val, end, start=None, form="10-K", filed="2026-02-01"):
    row = {"val": val, "end": end, "form": form, "filed": filed}
    if start:
        row["start"] = start
    return row


def _facts(taxonomy: str, concept: str, unit: str, rows: list[dict], extra=None) -> dict:
    body = {taxonomy: {concept: {"units": {unit: rows}}}}
    if extra:
        body[taxonomy].update(extra)
    return {"facts": body}


def test_twenty_f_counts_as_an_annual_filing():
    """ASML: us-gaap ตามปกติ แต่ฟอร์มเป็น 20-F — เดิมถูกกรองทิ้งทั้งหมด."""
    facts = _facts("us-gaap", "Revenues", "EUR", [
        _fact(32_667_300_000, "2025-12-31", "2025-01-01", form="20-F"),
        _fact(28_262_900_000, "2024-12-31", "2024-01-01", form="20-F"),
    ])
    out = _annual_values(facts, "Revenues", ["Revenues"], "duration", "EUR")
    assert out == [("FY2025", 32_667_300_000.0), ("FY2024", 28_262_900_000.0)]


def test_ifrs_taxonomy_is_read_when_us_gaap_is_absent():
    """TSM: ไม่มี us-gaap เลย มีแต่ ifrs-full ชื่อ concept คนละชุด."""
    facts = _facts("ifrs-full", "Revenue", "TWD", [
        _fact(2_894_307_700_000, "2024-12-31", "2024-01-01", form="20-F"),
    ])
    out = _annual_values(facts, "Revenues", ["Revenues", "SalesRevenueNet"], "duration", "TWD")
    assert out == [("FY2024", 2_894_307_700_000.0)]


def test_us_gaap_wins_when_both_exist():
    """บริษัทหนึ่งใช้ taxonomy เดียว — แต่ถ้าเจอทั้งคู่ ต้องเลือกอย่างคงเส้นคงวา ไม่สลับไปมา."""
    facts = {"facts": {
        "us-gaap": {"Revenues": {"units": {"USD": [_fact(100, "2025-12-31", "2025-01-01")]}}},
        "ifrs-full": {"Revenue": {"units": {"USD": [_fact(999, "2025-12-31", "2025-01-01")]}}},
    }}
    assert _annual_values(facts, "Revenues", ["Revenues"], "duration", "USD") == [("FY2025", 100.0)]


def test_quarterly_rows_inside_an_annual_filing_are_still_excluded():
    facts = _facts("ifrs-full", "Revenue", "TWD", [
        _fact(1_000, "2024-12-31", "2024-10-01", form="20-F"),      # ไตรมาสเดียว
        _fact(4_000, "2024-12-31", "2024-01-01", form="20-F"),      # ทั้งปี
    ])
    assert _annual_values(facts, "Revenues", ["Revenues"], "duration", "TWD") == [("FY2024", 4_000.0)]


def test_reporting_currency_picks_the_one_the_company_actually_reports_in():
    """TSM แถม USD มาบาง concept (ตัวเลขแปลงค่า มักมีแค่ปีล่าสุด) — ต้องไม่ชนะ TWD ที่เป็นสกุลจริง."""
    facts = _facts("ifrs-full", "Revenue", "TWD", [
        _fact(1, "2024-12-31", "2024-01-01", form="20-F"),
        _fact(2, "2023-12-31", "2023-01-01", form="20-F"),
        _fact(3, "2022-12-31", "2022-01-01", form="20-F"),
    ])
    facts["facts"]["ifrs-full"]["Revenue"]["units"]["USD"] = [
        _fact(9, "2024-12-31", "2024-01-01", form="20-F")
    ]
    assert reporting_currency(facts) == "TWD"


def test_reporting_currency_ignores_non_currency_units():
    facts = _facts("ifrs-full", "Revenue", "pure", [_fact(1, "2024-12-31", "2024-01-01")])
    assert reporting_currency(facts) is None


def test_all_concepts_are_read_in_one_currency(monkeypatch):
    """หัวใจ: Revenue สกุลหนึ่ง แต่ Net Income อีกสกุล = margin กลายเป็นขยะที่ดูน่าเชื่อ
    (บั๊กพันธุ์เดียวกับที่แก้ใน Phase 33.2) — ต้องล็อกสกุลทั้งบริษัท ไม่ใช่เลือกทีละ concept."""
    facts = {"facts": {"ifrs-full": {
        "Revenue": {"units": {
            "TWD": [_fact(1000, "2024-12-31", "2024-01-01", form="20-F"),
                    _fact(900, "2023-12-31", "2023-01-01", form="20-F")],
            "USD": [_fact(30, "2024-12-31", "2024-01-01", form="20-F")],
        }},
        # ปีล่าสุดมีแต่ USD -> ต้องไม่ถูกหยิบมาปนกับ Revenue ที่เป็น TWD
        "ProfitLoss": {"units": {"USD": [_fact(12, "2024-12-31", "2024-01-01", form="20-F")]}},
    }}}
    monkeypatch.setattr("src.providers.stock.xbrl.get_company_facts", lambda t: facts)

    series = get_annual_series("TSM")
    assert series["Revenues"] == [("FY2024", 1000.0), ("FY2023", 900.0)]
    assert series["NetIncomeLoss"] == []          # ว่าง ดีกว่าได้ค่าที่เทียบกันไม่ได้


def test_ten_k_path_is_unchanged(monkeypatch):
    """หุ้นอเมริกันต้องได้ผลเหมือนเดิมเป๊ะ — งานนี้ต้องเป็นการเพิ่มความสามารถ ไม่ใช่เปลี่ยนของเดิม."""
    facts = _facts("us-gaap", "Revenues", "USD", [
        _fact(416_161_000_000, "2025-09-27", "2024-09-29"),
        _fact(391_035_000_000, "2024-09-28", "2023-10-01"),
    ])
    monkeypatch.setattr("src.providers.stock.xbrl.get_company_facts", lambda t: facts)
    assert get_annual_series("AAPL")["Revenues"] == [
        ("FY2025", 416_161_000_000.0), ("FY2024", 391_035_000_000.0)]
