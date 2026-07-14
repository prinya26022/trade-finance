"""Cross-day change detection (Phase 3) — pure logic, ไม่แตะ DB/network."""
from src.agent.changes import _fy_int, _latest_by_label, _metric_changes, _diff, _health_jump_driver


def _fact(label, value, period="FY2025", unit="%"):
    return {"label": label, "value": value, "unit": unit, "period": period}


def test_fy_int_parsing():
    assert _fy_int("FY2025") == 2025
    assert _fy_int("TTM") == -1
    assert _fy_int("") == -1


def test_latest_by_label_picks_newest_period():
    facts = [_fact("Operating Margin", 30.0, "FY2023"),
             _fact("Operating Margin", 32.0, "FY2025"),
             _fact("Operating Margin", 31.0, "FY2024")]
    out = _latest_by_label(facts)
    assert out["Operating Margin"] == ("FY2025", 32.0)


def test_metric_changes_new_filing():
    cur = [_fact("Revenue", 400, "FY2025", "USD")]
    prev = [_fact("Revenue", 380, "FY2024", "USD")]
    changes = _metric_changes(cur, prev)
    assert len(changes) == 1
    assert changes[0]["type"] == "new_filing"
    assert changes[0]["severity"] == "info"


def test_metric_changes_big_move_same_period():
    # งวดเดียวกัน (FY2025) แต่ค่าขยับ >15% (แก้งบย้อนหลัง) -> เตือน metric_move
    cur = [_fact("Operating Margin", 20.0, "FY2025")]
    prev = [_fact("Operating Margin", 30.0, "FY2025")]
    changes = _metric_changes(cur, prev)
    assert len(changes) == 1
    assert changes[0]["type"] == "metric_move"
    assert changes[0]["severity"] == "warn"


def test_metric_changes_silent_on_small_move():
    # ขยับ < 15% ในงวดเดียวกัน = noise -> เงียบ (ปรัชญา alert-only)
    cur = [_fact("Operating Margin", 30.3, "FY2025")]
    prev = [_fact("Operating Margin", 30.0, "FY2025")]
    assert _metric_changes(cur, prev) == []


def test_metric_changes_ignores_nonmaterial_metric():
    # Market Cap ไม่อยู่ใน MATERIAL_METRICS (แกว่งตามราคา = noise) -> ไม่เตือน
    cur = [_fact("Market Cap", 3_000, "FY2025", "USD")]
    prev = [_fact("Market Cap", 2_000, "FY2025", "USD")]
    assert _metric_changes(cur, prev) == []


def _row(strength="strong", valuation="fair", sentiment="bullish", confidence=0.9,
         news=None, facts_ratio=1.0, facts=None, health=None):
    return {
        "summary": {
            "fundamental_strength": strength,
            "valuation_view": valuation,
            "sentiment": sentiment,
            "confidence": confidence,
            "thesis_relevant_news": news or [],
        },
        "facts_grounded_ratio": facts_ratio,
        "facts": facts or [],
        "health": health,
    }


def _health(score, components):
    return {"score": score, "tier": "ok", "label": "พอใช้", "reasons": [], "components": components}


def test_diff_strength_flip_is_alert():
    changes = _diff(_row(strength="weak"), _row(strength="strong"))
    flip = [c for c in changes if c["type"] == "strength_flip"]
    assert len(flip) == 1
    assert flip[0]["severity"] == "alert"


def test_diff_valuation_flip_is_warn():
    changes = _diff(_row(valuation="cheap"), _row(valuation="expensive"))
    assert any(c["type"] == "valuation_flip" and c["severity"] == "warn" for c in changes)


def test_diff_new_thesis_news():
    cur = _row(news=["FDA approval delayed"])
    prev = _row(news=[])
    changes = _diff(cur, prev)
    assert any(c["type"] == "thesis_news" and c["detail"] == "FDA approval delayed" for c in changes)


def test_diff_trust_drop():
    # facts grounding ตกแรง (1.0 -> 0.7) -> เตือนให้ระวังผล
    changes = _diff(_row(facts_ratio=0.7), _row(facts_ratio=1.0))
    assert any(c["type"] == "trust_drop" for c in changes)


def test_diff_silent_when_nothing_material():
    assert _diff(_row(), _row()) == []


