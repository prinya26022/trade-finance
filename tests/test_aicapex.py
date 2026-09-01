"""Phase 49 — เรดาร์ห่วงโซ่การเงิน AI. Offline ล้วน: ไม่แตะ yfinance/เน็ต/DB จริงเลย.

สิ่งที่เทสต์ชุดนี้คุ้มครองจริงๆ ไม่ใช่ 'โค้ดไม่ crash' แต่คือ **ความซื่อสัตย์ของเรดาร์**:
- ข้อมูลขาด ต้องกลายเป็น 'วัดไม่ได้' พร้อมเหตุผล ไม่ใช่ 'ปกติดี'
- ตัวที่หายไปจากตะกร้า ห้ามถูกนับเป็น 0% (ซึ่งจะทำให้ตะกร้าดูนิ่งกว่าความจริง)
- margin ต้องอ่านทางเดียวกันทุกสัญญาณ ('+ = แย่ลง') แม้สัญญาณจะกลับทิศกัน
- มุมอับต้องเดินทางไปกับรายงานทุกฉบับ
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.aicapex import radar, signals as sig, store
from src.aicapex.fetch import TickerData
from src.aicapex.notify import format_report


def _closes(start: float, end: float, n: int = 80) -> list[tuple[str, float]]:
    """ราคาปิดที่ไล่เป็นเส้นตรงจาก start ไป end — พอสำหรับทดสอบ % เปลี่ยน"""
    base = datetime(2026, 1, 1)
    return [((base + timedelta(days=i)).date().isoformat(),
             start + (end - start) * i / (n - 1)) for i in range(n)]


def _td(ticker: str, **kw) -> TickerData:
    return TickerData(ticker=ticker, **kw)


def _flat_market(pct_move: float = 0.0) -> dict:
    """ตลาดที่ขยับ pct_move% — ใช้เป็นฉากหลังของสัญญาณเชิงราคา"""
    return {"SPY": _td("SPY", closes=_closes(100.0, 100.0 * (1 + pct_move / 100)))}


# ---------- margin / borderline: กฎการอ่านที่ต้องเหมือนกันทุกสัญญาณ ----------

def test_margin_reads_the_same_direction_on_signals_that_point_opposite_ways():
    """'+ = ข้ามเส้นไปทางที่แย่แล้ว' ต้องจริงทั้งกับสัญญาณที่ยิ่งสูงยิ่งแย่ (หนี้) และยิ่งต่ำ
    ยิ่งแย่ (ส่วนต่างเครดิต) — ไม่งั้นคนอ่านต้องจำเองว่าตัวไหนอ่านกลับด้าน ซึ่งคือที่มาของ
    การอ่านผิด และเป็นบั๊กชนิดที่ไม่มีใครเห็นจนกว่าจะตัดสินใจผิดไปแล้ว"""
    higher_worse = sig.Signal("a", "หนี้", sig.ALERT, 24.7, "%", 10.0, 20.0, "")
    lower_worse = sig.Signal("b", "เครดิต", sig.ALERT, -7.0, "pp", -2.0, -5.0, "")

    assert higher_worse.margin == pytest.approx(14.7)   # เกินเส้น 10 ไป 14.7
    assert lower_worse.margin == pytest.approx(5.0)     # ต่ำกว่าเส้น -2 ไป 5.0 -> บวกเหมือนกัน


def test_a_signal_that_is_safely_clear_of_the_line_gets_a_negative_margin():
    safe = sig.Signal("b", "เครดิต", sig.OK, 2.45, "pp", -2.0, -5.0, "")

    assert safe.margin == pytest.approx(-4.45)
    assert safe.borderline is False


def test_borderline_catches_both_about_to_trip_and_just_tripped():
    """เกือบติดกับเพิ่งติด อ่านต่างกัน แต่ทั้งคู่แปลว่าคำตอบแขวนอยู่บนเกณฑ์ที่เราตั้งเอง
    (แนวคิดเดียวกับ close_call ของ Phase 48 ที่ทำกับเส้น 15pp)"""
    just_under = sig.Signal("x", "l", sig.OK, 9.8, "%", 10.0, 20.0, "")
    just_over = sig.Signal("x", "l", sig.WATCH, 10.5, "%", 10.0, 20.0, "")
    far_over = sig.Signal("x", "l", sig.ALERT, 24.7, "%", 10.0, 20.0, "")

    assert just_under.borderline is True
    assert just_over.borderline is True
    assert far_over.borderline is False


def test_a_signal_with_no_value_has_no_margin_rather_than_a_misleading_zero():
    unknown = sig.Signal("x", "l", sig.UNKNOWN, None, "%", 10.0, 20.0, "", missing="ไม่มีข้อมูล")

    assert unknown.margin is None
    assert unknown.borderline is False


# ---------- สัญญาณจากงบการเงิน ----------

def test_burning_cash_is_counted_not_averaged():
    """เฉลี่ยกระแสเงินสดของทั้งกลุ่มจะกลบรายที่ติดลบด้วยรายที่บวกจัด — คำถามคือ 'มีกี่ราย
    ที่เผาเงิน' ไม่ใช่ 'กลุ่มนี้เผาเงินโดยรวมไหม'"""
    data = {
        "MSFT": _td("MSFT", fcf_q=[19.6e9], quarter_ends=["2026-06-30"]),
        "AMZN": _td("AMZN", fcf_q=[-18.2e9], quarter_ends=["2026-03-31"]),
        "GOOGL": _td("GOOGL", fcf_q=[-5.9e9], quarter_ends=["2026-06-30"]),
        "META": _td("META", fcf_q=[1.7e9], quarter_ends=["2026-06-30"]),
    }

    s = sig.hyperscaler_fcf(data)

    assert (s.value, s.state) == (2, sig.ALERT)
    assert "Amazon" in s.detail and "Alphabet" in s.detail
    assert s.missing is None


