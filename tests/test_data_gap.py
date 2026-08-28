"""แยก "ดึงข้อมูลไม่สำเร็จ" ออกจาก "ประเมินมูลค่าไม่ได้" (Phase 39). Offline ล้วน.

เคสจริงที่จุดชนวน: **MA (Mastercard) 2026-07-28** — `.info` คืนมาไม่มี marketCap หนึ่งรอบ
-> EV คำนวณไม่ได้ -> คะแนน 10.0/11 ร่วงเป็น 8.0/8 แล้วเด้งกลับวันถัดมา และเหตุผลที่บันทึกไว้คือ
"ไม่มี Market Cap/FCF พอคำนวณ reverse-DCF — ตัดออกจาก screen นี้" ซึ่งอ่านเหมือนข้อสรุปเรื่อง
บริษัท ทั้งที่เป็นสะดุดของ API หนึ่งครั้ง (JPM เจอ 6 ครั้งใน 17 วัน)

สองอย่างนี้ต่างกันที่ "เจ้าของควรทำอะไรต่อ" คนละทางเลย — อันหนึ่งคือข้อมูลให้ตัดสินใจ อีกอันคือ
สิ่งที่ควรเมิน. เขียนเหมือนกันเมื่อไหร่ อันที่มีความหมายจะถูกกลืนไปกับอันที่ไม่มี
"""
from types import SimpleNamespace

import pytest

from src.agent.health import no_valuation_reason
from src.agent.screener import _partial_reason
from src.providers.stock import fundamentals as fnd


# ---------- ต้นเหตุ: .info ที่คืนมาไม่ครบ ----------

class _FakeTicker:
    """แทน yf.Ticker — นับจำนวนครั้งที่ถูกสร้าง เพื่อพิสูจน์ว่า retry สร้างตัวใหม่จริง."""

    def __init__(self, responses):
        self._responses = responses

    def __call__(self, ticker):
        payload = self._responses.pop(0) if self._responses else {}
        return SimpleNamespace(info=payload)


def test_a_thin_info_response_is_retried_until_it_comes_back_whole(monkeypatch):
    fake = _FakeTicker([{"currency": "USD"}, {"marketCap": 5.0e11, "currency": "USD"}])
    monkeypatch.setattr(fnd.yf, "Ticker", fake)

    assert fnd._fetch_info("MA")["marketCap"] == 5.0e11


def test_each_retry_builds_a_new_ticker_object(monkeypatch):
    """หัวใจของการแก้: yfinance จำผลไว้บน object — เรียก .info ซ้ำบนตัวเดิมจะได้ dict บางใบเดิม
    ทุกครั้ง แล้ว retry จะไม่มีความหมายอะไรเลย. เทสต์นี้คือสิ่งเดียวที่กันการ 'ปรับให้สวย'
    เป็น `t = yf.Ticker(x)` ครั้งเดียวนอกลูปในอนาคต."""
    built: list[str] = []

    def _ticker(name):
        built.append(name)
        return SimpleNamespace(info={} if len(built) < 3 else {"marketCap": 1.0})

    monkeypatch.setattr(fnd.yf, "Ticker", _ticker)

    fnd._fetch_info("MA")

    assert built == ["MA", "MA", "MA"]


def test_it_gives_up_quietly_instead_of_killing_the_whole_run(monkeypatch):
    """หุ้นตัวเดียวดึงไม่ได้ไม่ควรล้มรอบวิเคราะห์ทั้งกระดาน (หลักเดียวกับ loop.py) — คืนเท่าที่ได้
    แล้วให้ปลายทางบอกเองว่านี่คือปัญหาการดึงข้อมูล."""
    monkeypatch.setattr(fnd.yf, "Ticker", lambda name: SimpleNamespace(info={"currency": "USD"}))

    out = fnd._fetch_info("MA", attempts=2)

    assert out == {"currency": "USD"}


def test_an_exception_on_one_attempt_does_not_stop_the_next(monkeypatch):
    calls = {"n": 0}

    def _ticker(name):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("yahoo ล่ม")
        return SimpleNamespace(info={"marketCap": 2.0})

    monkeypatch.setattr(fnd.yf, "Ticker", _ticker)

    assert fnd._fetch_info("MA")["marketCap"] == 2.0


def test_the_canary_is_a_field_that_never_legitimately_missing():
    """beta/PEG/forwardPE หายได้ตามธรรมชาติ (เพิ่ง IPO, ไม่มีนักวิเคราะห์) — ถ้าเอามาเป็นตัวชี้วัด
    retry จะทำงานฟรีทุกวันกับหุ้นที่ปกติดี แล้วรอบวิเคราะห์จะช้าขึ้นสามเท่าโดยไม่ได้อะไร."""
    assert fnd._INFO_CANARY == "marketCap"


