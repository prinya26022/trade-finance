"""ด่านตรวจ 'เนื้อ' ของ output จาก LLM (2026-07) — เคสจริง: DUOL รอบ 2026-07-14 ได้
beginner_summary กลับมาเป็น control char U+0019 ล้วน หน้าเว็บขึ้นเป็นสี่เหลี่ยม □.
JSON valid + schema ผ่าน + grounding ผ่านหมด จึงต้องมีด่านตรวจตัวอักษรแยกต่างหาก. Pure, offline.
"""
from src.agent.summarize import Summary, WeakPoint, garbled_reason, scrub


def _summary(**over) -> Summary:
    base = dict(
        ticker="DUOL",
        price=100.0,
        fundamental_strength="strong",
        strength_reasons=["ROIC 76.1% สูงมาก"],
        weak_points=[WeakPoint(area="Valuation", detail="PEG 2.5 ตลาดคาดหวังสูง")],
        valuation_view="fair",
        thesis_relevant_news=[],
        key_news=["Duolingo beats earnings estimates"],   # verbatim อังกฤษ = ปกติ ไม่ใช่ของเสีย
        what_to_watch=["Gross Margin ที่ลดลง"],
        sentiment="neutral",
        confidence=0.8,
        thesis_assessment="",
        beginner_summary="ธุรกิจดีมาก ราคาไม่แพง ข้อควรระวังคือหุ้นเพิ่มทุน",
    )
    return Summary(**{**base, **over})


def test_clean_output_passes():
    assert garbled_reason(_summary()) is None


def test_detects_control_chars_in_beginner_summary():
    # เคส DUOL จริง: อักษรไทยทุกตัวกลายเป็น U+0019
    bad = _summary(beginner_summary="\x19" * 20 + " " + "\x19" * 30)
    assert "control character" in garbled_reason(bad)


def test_detects_control_chars_in_nested_weak_point():
    bad = _summary(weak_points=[WeakPoint(area="Growth", detail="รายได้โต\x19\x19ช้าลง")])
    assert "control character" in garbled_reason(bad)


def test_detects_beginner_summary_not_in_thai():
    # LLM ไม่ทำตาม prompt (ตอบอังกฤษ) -> ต้องจับได้เหมือนกัน ไม่ใช่ปล่อยผ่าน
    bad = _summary(beginner_summary="A great business at a fair price.")
    assert garbled_reason(bad) == "beginner_summary ไม่มีอักษรไทยเลย"


def test_newline_and_tab_are_not_treated_as_garbled():
    ok = _summary(beginner_summary="ธุรกิจดีมาก\nราคาไม่แพง")
    assert garbled_reason(ok) is None


def test_scrub_strips_control_chars_and_drops_empty_items():
    dirty = _summary(
        beginner_summary="ธุรกิจ\x19ดีมาก",
        strength_reasons=["ROIC 76.1% สูง", "\x19\x19\x19"],       # item ที่เหลือแต่ขยะ -> ตัดทิ้ง
        weak_points=[
            WeakPoint(area="Valuation", detail="PEG 2.5\x19 สูง"),
            WeakPoint(area="Growth", detail="\x19\x19"),            # detail ว่าง -> ตัดทั้ง item
        ],
    )
    clean = scrub(dirty)
    assert clean.beginner_summary == "ธุรกิจดีมาก"
    assert clean.strength_reasons == ["ROIC 76.1% สูง"]
    assert [w.detail for w in clean.weak_points] == ["PEG 2.5 สูง"]
    assert garbled_reason(clean) is None          # scrub แล้วต้องสะอาดจริง (ยกเว้นเรื่องภาษา)


def test_scrub_keeps_deterministic_fields_untouched():
    # scrub แตะแค่ 'ข้อความ' — ตัวเลข/verdict ที่ health score ใช้ต้องไม่ถูกแตะเลย
    dirty = _summary(beginner_summary="\x19" * 10)
    clean = scrub(dirty)
    assert (clean.price, clean.sentiment, clean.confidence) == (100.0, "neutral", 0.8)
    assert clean.fundamental_strength == "strong"
    assert clean.key_news == ["Duolingo beats earnings estimates"]