def test_missing_financials_become_unmeasurable_and_say_which_ticker():
    """เงียบเรื่องข้อมูลขาด = รายงานว่า 'ปกติดี' ทั้งที่ไม่ได้ตรวจ ซึ่งอันตรายกว่าไม่มีเรดาร์"""
    s = sig.hyperscaler_fcf({t: _td(t) for t in ("MSFT", "AMZN", "GOOGL", "META")})

    assert s.state == sig.UNKNOWN
    assert s.value is None
    assert "MSFT" in (s.missing or "")


def test_partial_data_still_reports_what_it_could_see_and_what_it_could_not():
    data = {"MSFT": _td("MSFT", fcf_q=[-1.0e9], quarter_ends=["2026-06-30"]),
            "AMZN": _td("AMZN")}

    s = sig.hyperscaler_fcf(data)

    assert s.value == 1                    # นับเท่าที่เห็น
    assert "AMZN" in (s.missing or "")     # แต่บอกด้วยว่าไม่ได้เห็นอะไร


def test_capex_to_depreciation_says_how_far_the_future_charge_must_grow():
    data = {"MSFT": _td("MSFT", capex_q=[-35.8e9], da_q=[11.02e9]),
            "GOOGL": _td("GOOGL", capex_q=[-44.9e9], da_q=[7.1e9])}

    s = sig.capex_vs_depreciation(data)

    assert s.value == pytest.approx((35.8 / 11.02 + 44.9 / 7.1) / 2, abs=0.02)
    assert s.state == sig.ALERT
    assert "Alphabet" in s.detail          # ชี้ตัวที่สุดโต่ง ไม่ใช่แค่ค่าเฉลี่ย


