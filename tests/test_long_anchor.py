"""ประวัติ FCF จากงบที่ยื่นจริงเป็น anchor ของ reverse-DCF (Phase 36). Offline ล้วน.

ที่มา: anchor เดิมคิดจากหน้าต่างที่ yfinance บังเอิญคืนมา ~4 ปี — CVX เริ่มที่ FY2022 ซึ่งเป็น
ยอดพีคราคาน้ำมัน เลยได้ FCF CAGR ~-24%/ปี, realistic growth -11.09%, ขาราคา 0/3. ประวัติ 19 ปี
จาก SEC บอกว่านั่นคือรอบวัฏจักร ไม่ใช่ธุรกิจถดถอย

หัวใจของชุดนี้คือ **เงื่อนไขที่ต้องผ่านก่อนจะยอมเปลี่ยน anchor** — การเปลี่ยนแหล่งข้อมูลกลางทาง
โดยไม่ตรวจว่าเป็นเส้นเดียวกันจริง คือวิธีสร้างเทรนด์ปลอมที่ดูน่าเชื่อ
"""
from types import SimpleNamespace

from src.agent.health import _build_duck_fundamentals, _window_years
from src.agent.valuation import reverse_dcf
from src.providers.stock import fundamentals as fnd
from src.providers.stock.xbrl import _annual_values, has_annual_data

SHORT = [("FY2022", 37.6), ("FY2023", 19.8), ("FY2024", 15.0), ("FY2025", 16.6)]
LONG = [("FY2007", 12.0), ("FY2008", 20.0), ("FY2009", 5.0), ("FY2010", 10.0),
        ("FY2011", 19.0), ("FY2012", 15.0), ("FY2013", 8.0), ("FY2014", 10.0),
        ("FY2015", 3.0), ("FY2016", 5.0), ("FY2017", 1.0), ("FY2018", 9.0),
        ("FY2019", 2.0), ("FY2020", 1.7), ("FY2021", 21.1),
        ("FY2022", 37.6), ("FY2023", 19.8), ("FY2024", 15.0), ("FY2025", 16.6)]


def _patch_long(monkeypatch, series):
    monkeypatch.setattr("src.providers.stock.xbrl.annual_fcf_series", lambda t: series)


# ---------- เงื่อนไขก่อนยอมใช้ประวัติยาว ----------

def test_a_long_history_that_agrees_on_the_overlap_is_used(monkeypatch):
    _patch_long(monkeypatch, LONG)
    cagr, window, years = fnd._long_fcf_growth("CVX", SHORT)
    assert years == 19 and window == "FY2007-FY2025"
    assert cagr > 0                      # 12.0 -> 16.6 ใน 18 ปี = โตช้าๆ ไม่ใช่ติดลบแบบหน้าต่างสั้น


def test_a_definition_change_on_the_overlap_is_refused(monkeypatch):
    """หัวใจ: ตัวเลขคนละนิยามที่ดูใกล้เคียงคือกับดัก — ฝั่งรายได้พังข้อนี้จริง (XBRL เลือก
    concept Revenues ซึ่งรวมรายได้อื่น ต่างจาก yfinance 3-4% ทุกปี)"""
    shifted = [(p, v * 1.05) for p, v in LONG]     # ต่าง 5% ทุกปี = เกิน tolerance 2%
    _patch_long(monkeypatch, shifted)
    assert fnd._long_fcf_growth("CVX", SHORT) == (None, None, None)


def test_a_history_that_does_not_overlap_at_all_is_refused(monkeypatch):
    """ไม่ทับกันเลย = พิสูจน์ไม่ได้ว่าเป็นชุดข้อมูลเดียวกัน (บทเรียนจาก NVDA ใน Phase 35)."""
    _patch_long(monkeypatch, [(p, v) for p, v in LONG if p < "FY2022"])
    assert fnd._long_fcf_growth("NVDA", SHORT) == (None, None, None)


def test_a_history_no_longer_than_what_we_already_have_is_refused(monkeypatch):
    _patch_long(monkeypatch, LONG[-4:])
    assert fnd._long_fcf_growth("X", SHORT) == (None, None, None)


def test_a_history_shorter_than_a_cycle_is_refused(monkeypatch):
    _patch_long(monkeypatch, LONG[-5:])             # 5 ปี < MIN_LONG_FCF_YEARS
    assert fnd._long_fcf_growth("NVDA", SHORT) == (None, None, None)


