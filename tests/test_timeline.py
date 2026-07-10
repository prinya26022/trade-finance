"""Company biography timeline (Phase 14) — ทดสอบ logic จุดพลิกพื้นฐาน (deterministic) +
narrate ด้วย generate ปลอม. ไม่แตะ EDGAR/Gemini/network."""
from src.domain.interfaces import Fact
from src.agent.timeline import _fundamental_inflections, narrate_timeline


def _facts(label, series, unit="%"):
    """สร้าง list[Fact] ของ 1 metric จาก [(period, value), ...]."""
    return [Fact(label, v, unit, p) for p, v in series]


def test_margin_drop_flagged():
    facts = _facts("Operating Margin", [("FY2023", 15.3), ("FY2024", 14.1), ("FY2025", 9.6)])
    events = _fundamental_inflections(facts, {})
    # FY24->FY25 หด 4.5pp >= 3 -> flag; FY23->FY24 หดแค่ 1.2 -> ไม่ flag
    details = [e["detail"] for e in events]
    assert any("9.6% (FY2025)" in d and "หดลง" in d for d in details)
    assert not any("FY2024" in d for d in details)


def test_margin_jump_up_also_flagged():
    facts = _facts("Net Margin", [("FY2024", 5.0), ("FY2025", 12.0)])
    events = _fundamental_inflections(facts, {})
    assert any("พุ่งขึ้น" in e["detail"] and e["label"] == "Net Margin" for e in events)


def test_small_change_not_flagged():
    facts = _facts("Gross Margin", [("FY2024", 40.0), ("FY2025", 41.5)])  # +1.5 < 3
    assert _fundamental_inflections(facts, {}) == []


def test_revenue_decline_flagged_from_xbrl():
    xbrl = {"Revenues": [("FY2023", 1000.0), ("FY2024", 1100.0), ("FY2025", 950.0)]}
    events = _fundamental_inflections([], xbrl)
    rev = [e for e in events if e["label"] == "Revenue"]
    assert len(rev) == 1                    # เฉพาะ FY2025 ที่หด (FY2024 โต ไม่ flag)
    assert "FY2025" in rev[0]["detail"]
    assert "หดตัว" in rev[0]["detail"]


def test_fcf_sign_flip_flagged():
    facts = _facts("Free Cash Flow", [("FY2024", 500.0), ("FY2025", -200.0)], unit="USD")
    events = _fundamental_inflections(facts, {})
    assert any("พลิกเป็นลบ" in e["detail"] for e in events)


def test_fcf_staying_negative_not_flagged():
    # ลบอยู่แล้วทั้งคู่ -> ไม่ใช่ 'จุดพลิก' (ไม่ใช่เหตุการณ์ใหม่)
    facts = _facts("Free Cash Flow", [("FY2024", -100.0), ("FY2025", -200.0)], unit="USD")
    assert _fundamental_inflections(facts, {}) == []


def test_inflection_has_sortable_date():
    facts = _facts("Operating Margin", [("FY2024", 20.0), ("FY2025", 10.0)])
    e = _fundamental_inflections(facts, {})[0]
    assert e["date"] == "2025-12-31"        # ปีงบ -> วันที่ ISO เรียงรวมกับ 8-K ได้
    assert e["kind"] == "fundamental"


def test_narrate_uses_injected_generator(monkeypatch):
    """narrate_timeline ต้องส่ง timeline ที่ build ได้เข้า prompt แล้วคืนผลจาก generate ที่ inject."""
    fake_events = [{"date": "2025-12-31", "kind": "fundamental", "detail": "margin หดลง"}]
    monkeypatch.setattr("src.agent.timeline.build_timeline", lambda t: fake_events)
    captured = {}
    def fake_gen(prompt):
        captured["prompt"] = prompt
        return "  เรื่องเล่าปลอม  "
    out = narrate_timeline("SBUX", generate=fake_gen)
    assert out == "เรื่องเล่าปลอม"           # strip() ทำงาน
    assert "margin หดลง" in captured["prompt"]   # timeline ถูกยัดเข้า prompt จริง


def test_narrate_empty_when_no_events(monkeypatch):
    monkeypatch.setattr("src.agent.timeline.build_timeline", lambda t: [])
    # generate ไม่ควรถูกเรียกเลยถ้าไม่มี event
    out = narrate_timeline("X", generate=lambda p: (_ for _ in ()).throw(AssertionError("ไม่ควรเรียก")))
    assert out == ""