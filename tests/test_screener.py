"""Screener (Phase 21) — สแกน UNIVERSE คัดมือหาหุ้นพื้นฐานแข็ง+ราคาถูก โดยไม่เรียก Gemini เลย
(fundamental + reverse-DCF ทั้งคู่ deterministic ล้วน). Offline ทั้งหมด — mock
StockFundamentalsProvider.get_fundamentals กัน network, ไม่แตะ yfinance/Gemini จริง.
"""
from dataclasses import dataclass, field

import pytest

from src.agent.valuation import intrinsic_value
from src.agent import screener


@dataclass
class FakeStock:
    """ครอบทั้ง 2 พาธที่ screen_one ต้องใช้: .to_facts() (ให้ _fundamental_score อ่าน) และ
    attribute ตรงๆ (ให้ reverse_dcf duck-type อ่าน) — เหมือน FakeFundamentals ใน test_valuation.py
    แต่เพิ่ม to_facts() ให้ครบ 8 เกณฑ์ Piotroski ด้วย."""
    roic: float | None = None
    beta: float | None = None
    net_margin_fy: float | None = None
    fcf_margin: float | None = None
    cfo: float | None = None
    net_income: float | None = None
    revenue_cagr: float | None = None
    net_debt: float | None = None
    op_margin_prev: float | None = None
    op_margin_last: float | None = None
    shares_prev: float | None = None
    shares_last: float | None = None
    pe: float | None = None
    # --- reverse_dcf duck attrs ---
    free_cash_flow: float | None = None
    market_cap: float | None = None
    fcf_series: list = field(default_factory=list)
    revenue: float | None = None
    revenue_series: list = field(default_factory=list)
    capex: float | None = None
    depreciation_amortization: float | None = None
    nwc_change: float | None = None
    nopat: float | None = None

    def to_facts(self):
        out = []

        def add(label, value, period=""):
            if value is not None:
                out.append({"label": label, "value": value, "unit": "", "period": period})

        add("ROIC", self.roic)
        add("Beta", self.beta)
        add("Net Margin", self.net_margin_fy, "FY2025")
        add("FCF Margin", self.fcf_margin)
        add("CFO", self.cfo)
        add("Net Income", self.net_income)
        add("Revenue CAGR", self.revenue_cagr)
        add("Net Debt", self.net_debt)
        add("Operating Margin", self.op_margin_prev, "FY2024")
        add("Operating Margin", self.op_margin_last, "FY2025")
        add("Diluted Shares", self.shares_prev, "FY2024")
        add("Diluted Shares", self.shares_last, "FY2025")
        add("P/E", self.pe)
        add("Market Cap", self.market_cap)
        return out


def _strong_cheap_stock(target_growth: float) -> FakeStock:
    """8/8 Piotroski เต็ม (ทุกค่าไกลจาก threshold+-band พอจะได้ 1.0 เต็มทุกเกณฑ์) + reverse-DCF
    standard lens ที่ gap ควบคุมได้ผ่าน target_growth (เหมือน test_reverse_dcf_score_graded_bands:
    capex/da/nwc/nopat/roic ตั้งให้ sustainable_growth=5.0 เสมอ ไม่ขึ้นกับ revenue_cagr — nopat_margin
    คำนวณไม่ได้ (revenue=None) จึงไม่ trigger NOPAT_UNSTABLE, sustainable=5.0 ไม่ diverge จาก
    revenue_cagr=10.0 เกิน DIVERGENCE_TRIGGER_PP=15pp -> lens ยังเป็น 'standard' เสมอ)."""
    fcf = 100.0
    net_debt = -500.0
    ev = intrinsic_value(fcf, target_growth, 0.0925, 0.025, 10)   # WACC=9.25% (Rf=4, beta=1.0)
    market_cap = ev - net_debt   # reverse_dcf ทำ ev = market_cap + net_debt เอง -> ย้อนกลับตรงนี้ก่อน
    return FakeStock(
        roic=25.0, beta=1.0, net_margin_fy=20.0, fcf_margin=20.0, cfo=95.0, net_income=100.0,
        revenue_cagr=10.0, net_debt=net_debt, op_margin_prev=20.0, op_margin_last=22.0,
        shares_prev=100.0, shares_last=95.0, pe=15.0,
        free_cash_flow=fcf, market_cap=market_cap, capex=-250, depreciation_amortization=50,
        nwc_change=0, nopat=1000.0,
    )


