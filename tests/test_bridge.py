"""Phase 52 — สะพานกระทบยอดตอน LLM กับเครื่องยนต์ตอบไม่ตรงกัน. Offline ล้วน.

เคสจริงที่ทำให้เกิดไฟล์นี้ (DUOL 2026-09-24) ถูกใช้เป็นตัวเลขตั้งต้นของเทสต์ทั้งชุด:
  Operating Income 136M · EBITDA 150M · Pretax 182M · ภาษี −232M (ได้คืน)
  -> Net Income 414M **สูงกว่า EBITDA** เพราะกลับรายการสำรองภาษีรอตัดบัญชี
  -> P/E 17.8 ดูถูก แต่ 56% ของตัวหารเป็นเครดิตภาษีก้อนเดียว
  FCF 360M มี SBC 137M + WC 49M อยู่ข้างใน -> EV/FCF วิ่ง 16.8x -> 34.8x แล้วแต่นิยาม
"""
import pytest

from src.agent.bridge import build_bridge, implied_ebitda


def _facts(**over) -> list[dict]:
    base = {
        "P/E": 17.76, "EV/EBITDA": 31.29, "Net Income": 414_065_000,
        "CFO": 387_823_000, "Capex": -27_399_000, "Stock Based Comp": 137_437_000,
        "NWC Change": 49_000_000, "Market Cap": 7_007_138_816,
    }
    base.update(over)
    return [{"label": k, "value": v} for k, v in base.items() if v is not None]


def _valuation(**over) -> dict:
    base = {"ev": 6_064_528_816, "score": 3.0,
            "flags": ["NEGATIVE_REINVESTMENT", "SUSTAINABLE_DIVERGES"]}
    base.update(over)
    return base


def _step(bridge, key):
    return next(s for s in bridge["steps"] if s["key"] == key)


# ---------- EBITDA เป็นค่าอนุมาน และต้องบอกว่าอนุมาน ----------

def test_ebitda_is_derived_from_two_numbers_we_already_store():
    """ดึง EBITDA ตรงๆ ก็ได้ แต่จะมีเฉพาะรอบใหม่ — อนุมานจาก EV ÷ (EV/EBITDA) ทำให้
    บันไดนี้ใช้ได้กับประวัติทั้งหมดทันทีโดยไม่ต้องรอดึงข้อมูลใหม่"""
    assert implied_ebitda({"EV/EBITDA": 31.29}, 6_064_528_816) == pytest.approx(193.8e6, rel=0.01)


def test_a_derived_number_is_labelled_as_derived():
    """ค่าอนุมานที่ไม่บอกว่าอนุมาน จะถูกอ่านเป็นตัวเลขที่บริษัทรายงาน ซึ่งไม่จริง"""
    assert build_bridge(_facts(), _valuation())["ebitda_is_derived"] is True


@pytest.mark.parametrize("ratio, ev", [(None, 6e9), (0, 6e9), (31.29, None)])
def test_ebitda_cannot_be_derived_without_both_halves(ratio, ev):
    assert implied_ebitda({"EV/EBITDA": ratio} if ratio is not None else {}, ev) is None


# ---------- ขั้น 1-3: ตัวเลขในงบ ----------

def test_multiples_that_point_opposite_ways_mean_the_earnings_figure_is_suspect():
    """P/E 17.8 บอกถูก · EV/EBITDA 31.3 บอกแพง — หุ้นตัวเดียวจะทั้งถูกทั้งแพงไม่ได้
    แปลว่าตัวหารตัวใดตัวหนึ่งมีปัญหา ไม่ใช่ว่าตลาดสับสน"""
    assert _step(build_bridge(_facts(), _valuation()), "multiples_agree")["flagged"] is True


def test_multiples_that_agree_raise_nothing():
    b = build_bridge(_facts(**{"P/E": 40.0}), _valuation())

    assert _step(b, "multiples_agree")["flagged"] is False


def test_net_income_above_ebitda_invalidates_every_pe_based_read():
    """เป็นไปไม่ได้จากการดำเนินงาน — ต้องมีรายการใต้เส้น (ของ DUOL คือเครดิตภาษี 232M)"""
    st = _step(build_bridge(_facts(), _valuation()), "ni_above_ebitda")

    assert st["flagged"] is True
    assert "114%" in st["detail"]          # 414 เทียบ EBITDA อนุมาน 193.8
    assert "P/E" in st["means"]


def test_a_normal_company_has_net_income_below_ebitda():
    st = _step(build_bridge(_facts(**{"Net Income": 100_000_000}), _valuation()),
               "ni_above_ebitda")

    assert st["flagged"] is False


