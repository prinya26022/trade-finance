"""fallback chain ข้ามโมเดล (src/agent/llm.py) — ทดสอบด้วย client ปลอม ไม่แตะ Gemini จริง.

เขียนตอน Phase 28 หลังเจอของจริง: gemini-3.5-flash ตอบ 503 'high demand' ต่อเนื่อง แล้วโค้ดเดิม
raise ทิ้งทั้ง chain ทั้งที่อีก 2 โมเดลยังตอบได้ปกติ — ล้มทั้งรอบวิเคราะห์/การสืบฟรีๆ.
"""
import pytest
from google.genai import errors

from src.agent import llm


class FakeAPIError(errors.APIError):
    """APIError ปลอมที่ตั้ง code ได้ตรงๆ (ไม่ต้องสร้าง response จริงจาก SDK)."""
    def __init__(self, code: int):
        self.code = code
        self.message = f"fake {code}"
        self.status = "FAKE"
        Exception.__init__(self, f"fake {code}")


class FakeClient:
    """client ปลอม: กำหนดพฤติกรรมรายโมเดลได้ (error code ที่จะโยน หรือ None = สำเร็จ)."""
    def __init__(self, behaviour: dict[str, int | None]):
        self._behaviour = behaviour
        self.calls: list[str] = []
        outer = self

        class _Models:
            def generate_content(self, model, contents, config=None):
                outer.calls.append(model)
                code = outer._behaviour.get(model)
                if code is not None:
                    raise FakeAPIError(code)
                return f"resp-from-{model}"

        self.models = _Models()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)   # ไม่ต้องรอ backoff จริงในเทสต์


def test_uses_first_model_when_healthy():
    c = FakeClient({})
    assert llm.generate_with_fallback(c, "prompt") == f"resp-from-{llm.MODEL_CHAIN[0]}"
    assert c.calls == [llm.MODEL_CHAIN[0]]                    # ไม่ไปแตะโมเดลอื่นเลย


def test_persistent_5xx_falls_through_to_next_model():
    """หัวใจของ bug fix: 503 ที่ retry ไม่หาย ต้องไปโมเดลถัดไป ไม่ใช่ raise ทิ้งทั้ง chain."""
    first, second = llm.MODEL_CHAIN[0], llm.MODEL_CHAIN[1]
    c = FakeClient({first: 503})

    assert llm.generate_with_fallback(c, "prompt", max_attempts=3) == f"resp-from-{second}"
    assert c.calls == [first, first, first, second]           # retry ครบ 3 ก่อนค่อยเปลี่ยน


def test_429_skips_to_next_model_without_retrying():
    first, second = llm.MODEL_CHAIN[0], llm.MODEL_CHAIN[1]
    c = FakeClient({first: 429})

    assert llm.generate_with_fallback(c, "prompt") == f"resp-from-{second}"
    assert c.calls == [first, second]                          # โควตาเต็ม -> ไม่ retry ซ้ำโมเดลเดิม


def test_permanent_error_raises_immediately():
    """400 = prompt/สคีมาผิดรูป — เปลี่ยนโมเดลก็ไม่ช่วย ต้องเด้งออกทันทีให้เห็นบั๊ก."""
    c = FakeClient({m: 400 for m in llm.MODEL_CHAIN})
    with pytest.raises(errors.APIError):
        llm.generate_with_fallback(c, "prompt")
    assert c.calls == [llm.MODEL_CHAIN[0]]


def test_whole_chain_down_raises_last_error():
    c = FakeClient({m: 503 for m in llm.MODEL_CHAIN})
    with pytest.raises(errors.APIError):
        llm.generate_with_fallback(c, "prompt", max_attempts=2)
    assert c.calls == [m for m in llm.MODEL_CHAIN for _ in range(2)]


def test_models_override_reorders_chain():
    """GeminiPolicy ส่ง chain ที่เรียงโมเดลที่อยากลองก่อนมาเอง."""
    preferred = llm.MODEL_CHAIN[2]
    c = FakeClient({})
    assert llm.generate_with_fallback(c, "p", models=[preferred]) == f"resp-from-{preferred}"
    assert c.calls == [preferred]


# ---- quota lane: งานที่ผู้ใช้กดเอง (ปุ่มสืบ/chat) ต้องไม่กินถังเดียวกับ analyze รายวัน ----

def test_interactive_chain_has_same_models_different_head():
    assert set(llm.INTERACTIVE_CHAIN) == set(llm.MODEL_CHAIN)      # ไม่มีโมเดลไหนหายไปจากเลน
    assert llm.INTERACTIVE_CHAIN[0] != llm.MODEL_CHAIN[0]          # หัวคนละตัว = ทั้งหมดของฟีเจอร์
    assert llm.INTERACTIVE_CHAIN[-1] == llm.MODEL_CHAIN[0]         # โมเดลของงานรายวัน = ตัวสุดท้าย


def test_interactive_lane_spends_its_own_model_first():
    c = FakeClient({})
    llm.generate_with_fallback(c, "p", models=llm.INTERACTIVE_CHAIN)
    assert c.calls == [llm.INTERACTIVE_CHAIN[0]]
    assert llm.MODEL_CHAIN[0] not in c.calls    # ไม่แตะโมเดลของ pipeline รายวันเลยถ้าไม่จำเป็น


def test_interactive_lane_still_falls_back_to_daily_model_as_last_resort():
    """เลนแยกไม่ได้แปลว่าห้ามข้ามเลน — โควตาเลนตัวเองหมดทั้งเลน ค่อยไปยืมของรายวันเป็นตัวสุดท้าย."""
    c = FakeClient({m: 429 for m in llm.INTERACTIVE_CHAIN[:-1]})
    assert llm.generate_with_fallback(c, "p", models=llm.INTERACTIVE_CHAIN) == \
        f"resp-from-{llm.MODEL_CHAIN[0]}"
    assert c.calls[-1] == llm.MODEL_CHAIN[0]