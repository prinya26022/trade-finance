"""Health score (Phase 18: scoring_spec.md — Fundamental/8 + Valuation reverse-DCF/3 +
News/1 = /12, fixed-denominator Piotroski + DISQUALIFY/EXCLUDE instead of LLM fallback) —
pure logic, offline (reverse_dcf() ที่เรียกข้างในเป็น deterministic bisection ล้วนๆ)."""
from types import SimpleNamespace

from src.agent.health import (
    compute_health, _fundamental_score, _valuation_score, _sentiment_points,
    _normalize_facts, _criterion_roic_vs_wacc, _criterion_roe_trend,
    _criterion_fcf_and_accruals, _criterion_revenue_growth, _criterion_leverage,
    _criterion_liquidity, _criterion_margin_improving, _criterion_not_diluting,
    DATA_GATE_MIN_CRITERIA,
)

RF = 4.0  # risk-free % คงที่สำหรับ test (ไม่พึ่ง network)


def _summary(sentiment="bullish"):
    return SimpleNamespace(sentiment=sentiment)


def _fact(label, value, period="", unit=""):
    return {"label": label, "value": value, "unit": unit, "period": period}


# --- criteria เดี่ยวๆ (True/False/None) ---

def test_criterion_roic_vs_wacc():
    # WACC = 4% + 1.0*5.25% = 9.25% (beta ไม่มี -> default 1.0)
    assert _criterion_roic_vs_wacc([_fact("ROIC", 15.0)], RF) is True
    assert _criterion_roic_vs_wacc([_fact("ROIC", 5.0)], RF) is False
    assert _criterion_roic_vs_wacc([], RF) is None


def test_criterion_roic_vs_wacc_uses_beta_when_present():
    # beta สูง -> WACC สูงขึ้น -> ROIC เดิมที่เคยผ่านอาจไม่ผ่าน
    facts = [_fact("ROIC", 10.0), _fact("Beta", 2.5)]   # WACC = 4% + 1.6(cap)*5.25% = 12.4%
    assert _criterion_roic_vs_wacc(facts, RF) is False


def test_criterion_roe_trend_needs_two_years():
    assert _criterion_roe_trend([_fact("ROE", 20.0, "FY2024"), _fact("ROE", 25.0, "FY2025")], RF) is True
    assert _criterion_roe_trend([_fact("ROE", 25.0, "FY2024"), _fact("ROE", 20.0, "FY2025")], RF) is False
    assert _criterion_roe_trend([_fact("ROE", 20.0, "FY2025")], RF) is None


def test_criterion_fcf_and_accruals_both_must_pass():
    facts_pass = [_fact("FCF Margin", 10.0), _fact("CFO", 120.0), _fact("Net Income", 100.0)]
    assert _criterion_fcf_and_accruals(facts_pass, RF) is True
    # CFO < Net Income -> คุณภาพกำไรแย่ -> ไม่ผ่านแม้ FCF Margin เป็นบวก
    facts_fail = [_fact("FCF Margin", 10.0), _fact("CFO", 80.0), _fact("Net Income", 100.0)]
    assert _criterion_fcf_and_accruals(facts_fail, RF) is False
    assert _criterion_fcf_and_accruals([_fact("FCF Margin", 10.0)], RF) is None


def test_criterion_revenue_growth_threshold_is_3pct_not_0():
    assert _criterion_revenue_growth([_fact("Revenue CAGR", 3.5)], RF) is True
    assert _criterion_revenue_growth([_fact("Revenue CAGR", 1.5)], RF) is False   # เดิม (Phase 17) จะผ่านเพราะ >0


def test_criterion_leverage_level_and_trend():
    ok = [_fact("Net Debt / EBITDA", 1.0, "FY2024"), _fact("Net Debt / EBITDA", 0.8, "FY2025")]
    assert _criterion_leverage(ok, RF) is True
    bad_level = [_fact("Net Debt / EBITDA", 4.0, "FY2024"), _fact("Net Debt / EBITDA", 3.5, "FY2025")]
    assert _criterion_leverage(bad_level, RF) is False   # level เกิน 3x แม้ trend ดีขึ้น
    bad_trend = [_fact("Net Debt / EBITDA", 0.5, "FY2024"), _fact("Net Debt / EBITDA", 0.8, "FY2025")]
    assert _criterion_leverage(bad_trend, RF) is False   # level ผ่านแต่หนี้เพิ่มขึ้น
    assert _criterion_leverage([_fact("Net Debt / EBITDA", 1.0, "FY2025")], RF) is None   # ต้อง 2 ปี