def test_fcf_above_ebitda_means_the_cash_leans_on_growth_continuing():
    """FCF ควรต่ำกว่า EBITDA เสมอ (หลังภาษี ดอกเบี้ย capex) — สูงกว่าเมื่อไหร่แปลว่า
    ส่วนเกินมาจาก SBC ที่บวกกลับ หรือเงินรับล่วงหน้า ซึ่งทั้งคู่พึ่งการเติบโต"""
    st = _step(build_bridge(_facts(), _valuation()), "fcf_above_ebitda")

    assert st["flagged"] is True
    assert "SBC" in st["detail"] and "เงินทุนหมุนเวียน" in st["detail"]


# ---------- ขั้น 4 เป็นบริบท ไม่ใช่เหตุผลที่จะเตือน ----------

def test_the_engines_own_guard_flags_are_reported_but_kept_out_of_the_accounting_count():
    """วัดจากข้อมูลจริง: ธง guard ติดกับ 7 ใน 16 ตัว — ถ้านับเป็นเหตุผลโชว์สะพาน
    มันจะขึ้นเกือบทุกตัวแล้วกลายเป็นวอลเปเปอร์ ซึ่งคือปัญหาที่สะพานนี้ถูกสร้างมาแก้"""
    b = build_bridge(_facts(), _valuation())

    assert _step(b, "engine_self_doubt")["flagged"] is True
    assert b["hits"] == 4
    assert b["accounting_hits"] == 3       # ไม่นับข้อ 4


def test_a_clean_company_with_only_a_guard_flag_reports_no_accounting_finding():
    clean = _facts(**{"P/E": 40.0, "Net Income": 100_000_000, "CFO": 120_000_000})

    b = build_bridge(clean, _valuation())

    assert b["accounting_hits"] == 0
    assert b["hits"] == 1                  # เหลือแค่ธงของโมเดลเอง
    assert "การตีความ" in b["conclusion"]


# ---------- บันไดตัวคูณ ----------

def test_the_same_enterprise_value_gives_opposite_verdicts_by_cash_definition():
    """นี่คือหัวใจของทั้งเฟส: ไม่มีใครผิด สองฝั่งแค่ยืนคนละบรรทัดของตารางนี้"""
    ladder = {r["label"]: r["multiple"] for r in build_bridge(_facts(), _valuation())["ladder"]}

    assert ladder["EV / FCF ที่รายงาน"] == pytest.approx(16.8, abs=0.2)
    assert ladder["EV / FCF หัก SBC"] == pytest.approx(27.2, abs=0.3)
    assert ladder["EV / FCF หัก SBC หักเงินทุนหมุนเวียน"] == pytest.approx(34.8, abs=0.5)
    assert ladder["EV / EBITDA"] == pytest.approx(31.3, abs=0.2)


def test_without_sbc_the_ladder_stops_early_and_says_so():
    """แถวที่บันทึกก่อน Phase 52 ไม่มี SBC — ต้องบอกว่าขาด ไม่ใช่เงียบแล้วโชว์แค่บรรทัดเดียว
    เหมือนกับว่านั่นคือคำตอบทั้งหมด"""
    b = build_bridge(_facts(**{"Stock Based Comp": None}), _valuation())

    assert [r["label"] for r in b["ladder"]] == ["EV / FCF ที่รายงาน", "EV / EBITDA"]
    assert any("Stock Based Comp" in m for m in b["missing"])


# ---------- ข้อสรุป ----------

def test_two_or_more_accounting_findings_reach_the_both_are_right_conclusion():
    b = build_bridge(_facts(), _valuation())

    assert "ทั้งสองฝั่งถูก แต่ถูกคนละตัวเลข" in b["conclusion"]


def test_nothing_found_says_so_plainly_instead_of_inventing_a_concern():
    clean = _facts(**{"P/E": 40.0, "Net Income": 100_000_000, "CFO": 120_000_000})

    b = build_bridge(clean, _valuation(flags=[]))

    assert b["hits"] == 0
    assert "ไม่พบจุด" in b["conclusion"]


def test_nothing_to_reconcile_returns_nothing_rather_than_an_empty_box():
    """กล่องว่างอ่านแล้วเหมือน 'ตรวจแล้วไม่เจออะไร' ซึ่งเป็นคำกล่าวอ้างที่เราไม่ได้ทำ"""
    assert build_bridge(_facts(), None) is None
    assert build_bridge([], _valuation()) is None


def test_missing_inputs_are_named_rather_than_silently_skipped():
    b = build_bridge([{"label": "P/E", "value": 17.76}], _valuation(ev=None))

    assert b["missing"], "ต้องบอกว่าคำนวณขั้นไหนไม่ได้เพราะขาดอะไร"
    assert b["ladder"] == []