def test_endpoints_crossing_zero_are_refused(monkeypatch):
    """CAGR ไม่มีความหมายทางคณิตศาสตร์ถ้าปลายทางฝั่งหนึ่งไม่เป็นบวก — ต้องไม่คืนเลขมั่ว."""
    _patch_long(monkeypatch, [("FY2006", -3.0)] + LONG)
    assert fnd._long_fcf_growth("X", SHORT)[0] is None


def test_a_failure_to_reach_sec_degrades_to_the_old_behaviour(monkeypatch):
    def _boom(t):
        raise OSError("EDGAR ล่ม")
    monkeypatch.setattr("src.providers.stock.xbrl.annual_fcf_series", _boom)
    assert fnd._long_fcf_growth("CVX", SHORT) == (None, None, None)


# ---------- ผลต่อ reverse-DCF ----------

def _duck(**kw):
    base = dict(market_cap=100.0, free_cash_flow=10.0, fcf_series=SHORT, revenue=100.0,
                revenue_cagr=5.0, revenue_series=[("FY2024", 90.0), ("FY2025", 100.0)],
                net_debt=0.0, beta=1.0, capex=None, depreciation_amortization=None,
                nwc_change=None, nopat=None, roic=None, fcf_margin=10.0,
                fcf_cagr_long=None, fcf_long_window=None, fcf_long_years=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_long_anchor_replaces_the_short_window_when_present():
    """หน้าต่างสั้นของ SHORT ให้ CAGR ติดลบหนัก (37.6 -> 16.6) — ประวัติยาวต้องชนะ."""
    short_only = reverse_dcf(_duck(), risk_free_pct=4.0)
    with_long = reverse_dcf(_duck(fcf_cagr_long=3.21, fcf_long_window="FY2007-FY2025",
                                  fcf_long_years=19), risk_free_pct=4.0)
    assert short_only["realistic_growth"] < with_long["realistic_growth"]
    assert with_long["anchor_window"]["source"] == "fcf_long"
    assert with_long["anchor_window"]["years"] == 19


def test_without_a_long_anchor_nothing_changes():
    """แถวเก่า/หุ้นที่ดึง SEC ไม่ได้ ต้องได้ผลเดิมเป๊ะ — งานนี้ต้องเป็นการเพิ่ม ไม่ใช่เปลี่ยนของเดิม."""
    r = reverse_dcf(_duck(), risk_free_pct=4.0)
    assert r["anchor_window"]["source"] == "fcf"
    assert r["anchor_window"]["years"] == 4


def test_the_facts_path_and_the_object_path_give_the_same_anchor():
    """เหตุผลทั้งหมดที่เก็บเป็น Fact แทน attribute — สองพาธต้องตอบเท่ากัน (บั๊กซ้ำของ 33.3/34)."""
    facts = [{"label": "Market Cap", "value": 100.0, "unit": "USD", "period": "TTM"},
             {"label": "FCF Yield", "value": 10.0, "unit": "%", "period": "TTM"},
             {"label": "Beta", "value": 1.0, "unit": "x", "period": "TTM"},
             {"label": "Revenue CAGR", "value": 5.0, "unit": "%", "period": "TTM"},
             {"label": "FCF CAGR (long-run)", "value": 3.21, "unit": "%",
              "period": "FY2007-FY2025"}]
    facts += [{"label": "Free Cash Flow", "value": v, "unit": "USD", "period": p}
              for p, v in SHORT]

    duck = _build_duck_fundamentals(facts)
    assert duck.fcf_cagr_long == 3.21
    assert duck.fcf_long_years == 19
    assert reverse_dcf(duck, risk_free_pct=4.0)["anchor_window"]["source"] == "fcf_long"


def test_window_years_is_parsed_not_guessed():
    assert _window_years("FY2007-FY2025") == 19
    assert _window_years("FY2025") is None
    assert _window_years(None) is None


# ---------- การเลือก concept ฝั่ง XBRL ----------

def _rows(vals, form="10-K"):
    return [{"val": v, "end": f"{y}-12-31", "start": f"{y}-01-01", "form": form,
             "filed": f"{y + 1}-02-01"} for y, v in vals]


NEW_TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_the_concept_with_the_most_recent_data_wins_not_the_longest():
    """AAPL/ASML ถอยไปจบ FY2017 ทันทีตอนลองใช้ 'จำนวนปีมากสุด' — ประวัติยาวที่จบเมื่อ 8 ปีก่อน
    ไม่ใช่ประวัติของบริษัทวันนี้"""
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": _rows([(2010 + i, 100.0) for i in range(8)])}},
        NEW_TAG: {"units": {"USD": _rows([(2023, 300.0), (2024, 350.0), (2025, 400.0)])}},
    }}}
    out = _annual_values(facts, "Revenues", [NEW_TAG, "Revenues"], "duration", "USD")
    assert out[0] == ("FY2025", 400.0)
    assert len(out) == 3                  # ไม่รวมกับแท็กเก่า = ไม่มีรอยต่อคนละนิยาม