# ---------- ปลายทาง: ข้อความต้องบอกความจริงคนละอย่าง ----------

def _obj(market_cap=5.0e11, mismatch=False):
    return SimpleNamespace(market_cap=market_cap, currency_mismatch=mismatch)


def test_a_missing_market_cap_is_named_as_a_fetch_problem():
    """หุ้นที่ซื้อขายอยู่จริงมี market cap เสมอ — ไม่มีเลยแปลว่าเราดึงพลาด."""
    reason, data_gap = no_valuation_reason(_obj(market_cap=None))

    assert data_gap is True
    assert "ดึง" in reason and "ไม่ใช่ข้อสรุป" in reason


def test_a_business_that_genuinely_cannot_be_valued_is_not_called_a_fetch_problem():
    """ORCL (รอบ capex ดาต้าเซ็นเตอร์) กับ SPCX (ยัง burn cash) — FCF ไม่เป็นบวกคือข้อเท็จจริง
    ของธุรกิจ อันนั้นคือคำตอบ ไม่ใช่ความผิดพลาด. ติดป้ายว่า 'ดึงไม่ได้' จะกลบสัญญาณจริง."""
    reason, data_gap = no_valuation_reason(_obj())

    assert data_gap is False
    assert "FCF" in reason


def test_a_currency_mismatch_that_survives_is_now_a_fetch_problem():
    """**เปลี่ยนความหมายโดยตั้งใจใน Phase 45.** ก่อนหน้านี้ 'งบคนละสกุลกับราคา' คือข้อจำกัด
    ถาวรที่เรารู้ตัวและยอมรับ (จึงไม่ใช่ data_gap) — ตอนนี้เราแปลงสกุลได้แล้วถ้าดึงเรตสำเร็จ
    ดังนั้นเคสที่ยังเหลือ mismatch อยู่แปลว่า **ดึงอัตราแลกเปลี่ยนไม่สำเร็จรอบนั้น** ซึ่งคือ
    ปัญหาการดึงข้อมูลที่รอบหน้าอาจหายเอง ไม่ใช่ข้อเท็จจริงเรื่องบริษัท.

    ความต่างนี้สำคัญเพราะมันเปลี่ยนสิ่งที่ผู้ใช้ควรทำ: 'ประเมินไม่ได้' = เอาไปคิดต่อได้เลย
    ส่วน 'ดึงไม่สำเร็จ' = เมินรอบนี้แล้วดูรอบหน้า (หลักเดียวกับที่ Phase 39 วางไว้)."""
    reason, data_gap = no_valuation_reason(_obj(market_cap=None, mismatch=True))

    assert data_gap is True
    assert "สกุลเงิน" in reason and "อัตราแลกเปลี่ยน" in reason


def test_a_dcf_that_ran_but_could_not_score_keeps_its_own_note():
    reason, data_gap = no_valuation_reason(_obj(), {"note": "growth เกินขอบเขตโมเดล"})

    assert data_gap is False and reason == "growth เกินขอบเขตโมเดล"


def test_the_screener_and_the_health_score_give_the_same_answer():
    """บั๊กประจำของโปรเจกต์: สองพาธที่อ้างว่าใช้เอนจิ้นเดียวกัน ตอบคนละอย่างกับหุ้นตัวเดียวกัน
    (33.3 แบงก์, 34 ORCL). คราวนี้ผูกไว้ด้วยฟังก์ชันตัวเดียว — เทสต์นี้คือสิ่งที่กันการแตกอีกครั้ง."""
    for obj, dcf in [(_obj(market_cap=None), None), (_obj(), None),
                     (_obj(mismatch=True), None), (_obj(), {"note": "x"})]:
        assert _partial_reason(dcf, obj) == no_valuation_reason(obj, dcf)


def test_the_health_row_carries_the_flag_not_just_the_wording():
    """หน้าเว็บ/รายงานต้องแยกได้โดยไม่ต้องเดาจากข้อความภาษาไทย — ข้อความมีไว้ให้คนอ่าน
    ส่วนธงมีไว้ให้โค้ดอ่าน."""
    from src.agent.health import _valuation_score

    facts = [{"label": "Free Cash Flow", "value": 1.0e10, "unit": "USD", "period": "FY2025"}]

    out = _valuation_score(facts, risk_free_pct=4.0)

    assert out["excluded"] is True and out["data_gap"] is True


@pytest.mark.parametrize("attempts", [1, 2, 5])
def test_the_attempt_count_is_respected(monkeypatch, attempts):
    built: list[str] = []
    monkeypatch.setattr(fnd.yf, "Ticker",
                        lambda name: (built.append(name), SimpleNamespace(info={}))[1])

    fnd._fetch_info("MA", attempts=attempts)

    assert len(built) == attempts