def test_leverage_uses_the_worst_borrower_because_defaults_do_not_average():
    """รายเดียวที่ล้มก็พอจะทำให้เจ้าหนี้ตีราคาหลักประกันของทั้งกลุ่มใหม่ — ค่าเฉลี่ยจะซ่อน
    CoreWeave 7.4 เท่า ไว้ใต้เพื่อนอีกสามรายที่ต่ำกว่า 2 เท่า"""
    data = {
        "CRWV": _td("CRWV", total_debt_q=[35.15e9], equity_q=[4.76e9]),   # 7.39
        "NBIS": _td("NBIS", total_debt_q=[9.5e9], equity_q=[7.24e9]),     # 1.31
        "IREN": _td("IREN", total_debt_q=[3.96e9], equity_q=[2.66e9]),    # 1.49
    }

    s = sig.neocloud_leverage(data)

    assert s.value == pytest.approx(7.39, abs=0.01)
    assert s.state == sig.ALERT
    assert "CoreWeave" in s.detail


def test_debt_growth_is_measured_on_the_whole_layer_not_per_company():
    """หนี้ของชั้นนี้เป็นความเสี่ยงร่วม — เจ้าหนี้กลุ่มเดียวกัน หลักประกันชนิดเดียวกัน"""
    data = {
        "CRWV": _td("CRWV", total_debt_q=[35.15e9, 29.82e9]),
        "NBIS": _td("NBIS", total_debt_q=[9.5e9, 4.97e9]),
    }

    s = sig.neocloud_debt_growth(data)

    assert s.value == pytest.approx((44.65 / 34.79 - 1) * 100, abs=0.1)
    assert s.state == sig.ALERT


def test_one_quarter_of_debt_history_is_not_enough_to_claim_a_trend():
    s = sig.neocloud_debt_growth({"CRWV": _td("CRWV", total_debt_q=[35.15e9])})

    assert s.state == sig.UNKNOWN
    assert s.missing is not None


# ---------- สัญญาณจากราคา ----------

def test_a_basket_skips_missing_members_instead_of_scoring_them_flat():
    """นับตัวที่ไม่มีข้อมูลเป็น 0% จะดึงตะกร้าเข้าหาศูนย์ = ตะกร้าดูนิ่งกว่าความจริงเสมอ
    ซึ่งทำให้สัญญาณ 'กลุ่มนี้โดนเท' อ่อนลงเงียบๆ พอดีตอนที่ควรจะดังที่สุด"""
    data = {"CRWV": _td("CRWV", closes=_closes(100, 60)),   # -40%
            "NBIS": _td("NBIS"),                            # ไม่มีข้อมูล -> ต้องข้าม
            "IREN": _td("IREN"), "APLD": _td("APLD")}

    assert sig._basket_change(data, ["CRWV", "NBIS", "IREN", "APLD"], 60) == pytest.approx(
        sig._pct_change(data["CRWV"].closes, 60))


def test_the_levered_basket_is_always_read_against_the_market():
    """'กลุ่มนี้ลง 25%' ไม่มีความหมายถ้าทั้งตลาดลง 25% — ตัวเลขที่ใช้ตัดสินคือส่วนต่าง"""
    data = {**_flat_market(pct_move=-25.0),
            "CRWV": _td("CRWV", closes=_closes(100, 75))}

    s = sig.levered_vs_market(data)

    assert s.value == pytest.approx(0.0, abs=0.6)   # ลงเท่าตลาด = ไม่มีสัญญาณ
    assert s.state == sig.OK


def test_credit_stress_needs_both_sides_of_the_comparison():
    s = sig.credit_stress({"HYG": _td("HYG", closes=_closes(100, 95))})

    assert s.state == sig.UNKNOWN
    assert "LQD" in (s.missing or "")


# ---------- สถานะรวม ----------

def test_the_overall_state_is_the_worst_signal_not_the_average():
    """เฉลี่ยจะกลบสัญญาณเดียวที่กำลังกรีดร้องด้วยอีกหกตัวที่เงียบ"""
    many = [sig.Signal(str(i), "x", sig.OK, 1, "", 1, 2, "") for i in range(6)]

    assert sig.worst_state(many) == sig.OK
    assert sig.worst_state(many + [sig.Signal("z", "x", sig.ALERT, 9, "", 1, 2, "")]) == sig.ALERT