def test_the_longer_concept_wins_when_both_reach_the_same_year():
    """XOM: Revenues ถึง FY2025 17 ปี ส่วน RevenueFromContract... หยุดที่ FY2021."""
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": _rows([(2009 + i, 100.0 + i) for i in range(17)])}},
        NEW_TAG: {"units": {"USD": _rows([(2017 + i, 200.0) for i in range(5)])}},
    }}}
    out = _annual_values(facts, "Revenues", [NEW_TAG, "Revenues"], "duration", "USD")
    assert len(out) == 17 and out[0][0] == "FY2025"


def test_concepts_are_never_merged_into_one_series():
    """เติมช่องว่างข้ามแท็กได้ก็จริง แต่สองแท็กนี้คนละนิยาม (ของจริงต่างกัน 3-4% ทุกปี) —
    ต่อกันจะได้ 'การเติบโต' ที่แท้จริงคือการเปลี่ยนวิธีนับ"""
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": _rows([(2015, 100.0), (2016, 110.0)])}},
        NEW_TAG: {"units": {"USD": _rows([(2020, 200.0), (2021, 210.0), (2022, 220.0)])}},
    }}}
    out = _annual_values(facts, "Revenues", [NEW_TAG, "Revenues"], "duration", "USD")
    assert [p for p, _ in out] == ["FY2022", "FY2021", "FY2020"]


# ---------- นิติบุคคลใหม่ที่ยังไม่มีงบประจำปี ----------

def test_a_successor_shell_is_told_apart_from_a_company_with_no_data():
    """XOM ชี้ไป ExxonMobil Holdings Corp (ตั้ง 2026-07, มีแต่ 10-Q) — เดิมออกมาหน้าตาเหมือน
    บริษัทที่ไม่มีข้อมูลทุกประการ ทั้งที่ประวัติ 17 ปีอยู่ใต้ CIK เดิม"""
    shell = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": _rows([(2026, 1.0)], form="10-Q")}}}}}
    real = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": _rows([(2025, 1.0)])}}}}}
    assert has_annual_data(shell) is False
    assert has_annual_data(real) is True
    assert has_annual_data(None) is False


# ---------- ชื่อแถวงบกระแสเงินสดที่ yfinance สลับใช้ (Phase 38) ----------

def test_cfo_falls_back_to_the_continuing_operations_row():
    """ASML ของจริง: บางรอบ yfinance คืนเฉพาะ 'Cash Flow From Continuing Operating Activities'
    -> CFO หาย -> เกณฑ์ #3 คำนวณไม่ได้ -> คะแนนพลิก 6 ครั้งใน 17 วัน (ตัวหนักสุดในสมุดพก)."""
    import pandas as pd

    from src.providers.stock.fundamentals import CFO_ROWS, _first

    df = pd.DataFrame({pd.Timestamp("2025-12-31"): [12658500000.0]},
                      index=["Cash Flow From Continuing Operating Activities"])
    assert _first(CFO_ROWS, df) == 12658500000.0


def test_the_exact_row_still_wins_when_both_exist():
    """ชื่อสำรองต้องเป็นทางออกฉุกเฉิน ไม่ใช่ตัวแทน — บริษัทที่มี discontinued operations จริง
    'Operating Cash Flow' คือยอดรวม ส่วน 'Continuing' คือยอดที่ตัดส่วนที่เลิกไปแล้วออก"""
    import pandas as pd

    from src.providers.stock.fundamentals import CFO_ROWS, _first

    df = pd.DataFrame({pd.Timestamp("2025-12-31"): [100.0, 90.0]},
                      index=["Operating Cash Flow",
                             "Cash Flow From Continuing Operating Activities"])
    assert _first(CFO_ROWS, df) == 100.0
