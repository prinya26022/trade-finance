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
