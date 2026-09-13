"""Phase 50 — ผูกเรดาร์เข้ากับพอร์ต. Offline ล้วน (ฉีด portfolio/watchlist เข้าไป ไม่แตะ DB).

สิ่งที่เทสต์ชุดนี้คุ้มครองคือ **ความซื่อสัตย์ของการจัดกลุ่ม** ไม่ใช่แค่เลขบวกถูก:
- ticker ที่ยังไม่เคยจัด ต้องไม่ตกไปเป็น "ไม่เกี่ยว" เงียบๆ
- "ข้อเท็จจริง" กับ "ความเห็นของเรา" ต้องแยกกันได้จากตัวข้อมูล ไม่ใช่จากความจำของคนอ่าน
- ฝั่งที่ได้ประโยชน์ต้องไม่ถูกบวกรวมกับฝั่งที่เจ็บ จนกลายเป็น "% เกี่ยวกับ AI" ที่ไร้ความหมาย
"""
import pytest

from src.aicapex import exposure as ex
from src.aicapex.universe import BENCHMARKS, HYPERSCALERS


def _portfolio(*positions, total_value=1000.0):
    return {"positions": list(positions), "total_value": total_value}


def _pos(ticker, weight=None, market_value=None):
    return {"ticker": ticker, "weight": weight, "market_value": market_value}


def _watch(ticker, status="watching"):
    return {"ticker": ticker, "status": status}


# ---------- ข้อเท็จจริง vs ความเห็น ----------

def test_membership_in_the_radar_universe_is_a_fact_not_a_judgement():
    """ตัวที่งบของมันเป็นวัตถุดิบของสัญญาณจริงๆ ตรวจได้ด้วยการเช็คสมาชิก ไม่ต้องตีความ —
    ต้องติดธง objective เพื่อให้หน้าเว็บแยกมันออกจากความเห็นของเราได้"""
    c = ex.classify("MSFT")

    assert c["level"] == ex.MEASURED
    assert c["objective"] is True
    assert c["layer"] is not None


def test_everything_that_is_not_measured_is_flagged_as_our_opinion():
    """ตารางที่ดูน่าเชื่อเท่ากันหมดจะทำให้การตัดสินใจของเราถูกอ่านเป็นข้อมูล"""
    for t in ("ASML", "ADBE", "DUOL", "TSLA", "AAPL", "JPM", "CVX", "SBUX", "MA", "BTC"):
        c = ex.classify(t)
        assert c["objective"] is False, t
        assert c["reason"], f"{t} ต้องมีเหตุผลกำกับ ไม่งั้นเถียงกับมันไม่ได้"


def test_a_benchmark_is_not_counted_as_being_in_the_chain():
    """SPY/HYG/LQD อยู่ใน universe ของเรดาร์ในฐานะ *ตัวเทียบ* ไม่ใช่ผู้เล่นในห่วงโซ่ —
    ถ้านับรวม จะได้ว่า 'ตลาดทั้งตลาดคือห่วงโซ่ AI' ซึ่งจริงแต่ไร้ประโยชน์"""
    for t in BENCHMARKS:
        assert ex.classify(t)["level"] != ex.MEASURED, t


# ---------- โหมดพังที่เงียบที่สุด ----------

def test_an_unknown_ticker_is_unclassified_rather_than_declared_harmless():
    """'ยังไม่ได้ดู' กับ 'ดูแล้วไม่เกี่ยว' เป็นคนละคำกล่าวอ้าง — ถ้าปนกัน วันที่เพิ่ม ticker
    ใหม่เข้า watchlist แล้วลืมจัดกลุ่ม มันจะขึ้นว่าปลอดภัยเงียบๆ ซึ่งมองไม่เห็นเลย"""
    c = ex.classify("ZZZZ")

    assert c["level"] == ex.UNCLASSIFIED
    assert c["level"] != ex.UNRELATED
    assert c["direction"] == "unknown"


def test_unclassified_weight_is_reported_separately_not_folded_into_either_side():
    """นับตัวที่ไม่รู้เข้าฝั่งใดฝั่งหนึ่ง = แกล้งว่ารู้"""
    out = ex.build_exposure(_portfolio(_pos("ZZZZ", weight=40.0), _pos("DUOL", weight=60.0)), [])

    assert out["holdings"]["unclassified_pct"] == 40.0
    assert out["holdings"]["hurt_pct"] == 0.0
    assert out["holdings"]["helped_pct"] == 60.0


def test_a_position_with_no_share_count_is_named_rather_than_silently_dropped():
    """ไม่ใส่จำนวนหุ้น = คิดน้ำหนักไม่ได้ ซึ่งทำให้ % ทั้งหมดไม่ครบพอร์ตจริง
    ถ้าไม่บอก คนอ่านจะคิดว่า 100% ที่เห็นคือทั้งพอร์ต"""
    out = ex.build_exposure(_portfolio(_pos("NVDA", weight=None)), [])

    assert out["holdings"]["positions_without_weight"] == ["NVDA"]


# ---------- ทิศทางสำคัญกว่าขนาด ----------