def test_unknown_ranks_above_ok_so_a_blind_radar_never_reads_as_all_clear():
    mixed = [sig.Signal("a", "x", sig.OK, 1, "", 1, 2, ""),
             sig.Signal("b", "x", sig.UNKNOWN, None, "", 1, 2, "")]

    assert sig.worst_state(mixed) == sig.UNKNOWN


# ---------- การเปลี่ยนแปลงข้ามวัน ----------

def _sample_data() -> dict:
    return {**_flat_market(),
            "MSFT": _td("MSFT", fcf_q=[19.6e9], quarter_ends=["2026-06-30"]),
            "AMZN": _td("AMZN", fcf_q=[5.0e9], quarter_ends=["2026-03-31"]),
            "GOOGL": _td("GOOGL", fcf_q=[10.0e9], quarter_ends=["2026-06-30"]),
            "META": _td("META", fcf_q=[1.7e9], quarter_ends=["2026-06-30"])}


def test_the_first_run_is_flagged_so_silence_is_not_read_as_stability():
    """รอบแรกไม่มี changes โดยธรรมชาติ — ถ้าไม่ติดธง ปลายทางจะเขียนว่า 'ไม่มีอะไรเปลี่ยน'
    ทั้งที่ความจริงคือ 'ยังไม่มีอะไรให้เทียบ' ซึ่งเป็นคนละเรื่อง"""
    r = radar.build_report(data=_sample_data(), previous={})

    assert r.first_run is True
    assert r.changes == []


def test_a_state_change_is_reported_with_both_the_before_and_the_after():
    """ต้องเห็นทั้ง 'จากอะไร' และ 'เป็นอะไร' — 'ตอนนี้ alert' อย่างเดียวตอบไม่ได้ว่าเพิ่งพัง
    หรือพังมานานแล้ว ซึ่งเป็นคำถามที่เปลี่ยนการตัดสินใจจริง"""
    # AMZN ติดลบ -> hyperscaler_fcf = watch (1 ราย) ขณะที่รอบก่อนบันทึกไว้ว่า ok
    data = {**_sample_data(), "AMZN": _td("AMZN", fcf_q=[-18.2e9], quarter_ends=["2026-03-31"])}
    prev = {"hyperscaler_fcf": {"state": "ok", "value": 0}}

    r = radar.build_report(data=data, previous=prev)
    changed = {c.key: c for c in r.changes}

    assert "hyperscaler_fcf" in changed, "สถานะเปลี่ยนจริงแต่ไม่ถูกรายงาน"
    assert (changed["hyperscaler_fcf"].before, changed["hyperscaler_fcf"].after) == ("ok", "watch")
    assert changed["hyperscaler_fcf"].worsened is True


def test_a_signal_that_did_not_move_is_not_reported_as_a_change():
    """รายงานรายวันที่ทวนของเดิมทุกวันจะถูกเลื่อนผ่านภายในสัปดาห์เดียว แล้ววันที่มีของจริง
    ก็จะถูกเลื่อนผ่านไปด้วย"""
    prev = {"hyperscaler_fcf": {"state": "ok", "value": 0}}

    r = radar.build_report(data=_sample_data(), previous=prev)

    assert [c.key for c in r.changes if c.key == "hyperscaler_fcf"] == []


def test_a_signal_that_got_worse_is_distinguished_from_one_that_recovered():
    worse = radar.Change("k", "l", before="ok", after="alert", value=1)
    better = radar.Change("k", "l", before="alert", after="ok", value=1)

    assert worse.worsened is True
    assert better.worsened is False


# ---------- state store ----------

