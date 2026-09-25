"""Phase 51 — ป้ายราคาของ LLM ต้องมีเหตุผล และต้องรู้ตัวเมื่อขัดกับเครื่องยนต์. Offline ล้วน.

**ที่มาของเฟสนี้ วัดจากข้อมูลจริงก่อนเขียนโค้ด** (780 คู่วันติดกัน / 597 แถวที่มีทั้งสองฝั่ง):
- `valuation_view` เปลี่ยน 127 ครั้ง และ **88% ของการเปลี่ยนนั้นคะแนนเครื่องยนต์ไม่ขยับเลย**
- ขัดกันคนละขั้ว 68 จาก 597 แถว (11.4%)
- DUOL 2026-09-23 -> 24: ราคาขยับ 1.7% ป้ายพลิก cheap -> expensive ขณะเครื่องยนต์ให้ 3.0/3
  ทั้งสองวัน

โหมดพังเดียวกับที่ Phase 19.3.1 จับ sentiment ได้ ต่างกันแค่ sentiment อยู่ในคะแนนเลยมีคนวัด
ส่วนป้ายนี้อยู่แค่บนหน้าจอ เลยลอยอยู่ได้เป็นเดือนโดยไม่มีใครจับ
"""
import pytest

from src.agent.label_check import CHEAP_AT, EXPENSIVE_AT, engine_view, valuation_conflict
from src.agent.summarize import Summary, engine_price_block


# ---------- แปลคะแนนเป็นป้าย ----------

@pytest.mark.parametrize("score, view", [
    (3.0, "cheap"), (2.5, "cheap"),
    (2.49, "fair"), (1.5, "fair"), (0.51, "fair"),
    (0.5, "expensive"), (0.0, "expensive"),
])
def test_the_engine_score_maps_to_the_same_words_the_llm_uses(score, view):
    """ต้องแปลเป็นคำเดียวกับที่ LLM ใช้ ไม่งั้นเทียบกันไม่ได้เลย — และจุดตัดต้องสมมาตร
    รอบกลางสเกล ไม่ใช่เลือกให้พอดีกับข้อมูลที่มีอยู่"""
    assert engine_view(score) == view


def test_an_engine_that_could_not_compute_is_not_evidence_against_the_llm():
    """ไม่มีอะไรให้เทียบ ก็ไม่มีข้อขัดแย้ง — การนับว่า 'ขัด' ตอนที่เราคำนวณไม่ได้เอง
    คือการโทษอีกฝ่ายด้วยความเงียบของตัวเอง"""
    assert engine_view(None) is None
    assert valuation_conflict("cheap", None) is None


# ---------- ตรวจความขัดแย้ง ----------

def test_opposite_ends_are_flagged_loudly():
    """เคส DUOL จริง: LLM ว่าแพง เครื่องยนต์ให้เต็ม 3.0/3 — อย่างน้อยหนึ่งฝั่งผิดแน่นอน"""
    c = valuation_conflict("expensive", 3.0)

    assert c["level"] == "opposite"
    assert (c["llm_view"], c["engine_view"]) == ("expensive", "cheap")
    assert "3.0" in c["note"]


def test_a_one_step_difference_is_reported_but_not_as_a_contradiction():
    """'แพง' กับ 'พอดี' คือต่างมุมมอง ไม่ใช่เถียงกัน — ถ้าตีเป็นความขัดแย้งเท่ากันหมด
    คำเตือนจะขึ้นตลอดจนไม่มีใครดู แล้ววันที่ขัดกันจริงก็จะถูกเลื่อนผ่าน"""
    c = valuation_conflict("expensive", 1.35)

    assert c["level"] == "off_by_one"


def test_agreement_produces_nothing_at_all():
    assert valuation_conflict("cheap", 3.0) is None
    assert valuation_conflict("fair", 1.5) is None
    assert valuation_conflict("expensive", 0.0) is None


