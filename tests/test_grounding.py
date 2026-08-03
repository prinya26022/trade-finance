"""Grounding evals (Phase 1-2) — กัน LLM มั่วราคา/ข่าว/ตัวเลขงบ. Pure, offline."""
from types import SimpleNamespace

from src.evals.check_grounding import _extract_numbers, check_facts_grounding, check_grounding


def test_extract_numbers_strips_fiscal_year_and_commas():
    nums = _extract_numbers("Revenue FY2025 grew to 1,234.5 with ROIC 82%")
    assert 2025 not in nums           # FYxxxx ถูกตัดก่อน ไม่ถูกนับเป็นเมตริก
    assert 1234.5 in nums
    assert 82 in nums


def _fact(label, value, unit="%", period="FY2025"):
    return SimpleNamespace(label=label, value=value, unit=unit, period=period)


def test_facts_grounding_all_cited_numbers_real():
    facts = [_fact("ROIC", 82.0), _fact("Operating Margin", 31.5)]
    summary = SimpleNamespace(
        strength_reasons=["ROIC 82% สูงมาก", "Operating Margin 31.5%"],
        weak_points=[],
    )
    result = check_facts_grounding(summary, facts)
    assert result["facts_grounded_ratio"] == 1.0
    assert result["unmatched_numbers"] == []


def test_facts_grounding_flags_hallucinated_number():
    facts = [_fact("ROIC", 82.0)]
    summary = SimpleNamespace(
        strength_reasons=["ROIC 82%"],
        weak_points=[SimpleNamespace(area="Growth", detail="Revenue fell 99%")],  # 99 ไม่มีจริง
    )
    result = check_facts_grounding(summary, facts)
    assert result["facts_grounded_ratio"] < 1.0
    assert 99.0 in result["unmatched_numbers"]


def test_facts_grounding_matches_unit_scaled_numbers():
    # LLM เขียน "16.33 billion", Fact เก็บ 16.33e9 -> ต้อง match ผ่าน candidate *1e9
    facts = [_fact("Free Cash Flow", 16_330_000_000.0, unit="USD")]
    summary = SimpleNamespace(
        strength_reasons=["Free Cash Flow 16.33 billion"],
        weak_points=[],
    )
    result = check_facts_grounding(summary, facts)
    assert result["facts_grounded_ratio"] == 1.0


def test_check_grounding_price_ok():
    summary = SimpleNamespace(price=234.10, key_news=[])
    price = SimpleNamespace(price=234.07)
    result = check_grounding(summary, price, news=[])
    assert result["price_ok"] is True


def test_check_grounding_price_mismatch():
    summary = SimpleNamespace(price=200.0, key_news=[])   # เพี้ยนจากราคาจริงมาก
    price = SimpleNamespace(price=234.07)
    result = check_grounding(summary, price, news=[])
    assert result["price_ok"] is False


def test_check_grounding_news_ratio():
    summary = SimpleNamespace(
        price=100.0,
        key_news=["Apple beats earnings", "Totally made up headline"],
    )
    price = SimpleNamespace(price=100.0)
    news = [SimpleNamespace(title="Apple beats earnings estimates")]
    result = check_grounding(summary, price, news)
    assert result["news_grounded_ratio"] == 0.5   # 1 จาก 2 ที่ตรงข่าวจริง


# ── fix 2026-08: eval ถูกใช้เป็นคะแนน 'ใครแม่นกว่า' ตอนเทียบสองโมเดล แล้วพบว่ามันวัดสไตล์
# การเขียนตัวเลขปนมาด้วย (ดูคอมเมนต์ใน check_grounding.py). เทสต์ชุดนี้ล็อกไว้ว่าเครื่องวัดเที่ยง

def test_thai_scale_units_count_as_grounded():
    """เคสจริง NVDA 2026-08-02: โมเดลเขียน '2.69 หมื่นล้าน' ซึ่งตรงกับ Fact เป๊ะ
    แต่เดิมถูกนับว่าไม่ตรงเพราะไม่มีตัวคูณ 1e10 -> ได้ 50% ทั้งที่ตัวเลขถูกทุกตัว."""
    facts = [_fact("Revenue FY", 26_974_000_000.0, unit="USD"),
             _fact("Revenue", 215_938_000_000.0, unit="USD"),
             _fact("Free Cash Flow", 3_808_000_000.0, unit="USD")]
    summary = SimpleNamespace(
        strength_reasons=["Revenue โตจาก 2.69 หมื่นล้าน USD สู่ 2.15 แสนล้าน USD "
                          "และ Free Cash Flow 3.8 พันล้าน USD"],
        weak_points=[],
    )
    result = check_facts_grounding(summary, facts)
    assert result["facts_grounded_ratio"] == 1.0
    assert result["unmatched_numbers"] == []


def test_scaled_number_does_not_match_a_fact_a_thousand_times_off():
    """หน่วยกำกับชัดแล้วต้องไม่เดาหลักซ้ำอีก — ไม่งั้นการตรวจจะหลวมจนจับการมั่วหลักไม่ได้."""
    facts = [_fact("Revenue", 26_974_000_000.0, unit="USD")]
    summary = SimpleNamespace(
        strength_reasons=["Revenue 2.69 ล้าน USD"],     # ผิดหลักไปสี่พันเท่า
        weak_points=[],
    )
    result = check_facts_grounding(summary, facts)
    assert result["facts_grounded_ratio"] == 0.0


def test_dates_and_form_names_are_not_counted_as_cited_metrics():
    """'8-K วันที่ 2026-06-10' ไม่ใช่การอ้างเมตริก — เดิมกลายเป็นเลขไม่ตรง 4 ตัวรวด
    (หลักเดียวกับที่ตัด FY2025 ทิ้งอยู่แล้ว)."""
    facts = [_fact("ROIC", 82.0)]
    summary = SimpleNamespace(
        strength_reasons=["ROIC 82%"],
        weak_points=[SimpleNamespace(area="Management",
                                     detail="มี 8-K วันที่ 2026-06-10 และ 10-Q วันที่ 2026-04-29")],
    )
    result = check_facts_grounding(summary, facts)
    assert result["unmatched_numbers"] == []
    assert result["cited_count"] == 1          # นับเฉพาะ ROIC 82