def _data_gate_fail_stock() -> FakeStock:
    """แค่ ROIC ตัวเดียว -> computable 1/8 (< DATA_GATE_MIN_CRITERIA=6) -> disqualify ทั้งตัว."""
    return FakeStock(roic=25.0, market_cap=1000.0, free_cash_flow=50.0)


RF = 4.0


def test_screen_one_scores_strong_cheap_stock(monkeypatch):
    stock = _strong_cheap_stock(target_growth=-0.05)   # gap=-10pp, ไกลจาก boundary -> valuation เต็ม 3.0
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    result = screener.screen_one("GOOD", RF)
    assert result is not None
    assert result["ticker"] == "GOOD"
    assert result["fundamental_score"] == pytest.approx(8.0)
    assert result["valuation_score"] == pytest.approx(3.0)
    assert result["score"] == pytest.approx(11.0)
    assert result["tier"] == "strong"
    assert result["gap"] == pytest.approx(-10.0)


def test_screen_one_skips_when_data_gate_fails(monkeypatch):
    stock = _data_gate_fail_stock()
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    assert screener.screen_one("BAD", RF) is None


def test_screen_one_returns_a_partial_row_when_reverse_dcf_cannot_run(monkeypatch):
    """Phase 34 (เปลี่ยนพฤติกรรมจากเดิมที่คืน None): ประเมินราคาไม่ได้ != วิเคราะห์ไม่ได้เลย.

    เดิมทิ้งทั้งตัวเงียบๆ ขณะที่ health.py คืน 'พื้นฐานล้วน /8' ให้ตั้งแต่ Phase 29 — เอนจิ้น
    เดียวกันแต่ตอบคนละอย่างกับหุ้นตัวเดียวกัน. เจอจริงกับ ORCL (FCF เฉลี่ย 3 ปีติดลบจากรอบ capex)
    """
    stock = _strong_cheap_stock(target_growth=0.0)
    stock.market_cap = None                       # -> reverse_dcf() คืน None ตั้งแต่ต้น
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    result = screener.screen_one("NOCAP", RF)

    assert result is not None
    assert result["partial"] is True
    assert result["max"] == 8.0                   # ห้าม normalize ขึ้น /11 = เสกคะแนนราคาที่ไม่มีอยู่
    assert result["score"] == result["fundamental_score"]
    assert result["valuation_score"] is None      # None ไม่ใช่ 0 ที่อ่านว่า 'ขาราคาสอบตก'
    assert result["gap"] is None
    assert result["partial_reason"]               # ต้องบอกเหตุผล ไม่ใช่หายไปเฉยๆ


def test_screen_one_skips_on_fetch_error(monkeypatch):
    def _raise(t):
        raise RuntimeError("network down")
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(_raise)})(),
    )
    assert screener.screen_one("ERR", RF) is None   # ล้มเงียบๆ ไม่ raise (1 ตัวพังไม่ทำ scan ตาย)


def test_run_screen_sorts_by_score_descending_and_skips_bad(monkeypatch):
    stocks = {
        "CHEAP": _strong_cheap_stock(target_growth=-0.05),    # score ~11.0
        "FAIR": _strong_cheap_stock(target_growth=0.12),      # valuation ~1.0 -> score ~9.0
        "GATE_FAIL": _data_gate_fail_stock(),                  # ถูกข้าม
    }

    def _fake_get(ticker):
        return stocks[ticker]

    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(_fake_get)})(),
    )
    monkeypatch.setattr("src.agent.screener.get_risk_free_rate_pct", lambda: RF)

    results = screener.run_screen(tickers=list(stocks.keys()))
    assert [r["ticker"] for r in results] == ["CHEAP", "FAIR"]   # GATE_FAIL ถูกข้าม, เรียงคะแนนมาก->น้อย
    assert results[0]["score"] > results[1]["score"]


# --- cache (screen()) ---

def test_screen_reads_fresh_cache_without_rescanning(monkeypatch, tmp_path):
    cache_path = tmp_path / "screener_cache.json"
    cache_path.write_text('{"computed_at": 123.0, "results": [{"ticker": "CACHED"}]}', encoding="utf-8")
    monkeypatch.setattr("src.agent.screener._CACHE_PATH", cache_path)

    def _boom():
        raise AssertionError("ไม่ควรสแกนใหม่เมื่อ cache ยังสด")
    monkeypatch.setattr("src.agent.screener.run_screen", _boom)

    data = screener.screen(force=False)
    assert data["results"] == [{"ticker": "CACHED"}]


