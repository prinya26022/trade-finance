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


def test_screen_one_skips_when_reverse_dcf_none(monkeypatch):
    # market_cap ไม่มีเลย -> reverse_dcf() คืน None ตั้งแต่ต้น -> screen_one ต้องข้าม ไม่ crash
    stock = _strong_cheap_stock(target_growth=0.0)
    stock.market_cap = None
    monkeypatch.setattr(
        "src.agent.screener.StockFundamentalsProvider",
        lambda: type("P", (), {"get_fundamentals": staticmethod(lambda t: stock)})(),
    )
    assert screener.screen_one("NOCAP", RF) is None


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
