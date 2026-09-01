"""Phase 49 — เรดาร์ห่วงโซ่การเงิน AI. Offline ล้วน: ไม่แตะ yfinance/เน็ต/DB จริงเลย.

สิ่งที่เทสต์ชุดนี้คุ้มครองจริงๆ ไม่ใช่ 'โค้ดไม่ crash' แต่คือ **ความซื่อสัตย์ของเรดาร์**:
- ข้อมูลขาด ต้องกลายเป็น 'วัดไม่ได้' พร้อมเหตุผล ไม่ใช่ 'ปกติดี'
- ตัวที่หายไปจากตะกร้า ห้ามถูกนับเป็น 0% (ซึ่งจะทำให้ตะกร้าดูนิ่งกว่าความจริง)
- margin ต้องอ่านทางเดียวกันทุกสัญญาณ ('+ = แย่ลง') แม้สัญญาณจะกลับทิศกัน
- มุมอับต้องเดินทางไปกับรายงานทุกฉบับ
"""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.aicapex import radar, signals as sig, store
from src.aicapex.fetch import TickerData
from src.aicapex.notify import _distance, _gauge, format_report


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


# ---------- รูปแบบข้อความ: สิ่งที่ทำให้อ่านต่อ (แก้ 2026-09 หลังฟีดแบ็ก "อ่านลำบาก") ----------

def test_the_decisive_signal_is_stated_before_any_of_the_others():
    """ฉบับแรกเปิดด้วยรายการ 7 ข้อน้ำหนักเท่ากันหมด คนอ่านต้องประกอบข้อสรุปเอง — ซึ่งแปลว่า
    ส่วนใหญ่จะไม่ประกอบ. ข้อเครดิตข้อเดียวสำคัญกว่าอีก 6 ข้อรวมกัน เพราะมันคือตัวที่เปลี่ยน
    'งบดุลน่ากังวล' ให้เป็น 'ผิดนัดชำระจริง' — จึงต้องอยู่เหนือรายการ ไม่ใช่ลำดับที่ 5"""
    text = format_report(radar.build_report(data=_sample_data(), previous={}))
    head = text.split("**1.")[0]          # ทุกอย่างก่อนบทแรก

    assert "ตัวชี้ขาด" in head
    assert "ส่วนต่างเครดิต" in head


def test_the_gauge_groups_colours_so_it_reads_before_the_words_do():
    """สีที่สลับกันไปมาต้องนับทีละอัน ส่วนสีที่จับกลุ่มอ่านได้ทันที"""
    signals = [sig.Signal("a", "x", sig.OK, 1, "", 1, 2, ""),
               sig.Signal("b", "x", sig.ALERT, 1, "", 1, 2, ""),
               sig.Signal("c", "x", sig.OK, 1, "", 1, 2, ""),
               sig.Signal("d", "x", sig.ALERT, 1, "", 1, 2, "")]

    assert _gauge(signals) == "🔴🔴🟢🟢"


def test_every_signal_belongs_to_exactly_one_chapter():
    """สัญญาณที่ตกหล่นจากบทจะหายไปจากรายงานเงียบๆ — เพิ่มสัญญาณใหม่แล้วลืมจัดบท
    คือวิธีที่ง่ายที่สุดที่จะทำให้เรดาร์ตาบอดโดยไม่มีใครรู้"""
    keys = {fn({}).key for fn in sig.SIGNALS}

    assert keys == set(sig.CHAPTER_OF)
    assert set(sig.CHAPTER_OF.values()) <= {k for k, _ in sig.CHAPTERS}


def test_the_decisive_key_names_a_signal_that_actually_exists():
    """ถ้าเปลี่ยนชื่อ key แล้วลืมแก้ DECISIVE พาดหัวจะหายไปเงียบๆ ทั้งที่เป็นบรรทัดสำคัญสุด"""
    assert sig.DECISIVE in {fn({}).key for fn in sig.SIGNALS}


