"""Health score (persisted, Phase 10) — pure logic, offline. ต้องตรงสูตรกับ web/lib/health.ts."""
from types import SimpleNamespace

from src.agent.health import compute_health


def _summary(strength="strong", valuation="fair", sentiment="bullish", confidence=0.9):
    return SimpleNamespace(fundamental_strength=strength, valuation_view=valuation,
                            sentiment=sentiment, confidence=confidence)


def test_best_case_score_near_ceiling():
    h = compute_health(_summary())
    # strong(4) + fair(2) + bullish(2) + conf(0.9) = 8.9
    assert h["score"] == 8.9
    assert h["tier"] == "strong"
    assert h["label"] == "แข็งแรง"
    assert len(h["reasons"]) == 4   # ไม่มี breach -> ไม่มีเหตุผลที่ 5


def test_worst_case_score_floor():
    h = compute_health(_summary(strength="weak", valuation="expensive", sentiment="bearish", confidence=0.0))
    # weak(0) + expensive(0.5) + bearish(0) + conf(0.0) = 0.5
    assert h["score"] == 0.5
    assert h["tier"] == "weak"


def test_breach_penalizes_score_and_is_floored_at_zero():
    breaches = [{"severity": "alert"}]
    h = compute_health(_summary(strength="weak", valuation="expensive", sentiment="bearish", confidence=0.0), breaches)
    assert h["score"] == 0.0   # 0.5 - 3 -> floored ที่ 0 ไม่ติดลบ
    assert "เงื่อนไขออกโดนแตะ (−3)" in h["reasons"]


def test_warn_severity_breach_does_not_penalize():
    # แค่ 'no_margin_safety' (severity warn) ไม่ใช่ alert -> ไม่หักคะแนน
    breaches = [{"severity": "warn"}]
    h = compute_health(_summary(), breaches)
    assert h["score"] == 8.9
    assert not any("โดนแตะ" in r for r in h["reasons"])


def test_tier_boundaries():
    assert compute_health(_summary(strength="mixed", valuation="fair", sentiment="neutral", confidence=1.0))["tier"] == "ok"
    # 2+2+1+1.0 = 6.0 -> ok (>=4.5, <7)
    assert compute_health(_summary(strength="strong", valuation="cheap", sentiment="bullish", confidence=1.0))["tier"] == "strong"
    # 4+3+2+1.0 = 10.0 -> strong


def test_score_is_json_serializable_and_bounded():
    import json
    h = compute_health(_summary())
    json.dumps(h)   # save_analysis เก็บก้อนนี้เป็น JSON ตรงๆ ต้อง serialize ได้
    assert 0.0 <= h["score"] <= 10.0