def test_criterion_liquidity_level_and_trend():
    ok = [_fact("Current Ratio", 1.5, "FY2024"), _fact("Current Ratio", 1.6, "FY2025")]
    assert _criterion_liquidity(ok, RF) is True
    bad_level = [_fact("Current Ratio", 0.8, "FY2024"), _fact("Current Ratio", 0.9, "FY2025")]
    assert _criterion_liquidity(bad_level, RF) is False
    assert _criterion_liquidity([_fact("Current Ratio", 1.5, "FY2025")], RF) is None


def test_criterion_margin_improving():
    assert _criterion_margin_improving(
        [_fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025")], RF) is True
    assert _criterion_margin_improving(
        [_fact("Operating Margin", 22.0, "FY2024"), _fact("Operating Margin", 20.0, "FY2025")], RF) is False


def test_criterion_not_diluting():
    assert _criterion_not_diluting(
        [_fact("Diluted Shares", 100.0, "FY2024"), _fact("Diluted Shares", 95.0, "FY2025")], RF) is True
    assert _criterion_not_diluting(
        [_fact("Diluted Shares", 95.0, "FY2024"), _fact("Diluted Shares", 100.0, "FY2025")], RF) is False


# --- _fy_series dedup (scalar period ชนกับ series ปีเดียวกัน) ---

def test_fy_series_dedupes_scalar_and_series_collision():
    from src.agent.health import _fy_series
    # ROE มีทั้ง scalar (period=FY2025, ค่า A) และ series (FY2024, FY2025=ค่า B) — series ต้องชนะ
    facts = [_fact("ROE", 999.0, "FY2025"), _fact("ROE", 20.0, "FY2024"), _fact("ROE", 25.0, "FY2025")]
    pts = _fy_series(facts, "ROE")
    assert pts == [("FY2024", 20.0), ("FY2025", 25.0)]   # ไม่ใช่ [("FY2024",20),("FY2025",999),("FY2025",25)]


# --- fundamental score / data gate ---

_FULL_PASS_FACTS = [
    _fact("ROIC", 20.0), _fact("Beta", 1.0),
    _fact("ROE", 20.0, "FY2024"), _fact("ROE", 25.0, "FY2025"),
    _fact("FCF Margin", 10.0), _fact("CFO", 120.0), _fact("Net Income", 100.0),
    _fact("Revenue CAGR", 5.0),
    _fact("Net Debt / EBITDA", 1.0, "FY2024"), _fact("Net Debt / EBITDA", 0.8, "FY2025"),
    _fact("Current Ratio", 1.5, "FY2024"), _fact("Current Ratio", 1.6, "FY2025"),
    _fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025"),
    _fact("Diluted Shares", 100.0, "FY2024"), _fact("Diluted Shares", 95.0, "FY2025"),
]


def test_fundamental_score_all_pass():
    result = _fundamental_score(_FULL_PASS_FACTS, RF)
    assert result["score"] == 8
    assert result["computable"] == 8
    assert result["disqualified"] is False


def test_fundamental_score_disqualifies_below_data_gate():
    # เหลือแค่ 4 เกณฑ์ที่คำนวณได้ (< DATA_GATE_MIN_CRITERIA=6)
    thin_facts = [_fact("ROIC", 20.0), _fact("Revenue CAGR", 5.0),
                  _fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025")]
    result = _fundamental_score(thin_facts, RF)
    assert result["score"] is None
    assert result["disqualified"] is True
    assert result["computable"] < DATA_GATE_MIN_CRITERIA
    assert f"{result['computable']}/8" in result["reason"]


def test_fundamental_score_missing_criterion_counts_as_fail_not_skip():
    # ผ่าน data gate (>=6 คำนวณได้) แต่มี 1 เกณฑ์ที่ไม่ผ่าน -> denominator ยังเป็น 8 เสมอ
    facts = [f for f in _FULL_PASS_FACTS if f["label"] != "ROIC" and f["label"] != "Beta"]
    result = _fundamental_score(facts, RF)
    assert result["computable"] == 7   # ROIC>WACC เช็คไม่ได้ (ไม่มี ROIC)
    assert result["score"] == 7        # /8 เสมอ ไม่ใช่ 7/7


def test_fundamental_score_no_facts_at_all_disqualifies():
    result = _fundamental_score([], RF)
    assert result["score"] is None
    assert result["disqualified"] is True
    assert result["computable"] == 0


# --- valuation (reverse-DCF score, 0-3) ---

def test_valuation_score_excluded_when_no_market_data():
    result = _valuation_score([], RF)
    assert result["score"] is None
    assert result["excluded"] is True


def test_valuation_score_excluded_when_fcf_negative():
    facts = [_fact("Market Cap", 1000.0), _fact("FCF Yield", -5.0)]
    result = _valuation_score(facts, RF)
    assert result["score"] is None
    assert result["excluded"] is True
    assert "burn cash" in result["reason"]


def test_valuation_score_computed_when_data_present():
    facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04), _fact("Revenue CAGR", 15.0)]
    result = _valuation_score(facts, RF)
    assert result["score"] is not None
    assert result["excluded"] is False
    assert 0 <= result["score"] <= 3


# --- sentiment (/1, เหมือน Phase 17) ---

def test_sentiment_points():
    assert _sentiment_points(_summary("bullish"))[0] == 1.0
    assert _sentiment_points(_summary("neutral"))[0] == 0.5
    assert _sentiment_points(_summary("bearish"))[0] == 0.0


# --- compute_health end-to-end ---

def test_compute_health_normal_case():
    valuation_facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04)]
    h = compute_health(_summary("bullish"), None, _FULL_PASS_FACTS + valuation_facts, RF)
    assert h["score"] is not None
    assert h["tier"] in ("strong", "ok", "weak")
    assert h["components"]["strength"] == 8
    assert 0.0 <= h["score"] <= 12.0
    assert round(sum(h["components"].values()), 6) == h["score"]