def test_a_count_signal_does_not_claim_a_distance_to_the_line():
    """'เกินเส้นมา 1 ราย' ไม่มีความหมาย — บริษัทเป็นจำนวนเต็ม จะเฉียดเส้นครึ่งบริษัทไม่ได้"""
    counted = sig.Signal("k", "l", sig.ALERT, 2, "ราย", 1, 2, "")
    measured = sig.Signal("k", "l", sig.ALERT, 4.16, "เท่า", 2.0, 3.5, "")

    assert _distance(counted) == ""
    assert "เกินเส้นมา" in _distance(measured)


def test_blind_spots_collapse_on_quiet_days_but_open_when_something_changed():
    """5 บรรทัดเดิมทุกวันคือตัวที่ฝึกให้คนเลื่อนผ่าน — แล้ววันที่มีของจริงก็จะโดนเลื่อนผ่านด้วย
    แต่ตัดทิ้งไม่ได้เพราะเป็นส่วนหนึ่งของความซื่อสัตย์ จึงย่อวันเงียบ กางวันที่คนจะอ่านจริง"""
    quiet = radar.build_report(data=_sample_data(),
                               previous={s.key: {"state": s.state, "value": s.value}
                                         for s in radar.build_report(data=_sample_data(),
                                                                     previous={}).signals})
    tuesday, monday = date(2026, 9, 1), date(2026, 8, 31)

    assert "กางเต็มทุกวันจันทร์" in format_report(quiet, today=tuesday)
    assert "ค่าเช่า GPU" in format_report(quiet, today=monday)          # วันจันทร์กางเต็ม


def test_a_day_with_a_state_change_always_shows_the_full_blind_spots():
    """วันที่สถานะเปลี่ยนคือวันที่คนจะอ่านจริง — ต้องเห็นข้อจำกัดครบตอนกำลังจะตัดสินใจ"""
    changed = radar.build_report(data=_sample_data(),
                                 previous={"hyperscaler_fcf": {"state": "alert", "value": 3}})
    assert changed.changes, "ฉากทดสอบต้องมีการเปลี่ยนสถานะจริง"

    assert "ค่าเช่า GPU" in format_report(changed, today=date(2026, 9, 1))   # อังคาร แต่กางเต็ม


def _measurable_data() -> dict:
    """ฉากที่วัดได้ครบพอให้มีระยะห่างเส้นจริง — ต่างจาก _sample_data ที่ตั้งใจให้ขาดบางส่วน"""
    return {**_sample_data(),
            "HYG": _td("HYG", closes=_closes(100, 102)),
            "LQD": _td("LQD", closes=_closes(100, 100)),
            "CRWV": _td("CRWV", total_debt_q=[35.15e9, 29.82e9], equity_q=[4.76e9],
                        closes=_closes(100, 75))}


def test_an_unmeasurable_decisive_signal_is_never_reported_as_having_flipped():
    """บั๊กที่เทสต์ชุดนี้จับได้ (2026-09): เดิมเขียน `if ok -> เขียว else -> พลิกแล้ว` ทำให้
    วันไหนดึงราคา HYG/LQD ไม่ได้ พาดหัวจะขึ้น 🚨 เต็มจอทั้งที่ไม่มีอะไรเกิดขึ้น
    สัญญาณเตือนเท็จบนบรรทัดสำคัญที่สุด คือวิธีเร็วที่สุดที่จะทำให้คนเลิกเชื่อทั้งฉบับ"""
    blind = {k: v for k, v in _sample_data().items() if k not in ("HYG", "LQD")}

    text = format_report(radar.build_report(data=blind, previous={}))

    assert "พลิกแล้ว" not in text
    assert "วัดไม่ได้รอบนี้" in text
    assert "ไม่ใช่ 'ยังปลอดภัย'" in text     # ไม่รู้ ต้องไม่ถูกอ่านเป็นปลอดภัย


def test_the_report_never_prints_a_raw_threshold_as_a_bare_number():
    """'(เส้นที่ 2)' เป็นหน่วยของเครื่องมือ ไม่ใช่หน่วยที่คนใช้ตัดสินใจ — กฎเดียวกับที่
    เจ้าของตั้งไว้ตอน Phase 43 หลังอ่านรายงานฉบับแรกแล้วไม่เข้าใจ"""
    text = format_report(radar.build_report(data=_measurable_data(), previous={}))

    assert "เส้นที่" not in text
    assert "ห่างเส้น" in text or "เกินเส้นมา" in text