def test_screen_force_rescans_even_with_fresh_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "screener_cache.json"
    cache_path.write_text('{"computed_at": 123.0, "results": [{"ticker": "OLD"}]}', encoding="utf-8")
    monkeypatch.setattr("src.agent.screener._CACHE_PATH", cache_path)
    monkeypatch.setattr("src.agent.screener.run_screen", lambda: [{"ticker": "NEW"}])

    data = screener.screen(force=True)
    assert data["results"] == [{"ticker": "NEW"}]
    assert cache_path.exists()   # เขียนทับ cache ใหม่แล้ว


def test_screen_rescans_when_cache_stale(monkeypatch, tmp_path):
    import time
    cache_path = tmp_path / "screener_cache.json"
    cache_path.write_text('{"computed_at": 1.0, "results": [{"ticker": "OLD"}]}', encoding="utf-8")
    old_time = time.time() - (screener._CACHE_TTL_HOURS + 1) * 3600
    import os
    os.utime(cache_path, (old_time, old_time))
    monkeypatch.setattr("src.agent.screener._CACHE_PATH", cache_path)
    monkeypatch.setattr("src.agent.screener.run_screen", lambda: [{"ticker": "NEW"}])

    data = screener.screen(force=False)
    assert data["results"] == [{"ticker": "NEW"}]


# ── Phase 33.3: ธนาคารใน screener ต้องใช้เลนส์ราคาเดียวกับ health ────────────
# ถ้าไม่แก้: _fundamental_score จับได้ว่าเป็นแบงก์แล้วให้คะแนนด้วยเกณฑ์ธนาคาร แต่ขาราคายังเรียก
# reverse_dcf ซึ่งอ่าน FCF ของแบงก์ไม่ได้ -> คืน None -> แบงก์หายไปจาก screener เงียบๆ ทั้งที่
# health ให้ 10.6/11 = สองพาธที่อ้างว่าใช้ 'เอนจิ้นเดียวกัน' ตอบคนละอย่างสำหรับหุ้นตัวเดียวกัน

class _FakeBank:
    """ธนาคารแบบย่อ: FCF ติดลบมหาศาลตามธรรมชาติของธุรกิจ (ปล่อยสินเชื่อ) — reverse_dcf ต้องไม่ถูกใช้."""
    free_cash_flow = -147_782_000_000.0
    market_cap = 935_128_203_264.0
    fcf_series: list = []
    revenue_series: list = []
    revenue = 181_847_000_000.0
    revenue_cagr = 12.5
    net_debt = 156_644_000_000.0
    beta = 0.977
    capex = None
    depreciation_amortization = 8_821_000_000.0
    nwc_change = -218_801_000_000.0
    nopat = None
    roic = None
    fcf_margin = None

    def to_facts(self):
        from src.domain.interfaces import Fact
        rows = [
            ("Revenue", 181_847_000_000.0, "USD", "FY2025"),
            ("Net Interest Income", 95_443_000_000.0, "USD", "FY2025"),
            ("ROTCE", 20.53, "%", "FY2025"),
            ("Equity / Assets", 8.19, "%", "FY2025"),
            ("NII / Assets", 2.16, "%", "FY2025"),
            ("Cost+Provision / Revenue", 61.04, "%", "FY2025"),
            ("Revenue CAGR", 12.5, "%", "FY2025"),
            ("P/B", 2.6448984, "x", "FY2025"),
            ("Beta", 0.977, "x", "FY2025"),
            ("ROE", 15.74, "%", "FY2025"),
            ("Net Margin", 31.37, "%", "FY2025"),
            ("Diluted Shares", 2_781_500_000.0, "shares", "FY2025"),
            ("Diluted Shares", 2_879_000_000.0, "shares", "FY2024"),
        ]
        return [Fact(label=a, value=b, unit=c, period=d) for a, b, c, d in rows]