def test_diff_health_jump_flagged_with_driver():
    # เคสจริงที่เจอ: MSFT valuation expensive(+0.5) -> cheap(+3) = +2.5 แต้ม ตัวอื่นเท่าเดิม
    prev = _row(valuation="expensive", health=_health(7.4, {
        "strength": 4.0, "valuation": 0.5, "sentiment": 2.0, "confidence": 0.9, "breach_penalty": 0.0,
    }))
    cur = _row(valuation="cheap", health=_health(9.9, {
        "strength": 4.0, "valuation": 3.0, "sentiment": 2.0, "confidence": 0.9, "breach_penalty": 0.0,
    }))
    changes = _diff(cur, prev)
    jumps = [c for c in changes if c["type"] == "health_jump"]
    assert len(jumps) == 1
    assert jumps[0]["severity"] == "warn"
    assert "7.4 → 9.9" in jumps[0]["detail"]
    # Phase 18: valuation ไม่ผูกกับ LLM label (valuation_view) อีกต่อไป (มาจาก reverse-DCF gap
    # แทน) -> ข้อความโชว์แค่ delta ตัวเลข ไม่ใช่ 'expensive→cheap' เหมือนก่อนหน้า
    assert "มุมมองราคา (reverse-DCF) (+2.5)" in jumps[0]["detail"]


def test_diff_health_jump_silent_below_threshold():
    # ขยับแค่ 0.5 แต้ม (confidence ต่างนิดหน่อย) < HEALTH_JUMP_THRESHOLD -> เงียบ
    prev = _row(health=_health(7.9, {
        "strength": 4.0, "valuation": 2.0, "sentiment": 2.0, "confidence": -0.1, "breach_penalty": 0.0,
    }))
    cur = _row(health=_health(8.4, {
        "strength": 4.0, "valuation": 2.0, "sentiment": 2.0, "confidence": 0.4, "breach_penalty": 0.0,
    }))
    changes = _diff(cur, prev)
    assert not any(c["type"] == "health_jump" for c in changes)


def test_diff_health_jump_silent_when_health_missing():
    # แถวเก่าก่อนมี health persisted (Phase 10) -> health เป็น None -> ต้องไม่ crash/ไม่เตือน
    assert _diff(_row(health=None), _row(health=None)) == []


def test_diff_health_jump_silent_when_score_excluded():
    # Phase 18: ticker ที่ 'excluded' (ข้อมูลไม่พอ/ขาดทุน/crypto) score=None แต่ components
    # ยังมี key อยู่ (ค่า None) -> ต้องไม่ crash ตอน None - number
    excluded = {"score": None, "components": {"strength": None, "valuation": None,
                                               "sentiment": 1.0, "breach_penalty": None}}
    normal = _health(7.0, {"strength": 4.0, "valuation": 2.0, "sentiment": 1.0, "breach_penalty": 0.0})
    changes = _diff(_row(health=excluded), _row(health=normal))   # ไม่ raise = pass ครึ่งหนึ่ง
    assert not any(c["type"] == "health_jump" for c in changes)


def test_health_jump_driver_picks_biggest_component():
    ph = {"components": {"strength": 4.0, "valuation": 0.5, "sentiment": 2.0, "confidence": 0.9, "breach_penalty": 0.0}}
    ch = {"components": {"strength": 4.0, "valuation": 3.0, "sentiment": 0.0, "confidence": 0.9, "breach_penalty": 0.0}}
    cs = {"fundamental_strength": "strong", "valuation_view": "cheap", "sentiment": "neutral", "confidence": 0.9}
    ps = {"fundamental_strength": "strong", "valuation_view": "expensive", "sentiment": "bullish", "confidence": 0.9}
    # valuation ขยับ +2.5 (ใหญ่กว่า sentiment -2.0) -> ต้องเลือก valuation เป็นตัวขับ
    driver = _health_jump_driver(ch, ph, cs, ps)
    assert "มุมมองราคา (reverse-DCF) (+2.5)" in driver


def test_health_jump_driver_never_blames_sentiment():
    # Phase 19.3.1: sentiment ไม่กระทบ score แล้ว -> ต้องไม่ถูกเลือกเป็น 'ตัวขับ' อีกต่อไป
    # แม้ตัวเลข delta ของมันจะใหญ่กว่า component อื่นทุกตัวก็ตาม (เคสสมมติ: sentiment แกว่ง
    # bullish->bearish (-1.0) ในขณะที่พื้นฐาน/ราคาขยับแค่ +0.4/+0.4 รวมกันพอให้ threshold ผ่าน)
    ph = {"components": {"strength": 4.0, "valuation": 2.0, "sentiment": 1.0, "breach_penalty": 0.0}}
    ch = {"components": {"strength": 4.4, "valuation": 2.4, "sentiment": 0.0, "breach_penalty": 0.0}}
    cs = {"fundamental_strength": "strong", "valuation_view": "fair", "sentiment": "bearish"}
    ps = {"fundamental_strength": "strong", "valuation_view": "fair", "sentiment": "bullish"}
    driver = _health_jump_driver(ch, ph, cs, ps)
    assert "มุมมองข่าว" not in driver
    assert "พื้นฐาน" in driver or "มุมมองราคา" in driver