def test_the_two_directions_are_never_added_together():
    """ถ้า capex หด ฝั่งที่ขายของให้การก่อสร้างรายได้หาย ส่วนฝั่งที่จ่ายค่าคอมพิวต์ต้นทุนถูกลง
    การรวมเป็น '% ที่เกี่ยวกับ AI' ก้อนเดียวกลบข้อมูลที่สำคัญที่สุดทิ้ง"""
    out = ex.build_exposure(
        _portfolio(_pos("NVDA", weight=30.0), _pos("ASML", weight=20.0), _pos("DUOL", weight=50.0)),
        [])
    h = out["holdings"]

    assert h["hurt_pct"] == 50.0      # NVDA (วัดตรง) + ASML (ขายของให้)
    assert h["helped_pct"] == 50.0    # DUOL (จ่ายค่าคอมพิวต์)
    assert "ai_pct" not in h and "exposure_pct" not in h


@pytest.mark.parametrize("ticker, direction", [
    ("NVDA", "hurt"), ("MSFT", "hurt"), ("ASML", "hurt"),
    ("DUOL", "helped"), ("ADBE", "helped"), ("TSLA", "helped"),
    ("SBUX", "none"), ("ZZZZ", "unknown"),
])
def test_each_ticker_carries_which_way_a_capex_cut_would_push_it(ticker, direction):
    assert ex.classify(ticker)["direction"] == direction


def test_the_software_names_are_on_the_paying_side_not_the_selling_side():
    """ประเด็นที่ง่ายที่สุดที่จะอ่านผิด: ADBE/DUOL ถูกเรียกว่า 'หุ้น AI' เหมือนกัน แต่ความเสี่ยง
    AI ของมันคือ 'ถูกแทนที่' ไม่ใช่ 'capex หด' — capex หดแปลว่าค่า GPU ถูกลง = ดีกับมัน"""
    for t in ("ADBE", "DUOL"):
        c = ex.classify(t)
        assert c["level"] == ex.BUYS_FROM, t
        assert c["direction"] == "helped", t


# ---------- พอร์ตจริงกับ watchlist ----------

def test_holdings_and_watchlist_are_kept_apart_because_only_one_costs_money():
    """ความเสี่ยงกระจุกตัวเป็นเรื่องของสิ่งที่ **ถือ** ไม่ใช่สิ่งที่ **ดู** — รวมกันเมื่อไหร่
    ตัวเลขจะบอกว่าเสี่ยงหนักทั้งที่ยังไม่ได้ลงเงินสักบาท"""
    out = ex.build_exposure(
        _portfolio(_pos("DUOL", weight=100.0)),
        [_watch("NVDA"), _watch("MSFT"), _watch("DUOL", status="holding")])

    assert [r["ticker"] for r in out["holdings"]["rows"]] == ["DUOL"]
    watched = {r["ticker"] for r in out["watchlist"]["rows"]}
    assert watched == {"NVDA", "MSFT"}         # DUOL ไม่ถูกนับซ้ำ


def test_an_empty_portfolio_reports_zero_without_pretending_that_means_safe():
    out = ex.build_exposure(_portfolio(total_value=None), [_watch("NVDA")])

    assert out["holdings"]["rows"] == []
    assert out["holdings"]["hurt_pct"] == 0.0
    assert out["watchlist"]["rows"], "ยังต้องบอกได้ว่าถ้าซื้อตามที่จับตาอยู่จะเจอกับอะไร"


def test_holdings_are_ordered_by_weight_so_the_biggest_risk_reads_first():
    out = ex.build_exposure(
        _portfolio(_pos("SBUX", weight=10.0), _pos("NVDA", weight=70.0), _pos("DUOL", weight=20.0)),
        [])

    assert [r["ticker"] for r in out["holdings"]["rows"]] == ["NVDA", "DUOL", "SBUX"]


# ---------- ข้อจำกัดต้องเดินทางไปกับตัวเลข ----------

def test_the_caveats_travel_with_every_result():
    """ตัวเลข % อ่านเหมือนของที่วัดมา ทั้งที่การจัดกลุ่มเป็นความเห็น และขนาดของผลกระทบ
    เรายังตอบไม่ได้เลย — ข้อจำกัดจึงต้องอยู่ใน payload ไม่ใช่ใน docstring"""
    out = ex.build_exposure(_portfolio(_pos("DUOL", weight=100.0)), [])
    blob = " ".join(out["caveats"])

    assert "ความเห็น" in blob
    assert "10-K" in blob          # ต้องบอกว่าขนาดของผลกระทบต้องใช้ข้อมูลที่เรายังไม่มี


def test_every_hyperscaler_in_the_radar_is_recognised_by_the_classifier():
    """ถ้าเพิ่ม ticker เข้า universe ของเรดาร์แล้วตัวจัดกลุ่มไม่รู้จัก หน้าเว็บจะบอกว่า
    'ยังไม่ได้จัดกลุ่ม' ทั้งที่เรดาร์วัดมันอยู่ทุกวัน — สองส่วนของระบบเดียวกันเถียงกันเอง"""
    for t in HYPERSCALERS:
        assert ex.classify(t)["level"] == ex.MEASURED, t