def test_the_store_remembers_across_runs_so_change_detection_can_work(tmp_path):
    """ถ้า state ไม่รอดข้ามรัน ทุกรอบจะเป็น 'รอบแรก' แล้วจะไม่มีวันตรวจเจอการเปลี่ยนแปลงเลย
    — โหมดพังที่เงียบสนิท เพราะรายงานยังส่งออกทุกวันเหมือนปกติ"""
    db = tmp_path / "aicapex.db"
    s = [sig.Signal("k1", "l", sig.ALERT, 7.4, "เท่า", 3.0, 5.0, "")]

    store.record(s, db_path=db)

    saved = store.previous_states(db_path=db)
    assert saved["k1"]["state"] == "alert"
    assert saved["k1"]["value"] == pytest.approx(7.4)


def test_how_long_a_condition_has_held_is_answerable_only_from_history(tmp_path):
    """'เพิ่งพัง' กับ 'พังมา 60 วัน' เปลี่ยนการตัดสินใจคนละแบบ — เก็บแค่ค่าล่าสุดตอบไม่ได้"""
    db = tmp_path / "aicapex.db"
    s = [sig.Signal("k1", "l", sig.ALERT, 7.4, "เท่า", 3.0, 5.0, "")]
    base = datetime(2026, 8, 1, 9, 0, 0)
    for i in range(4):
        store.record(s, db_path=db, now=base + timedelta(days=i))

    assert store.days_in_state("k1", "alert", db_path=db) == 3


def test_asking_how_long_for_a_state_it_is_not_in_returns_nothing(tmp_path):
    db = tmp_path / "aicapex.db"
    store.record([sig.Signal("k1", "l", sig.OK, 1.0, "", 3.0, 5.0, "")], db_path=db)

    assert store.days_in_state("k1", "alert", db_path=db) is None


def test_reading_state_before_anything_was_ever_written_self_initialises(tmp_path):
    """CI checkout DB ที่อาจเก่ากว่าสคีมา — ทุก read ต้อง init เองก่อน ไม่งั้นพังเฉพาะบน CI"""
    assert store.previous_states(db_path=tmp_path / "brand-new.db") == {}


# ---------- ความซื่อสัตย์ของข้อความที่ส่งออก ----------

def test_every_report_carries_its_own_blind_spots(tmp_path):
    """มุมอับต้องเดินทางไปกับรายงาน ไม่ใช่อยู่ใน docstring ที่ไม่มีใครเปิดอ่าน — เรดาร์ที่
    ไม่บอกว่ามีมุมอับ อันตรายกว่าไม่มีเรดาร์"""
    text = format_report(radar.build_report(data=_sample_data(), previous={}),
                         db_path=tmp_path / "x.db")

    assert "มองไม่เห็น" in text
    assert "ค่าเช่า GPU" in text          # สัญญาณที่ตรงที่สุดและเราไม่มี ต้องถูกพูดถึงเสมอ
    assert "ไม่ใช่คำแนะนำให้ซื้อ/ขาย" in text


def test_the_first_run_message_says_it_cannot_compare_yet(tmp_path):
    text = format_report(radar.build_report(data=_sample_data(), previous={}),
                         db_path=tmp_path / "x.db")

    assert "รอบแรก" in text
    assert "ไม่มีเงื่อนไขไหนเปลี่ยนสถานะ" not in text


def test_the_report_never_collapses_into_a_single_bubble_score(tmp_path):
    """'ความเสี่ยง 63%' เป็นความแม่นยำปลอมที่เถียงกับมันไม่ได้ — รายงานนี้จึงนับเงื่อนไข
    และชี้ชื่อทีละข้อแทน ตัวเลขเดียวที่มีคือ 'กี่ข้อจากทั้งหมดกี่ข้อ'"""
    r = radar.build_report(data=_sample_data(), previous={})

    assert not hasattr(r, "score")
    assert "เงื่อนไข" in r.summary_line()
    assert str(len(r.signals)) in r.summary_line()