def test_compute_health_disqualified_when_fundamental_data_thin():
    h = compute_health(_summary(), None, [_fact("ROIC", 20.0)], RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_excluded_when_valuation_unresolvable():
    # fundamental ผ่าน data gate (8/8) แต่ FCF ติดลบ -> valuation excluded -> total ก็ excluded ด้วย
    facts = _FULL_PASS_FACTS + [_fact("Market Cap", 1000.0), _fact("FCF Yield", -5.0)]
    h = compute_health(_summary(), None, facts, RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_crypto_like_facts_disqualified():
    # crypto ไม่มี Fact ที่เกี่ยวข้องกับ Piotroski เลย -> data gate ไม่ผ่านอัตโนมัติ ไม่ต้องเช็ค asset_type แยก
    crypto_facts = [_fact("Market Cap", 500.0, "TTM"), _fact("Volume/Market Cap", 5.0, "TTM")]
    h = compute_health(_summary(), None, crypto_facts, RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_breach_penalizes_and_floors_at_zero():
    valuation_facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", -5.0)]
    # ใช้ facts ที่ fundamental ผ่านแต่ทุกเกณฑ์ fail ให้คะแนนต่ำสุด (0) + valuation ก็ต้อง resolvable
    low_facts = [
        _fact("ROIC", 1.0), _fact("Beta", 1.0),
        _fact("ROE", 25.0, "FY2024"), _fact("ROE", 20.0, "FY2025"),
        _fact("FCF Margin", -5.0), _fact("CFO", 80.0), _fact("Net Income", 100.0),
        _fact("Revenue CAGR", 1.0),
        _fact("Net Debt / EBITDA", 4.0, "FY2024"), _fact("Net Debt / EBITDA", 4.5, "FY2025"),
        _fact("Current Ratio", 0.8, "FY2024"), _fact("Current Ratio", 0.7, "FY2025"),
        _fact("Operating Margin", 22.0, "FY2024"), _fact("Operating Margin", 20.0, "FY2025"),
        _fact("Diluted Shares", 95.0, "FY2024"), _fact("Diluted Shares", 100.0, "FY2025"),
        _fact("Market Cap", 900.0), _fact("FCF Yield", 5.0), _fact("Revenue CAGR", 1.0),
    ]
    breaches = [{"severity": "alert"}]
    h = compute_health(_summary("bearish"), breaches, low_facts, RF)
    assert h["score"] is not None
    assert h["components"]["breach_penalty"] == -3.0
    assert h["score"] >= 0.0   # floored, ไม่ติดลบ


def test_compute_health_json_serializable():
    import json
    valuation_facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04)]
    h = compute_health(_summary(), None, _FULL_PASS_FACTS + valuation_facts, RF)
    json.dumps(h)   # ไม่ raise = pass

    h_excluded = compute_health(_summary(), None, [], RF)
    json.dumps(h_excluded)


def test_normalize_facts_accepts_dataclass_and_dict():
    from src.domain.interfaces import Fact
    dc = [Fact(label="ROIC", value=15.0, unit="%", period="FY2025")]
    d = [{"label": "ROIC", "value": 15.0, "unit": "%", "period": "FY2025"}]
    assert _normalize_facts(dc) == _normalize_facts(d)