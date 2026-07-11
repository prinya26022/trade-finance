"""Health score (Phase 10 persisted, Phase 17 Piotroski + reverse-DCF grounded) —
pure logic, offline (ไม่แตะ DB/network — reverse_dcf() ที่เรียกใน health.py เป็น
deterministic bisection ล้วนๆ ไม่ยิง Gemini/yfinance)."""
from types import SimpleNamespace

from src.agent.health import (
    compute_health, _strength_points, _valuation_points, _sentiment_points,
    _normalize_facts,
)


def _summary(strength="strong", valuation="fair", sentiment="bullish", confidence=0.9):
    return SimpleNamespace(fundamental_strength=strength, valuation_view=valuation,
                            sentiment=sentiment, confidence=confidence)


def _fact(label, value, period="", unit=""):
    return {"label": label, "value": value, "unit": unit, "period": period}


# --- fallback path (ไม่มี facts พอ -> พึ่ง LLM label ล้วนๆ, เหมือนพฤติกรรมก่อน Phase 17) ---

def test_fallback_best_case_score_near_ceiling():
    h = compute_health(_summary())
    # fallback: strong(5) + fair(2) + bullish(1) + conf(0.9) = 8.9
    assert h["score"] == 8.9
    assert h["tier"] == "strong"
    assert h["label"] == "แข็งแรง"
    assert len(h["reasons"]) == 4   # ไม่มี breach -> ไม่มีเหตุผลที่ 5


def test_fallback_worst_case_score_floor():
    h = compute_health(_summary(strength="weak", valuation="expensive", sentiment="bearish", confidence=0.0))
    # fallback: weak(0) + expensive(0.5) + bearish(0) + conf(0.0) = 0.5
    assert h["score"] == 0.5
    assert h["tier"] == "weak"


def test_breach_penalizes_score_and_is_floored_at_zero():
    breaches = [{"severity": "alert"}]
    h = compute_health(_summary(strength="weak", valuation="expensive", sentiment="bearish", confidence=0.0), breaches)
    assert h["score"] == 0.0   # 0.5 - 3 -> floored ที่ 0 ไม่ติดลบ
    assert "เงื่อนไขออกโดนแตะ (−3)" in h["reasons"]


def test_warn_severity_breach_does_not_penalize():
    breaches = [{"severity": "warn"}]
    h = compute_health(_summary(), breaches)
    assert h["score"] == 8.9
    assert not any("โดนแตะ" in r for r in h["reasons"])


def test_tier_boundaries():
    assert compute_health(_summary(strength="mixed", valuation="fair", sentiment="neutral", confidence=1.0))["tier"] == "ok"
    # mixed(2.5)+fair(2.0)+neutral(0.5)+conf(1.0) = 6.0 -> ok (>=4.5, <7)
    assert compute_health(_summary(strength="strong", valuation="cheap", sentiment="bullish", confidence=1.0))["tier"] == "strong"
    # strong(5)+cheap(3)+bullish(1)+conf(1.0) = 10.0 -> strong


def test_score_is_json_serializable_and_bounded():
    import json
    h = compute_health(_summary())
    json.dumps(h)
    assert 0.0 <= h["score"] <= 10.0


def test_components_sum_equals_score_in_fallback_path():
    h = compute_health(_summary(strength="strong", valuation="cheap", sentiment="bullish", confidence=0.9))
    c = h["components"]
    assert set(c) == {"strength", "valuation", "sentiment", "confidence", "breach_penalty"}
    assert round(sum(c.values()), 6) == h["score"]


def test_components_reflect_breach_penalty():
    breaches = [{"severity": "alert"}]
    h = compute_health(_summary(), breaches)
    assert h["components"]["breach_penalty"] == -3.0


# --- Piotroski-style strength scoring (จากตัวเลขจริงใน facts) ---

def test_strength_all_criteria_pass():
    facts = [
        _fact("ROIC", 15.0), _fact("ROE", 20.0), _fact("FCF Margin", 10.0),
        _fact("Revenue CAGR", 12.0), _fact("Net Debt / EBITDA", 1.0), _fact("Current Ratio", 1.5),
        _fact("Operating Margin", 20.0, "FY2023"), _fact("Operating Margin", 22.0, "FY2024"),
        _fact("Diluted Shares", 100.0, "FY2023"), _fact("Diluted Shares", 95.0, "FY2024"),
    ]
    pts, reason = _strength_points(_summary(), facts)
    assert pts == 5.0
    assert "8/8" in reason


