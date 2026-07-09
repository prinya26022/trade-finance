"""Cross-day change detection (Phase 3) — pure logic, ไม่แตะ DB/network."""
from src.agent.changes import _fy_int, _latest_by_label, _metric_changes, _diff


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


def _row(strength="strong", valuation="fair", news=None, facts_ratio=1.0, facts=None):
    return {
        "summary": {
            "fundamental_strength": strength,
            "valuation_view": valuation,
            "thesis_relevant_news": news or [],
        },
        "facts_grounded_ratio": facts_ratio,
        "facts": facts or [],
    }


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