def test_saying_unclear_is_an_honest_answer_not_a_wrong_one():
    """`unclear` แปลว่า 'ตอบไม่ได้' ซึ่งเป็นคำตอบที่ซื่อสัตย์ — คนละเรื่องกับการตอบผิดทาง
    ถ้าติดธงให้ด้วย จะกลายเป็นการลงโทษความซื่อสัตย์"""
    assert valuation_conflict("unclear", 0.0) is None
    assert valuation_conflict(None, 0.0) is None


@pytest.mark.parametrize("score", [CHEAP_AT, EXPENSIVE_AT])
def test_the_cut_points_themselves_are_inside_the_stricter_band(score):
    """จุดตัดพอดีเป๊ะต้องตกฝั่งที่เข้มกว่า ไม่ใช่ฝั่งกลาง — ไม่งั้นค่าที่อยู่บนเส้นพอดี
    จะอ่านได้สองแบบแล้วแต่ทิศที่เข้ามา"""
    assert engine_view(score) in ("cheap", "expensive")


# ---------- prompt ต้องให้ LLM เห็นคำตัดสินของเครื่องยนต์ก่อนตอบ ----------

def test_the_engine_verdict_reaches_the_prompt_with_the_numbers_behind_it():
    """เดิม LLM ตอบเรื่องราคาโดยไม่เคยเห็นผลการคำนวณของระบบเลย ทั้งที่ระบบคำนวณเสร็จอยู่แล้ว
    ในรอบเดียวกัน — สองชั้นจึงพูดคนละเรื่องได้อิสระ"""
    block = engine_price_block({
        "score": 3.0, "implied_growth": 9.61, "realistic_growth": 18.29,
        "gap": -8.68, "lens": "growth", "flags": ["NEGATIVE_REINVESTMENT"],
    })

    assert "3.0" in block
    assert "9.61" in block and "18.29" in block      # ต้องเห็นทั้งสองฝั่งของการเปรียบเทียบ
    assert "NEGATIVE_REINVESTMENT" in block          # รวมถึงเหตุผลที่ระบบไม่ไว้ใจ anchor ตัวเอง


def test_no_engine_verdict_means_no_block_rather_than_an_empty_heading():
    """หัวข้อว่างๆ ใน prompt ทำให้ LLM เดาว่าควรมีอะไรอยู่ตรงนั้น — ไม่มีก็ไม่ต้องใส่"""
    assert engine_price_block(None) == ""
    assert engine_price_block({"score": None}) == ""


# ---------- schema บังคับเหตุผล ----------

def _summary_kwargs(**over):
    base = dict(
        ticker="DUOL", price=150.39, fundamental_strength="strong",
        strength_reasons=["ROIC 76.1% สูงกว่าต้นทุนเงินทุนมาก"], weak_points=[],
        valuation_view="cheap",
        valuation_reason="ตลาด price การเติบโตไว้ 9.6%/ปี ต่ำกว่าที่ข้อมูลรองรับที่ 18.3%/ปี",
        thesis_relevant_news=[], key_news=[], what_to_watch=[], sentiment="neutral",
        confidence=0.9, thesis_assessment="", beginner_summary="ธุรกิจดี ราคายังไม่แพง",
    )
    base.update(over)
    return base


def test_a_price_label_without_a_reason_is_rejected_by_the_schema():
    """ต้นเหตุทั้งหมดคือป้ายนี้เคยเป็น enum เปล่าที่ไม่ต้องรับผิดชอบกับอะไรเลย"""
    kwargs = _summary_kwargs()
    del kwargs["valuation_reason"]

    with pytest.raises(Exception):
        Summary(**kwargs)


def test_the_reason_is_checked_for_garbled_text_like_every_other_written_field():
    """ฟิลด์ใหม่ที่ไม่ถูกใส่ในรายการตรวจ = ช่องที่ข้อความเพี้ยนหลุดออกหน้าจอได้เงียบๆ"""
    from src.agent.summarize import _text_fields

    fields = _text_fields(Summary(**_summary_kwargs(valuation_reason="ทดสอบข้อความ")))

    assert "ทดสอบข้อความ" in fields