def test_screener_scores_a_bank_instead_of_dropping_it(monkeypatch):
    monkeypatch.setattr(
        screener.StockFundamentalsProvider, "get_fundamentals",
        lambda self, ticker: _FakeBank(),
    )
    result = screener.screen_one("JPM", 4.0)

    assert result is not None
    assert result["lens"] == "bank_pb"
    assert result["valuation_score"] > 0
    # เลนส์ธนาคารไม่มี growth gap -> ต้องเป็น None ไม่ใช่ 0 ที่อ่านว่า 'ราคาตรงมูลค่าพอดี'
    assert result["gap"] is None and result["implied_growth"] is None


# ---------- Phase 34: partial rows ต้องเห็นได้ แต่ห้ามปนอันดับ ----------

def _fcf_negative_stock() -> FakeStock:
    """ทรง ORCL จริง: พื้นฐานคำนวณได้ปกติ แต่ FCF ฐานติดลบ -> reverse-DCF ใช้ไม่ได้."""
    stock = _strong_cheap_stock(target_growth=0.0)
    stock.fcf_series = [("FY2023", -1_000.0), ("FY2024", -2_000.0), ("FY2025", -3_000.0)]
    stock.free_cash_flow = -3_000.0
    return stock


def test_partial_rows_are_listed_after_every_full_row(monkeypatch):
    """8/8 ไม่ได้แปลว่าดีกว่า 10/11 — เรียงปนกันเมื่อไหร่ 'อันดับ' ก็โกหกทั้งที่ตัวเลขถูกทุกตัว."""
    full = _strong_cheap_stock(target_growth=0.0)
    partial = _fcf_negative_stock()
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(
            lambda t: partial if t == "BURN" else full)})(),
    )
    monkeypatch.setattr(screener, "get_risk_free_rate_pct", lambda: RF)

    rows = screener.run_screen(["BURN", "GOOD", "ALSO"])
    assert [r["partial"] for r in rows] == [False, False, True]
    assert rows[-1]["ticker"] == "BURN"


def test_a_cash_burning_company_is_shown_not_hidden(monkeypatch):
    """bias ที่ผิดทิศที่สุดสำหรับเครื่องมือ 'ค้นหาตัวใหม่' คือซ่อนบริษัทที่กำลังลงทุนหนัก
    โดยที่ไม่มีใครรู้ว่าถูกซ่อน — ให้เห็นแล้วตัดสินเอง"""
    stock = _fcf_negative_stock()
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    result = screener.screen_one("BURN", RF)

    assert result is not None and result["partial"] is True
    assert "FCF" in result["partial_reason"]


def test_a_full_row_still_reports_both_legs(monkeypatch):
    """กันการแก้ครั้งนี้ไปทำให้เคสปกติเปลี่ยนรูป — แถวเต็มต้องเหมือนเดิมทุกช่อง."""
    stock = _strong_cheap_stock(target_growth=0.0)
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    result = screener.screen_one("GOOD", RF)

    assert result["partial"] is False
    assert result["max"] == 11.0
    assert result["partial_reason"] is None
    assert result["score"] == round(result["fundamental_score"] + result["valuation_score"], 2)


def test_a_stock_that_fails_the_data_gate_is_still_dropped(monkeypatch):
    """partial คือ 'ขาราคาไม่ได้' เท่านั้น — พื้นฐานคำนวณไม่ได้ยังต้องหายไปเหมือนเดิม
    ไม่งั้นจะกลายเป็นคะแนนที่เสกจากข้อมูลที่ไม่มี"""
    stock = _data_gate_fail_stock()
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    assert screener.screen_one("BAD", RF) is None


def test_screener_and_health_agree_on_the_same_partial_stock(monkeypatch):
    """หัวใจของงานนี้: สองพาธที่อ้างว่าใช้เอนจิ้นเดียวกัน ต้องให้ตัวเลขเดียวกันจริงๆ."""
    from types import SimpleNamespace

    from src.agent.health import compute_health

    stock = _fcf_negative_stock()
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    from_screener = screener.screen_one("BURN", RF)
    summary = SimpleNamespace(sentiment="neutral", fundamental_strength="strong",
                              valuation_view="fair", price=1.0)
    from_health = compute_health(summary, facts=stock.to_facts(), risk_free_pct=RF)

    assert from_screener["partial"] == from_health["partial"] is True
    assert from_screener["max"] == from_health["max"]
    assert round(from_screener["score"], 1) == from_health["score"]