def test_strength_partial_pass_scales_by_computable_only():
    # มีแค่ 4 เกณฑ์ที่เช็คได้ (ROIC ผ่าน, ROE ไม่ผ่าน, growth ไม่ผ่าน, liquidity ผ่าน) -> 2/4
    facts = [
        _fact("ROIC", 15.0), _fact("ROE", 5.0),
        _fact("Revenue CAGR", -2.0), _fact("Current Ratio", 1.2),
    ]
    pts, reason = _strength_points(_summary(), facts)
    assert pts == 2.5   # 5.0 * 2/4
    assert "2/4" in reason


def test_strength_falls_back_to_llm_label_when_no_facts():
    pts, reason = _strength_points(_summary(strength="mixed"), [])
    assert pts == 2.5   # STRENGTH_FALLBACK_PTS["mixed"]
    assert "จาก LLM" in reason


def test_strength_margin_trend_needs_two_fy_points():
    # แค่ 1 จุด (FY เดียว) -> เช็ค 'margin ดีขึ้น' ไม่ได้ -> ข้าม ไม่นับเป็น fail
    facts = [_fact("ROIC", 15.0), _fact("Operating Margin", 20.0, "FY2024")]
    pts, reason = _strength_points(_summary(), facts)
    assert "1/1" in reason   # เหลือแค่ ROIC ที่เช็คได้จริง


def test_normalize_facts_accepts_dataclass_and_dict():
    from src.domain.interfaces import Fact
    dc = [Fact(label="ROIC", value=15.0, unit="%", period="FY2025")]
    d = [{"label": "ROIC", "value": 15.0, "unit": "%", "period": "FY2025"}]
    assert _normalize_facts(dc) == _normalize_facts(d)


# --- reverse-DCF valuation scoring (จากตัวเลขจริงใน facts) ---

def test_valuation_cheap_case_scores_high():
    # market_cap ต่ำเทียบ FCF (ราคาแค่ implied growth -5%) แต่ historical CAGR สูง (15%)
    # -> gap ติดลบมาก -> คะแนนควรสูงเกือบเต็ม (ใกล้ 3)
    facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04), _fact("Revenue CAGR", 15.0)]
    pts, reason = _valuation_points(_summary(), facts)
    assert pts > 2.5
    assert "reverse-DCF" in reason


def test_valuation_expensive_case_scores_low():
    # market_cap สูงเทียบ FCF (implied growth ~40%) แต่ historical CAGR ต่ำ (2%) -> gap บวกมาก
    facts = [_fact("Market Cap", 24333.91), _fact("FCF Yield", 0.41), _fact("Revenue CAGR", 2.0)]
    pts, reason = _valuation_points(_summary(), facts)
    assert pts < 0.5
    assert "reverse-DCF" in reason


def test_valuation_falls_back_when_market_cap_missing():
    pts, reason = _valuation_points(_summary(valuation="cheap"), [_fact("FCF Yield", 5.0)])
    assert pts == 3.0   # VALUATION_FALLBACK_PTS["cheap"]
    assert "จาก LLM" in reason


def test_valuation_falls_back_when_dcf_unresolvable():
    # FCF ติดลบ (fcf_yield ติดลบ) -> reverse_dcf คืน implied_growth=None -> fallback ไป LLM label
    facts = [_fact("Market Cap", 1000.0), _fact("FCF Yield", -5.0)]
    pts, reason = _valuation_points(_summary(valuation="expensive"), facts)
    assert pts == 0.5   # VALUATION_FALLBACK_PTS["expensive"]
    assert "จาก LLM" in reason


# --- sentiment (ลดน้ำหนักเหลือเต็ม 1) ---

def test_sentiment_points_halved_from_original():
    assert _sentiment_points(_summary(sentiment="bullish"))[0] == 1.0
    assert _sentiment_points(_summary(sentiment="neutral"))[0] == 0.5
    assert _sentiment_points(_summary(sentiment="bearish"))[0] == 0.0


# --- end-to-end: facts จริงที่ทำให้ทั้ง strength และ valuation grounded พร้อมกัน ---

def test_compute_health_end_to_end_with_grounded_facts():
    facts = [
        _fact("ROIC", 15.0), _fact("ROE", 20.0), _fact("FCF Margin", 10.0),
        _fact("Revenue CAGR", 15.0), _fact("Net Debt / EBITDA", 1.0), _fact("Current Ratio", 1.5),
        _fact("Market Cap", 905.78), _fact("FCF Yield", 11.04),
    ]
    h = compute_health(_summary(), breaches=None, facts=facts)
    assert round(sum(h["components"].values()), 6) == h["score"]
    # strength grounded (ไม่ fallback) + valuation grounded (reverse-DCF) -> reasons ไม่มีคำว่า 'จาก LLM'
    assert not any("จาก LLM" in r for r in h["reasons"])