# ---------- รายงานที่หน้าเว็บอ่าน (Phase 49.2) ----------

def test_the_web_payload_carries_the_chapter_and_the_decisive_flag():
    """หน้าเว็บต้องไม่ต้องรู้เรื่องโดเมนเองว่าข้อไหนสำคัญกว่า — ถ้าให้ frontend ตัดสิน
    ความสำคัญเอง วันที่แก้ลำดับความสำคัญใน backend หน้าเว็บจะเงียบๆ ไม่ตาม"""
    r = radar.build_report(data=_sample_data(), previous={})
    payload = r.to_dict()

    decisive = [s for s in payload["signals"] if s["decisive"]]
    assert [s["key"] for s in decisive] == [sig.DECISIVE]
    assert all(s["chapter"] for s in payload["signals"])
    assert payload["blind_spots"], "มุมอับต้องเดินทางไปกับ payload ด้วย ไม่ใช่แค่ข้อความ Discord"


def test_the_payload_says_whether_each_number_moved_since_last_run():
    """'-28.78 pp' ตัวเดียวอ่านแล้วไม่รู้ว่าดีขึ้นหรือแย่ลง ซึ่งเป็นคำถามแรกที่คนถามเสมอ"""
    prev = {"hyperscaler_fcf": {"state": "watch", "value": 1.0}}

    payload = radar.build_report(data=_sample_data(), previous=prev).to_dict(prev)
    fcf = next(s for s in payload["signals"] if s["key"] == "hyperscaler_fcf")

    # _sample_data ให้ทั้ง 4 รายมี FCF เป็นบวก -> นับได้ 0 ราย จาก 1 รายรอบก่อน = ดีขึ้น 1
    assert fcf["previous_value"] == 1.0
    assert (fcf["value"], fcf["delta"]) == (0, -1.0)


def test_a_signal_with_no_previous_value_reports_no_delta_rather_than_zero():
    """delta = 0 แปลว่า 'วัดแล้วไม่ขยับ' ส่วน None แปลว่า 'ยังไม่เคยวัด' — คนละเรื่อง
    ถ้าปนกัน หน้าเว็บจะเขียน 'ไม่ขยับ' ให้กับสัญญาณที่เพิ่งเห็นครั้งแรก"""
    payload = radar.build_report(data=_sample_data(), previous={}).to_dict({})

    assert all(s["delta"] is None for s in payload["signals"])


def test_the_stored_report_is_the_same_one_that_went_to_discord(tmp_path):
    """เว็บกับ Discord ต้องพูดตรงกันเสมอ — ถ้าเว็บดึงข้อมูลเองคนละรอบ ตัวเลขสองที่จะต่างกัน
    แล้วไม่มีใครรู้ว่าอันไหนจริง ซึ่งแย่กว่าไม่มีหน้าเว็บ"""
    db = tmp_path / "aicapex.db"
    report = radar.build_report(data=_sample_data(), previous={})

    store.save_report(report.to_dict(), db_path=db)
    saved = store.latest_report(db_path=db)

    assert saved is not None
    assert saved["run_at"] == report.run_at
    assert [s["key"] for s in saved["signals"]] == [s.key for s in report.signals]


def test_the_web_is_told_plainly_when_the_radar_has_never_run(tmp_path):
    """หน้าว่างที่ไม่มีคำอธิบาย อ่านได้เหมือน 'ทุกอย่างปกติ' ซึ่งเป็นคำกล่าวอ้างที่เราไม่มีสิทธิ์พูด"""
    assert store.latest_report(db_path=tmp_path / "never-run.db") is None


def test_history_comes_back_oldest_first_so_a_trend_line_reads_left_to_right(tmp_path):
    db = tmp_path / "aicapex.db"
    base = datetime(2026, 8, 1, 9, 0, 0)
    for i, v in enumerate([1.0, 2.0, 3.0]):
        store.record([sig.Signal("k1", "l", sig.OK, v, "", 3.0, 5.0, "")],
                     db_path=db, now=base + timedelta(days=i))

    pts = store.history_for("k1", db_path=db)

    assert [p["value"] for p in pts] == [1.0, 2.0, 3.0]
