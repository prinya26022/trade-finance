"""Invalidation checker (Phase 5) — thesis-stop แบบ deterministic.

รันผ่าน tmp_db จริง (thesis + history store) โดยไม่แตะ LLM/network:
seed 1 ผลวิเคราะห์ + 1 thesis ที่มี invalidation rule แล้วเช็คว่า breach โผล่ถูกจังหวะ.
"""
from tests.conftest import save_row


def _seed(tmp_db, op_margin, thesis_rules=None, fair_value=None, price=100.0):
    """บันทึก 1 analysis (มี Operating Margin) + ตั้ง thesis ให้ AAPL."""
    from src.thesis.store import set_thesis
    facts = [{"label": "Operating Margin", "value": op_margin, "unit": "%", "period": "FY2025"}]
    save_row(ticker="AAPL", facts=facts, price=price)
    set_thesis("AAPL", "ถือเพราะแบรนด์แข็ง",
               invalidation=thesis_rules or [], fair_value=fair_value)


def test_breach_when_rule_trips(tmp_db):
    from src.agent.invalidation import check_invalidation
    # rule: ออกถ้า Operating Margin < 10 ; ค่าจริง 8 -> โดนแตะ
    _seed(tmp_db, op_margin=8.0,
          thesis_rules=[{"metric": "Operating Margin", "op": "<", "value": 10, "note": "core profit หลุด"}])
    result = check_invalidation("AAPL")
    breaches = [b for b in result["breaches"] if b["type"] == "invalidation"]
    assert len(breaches) == 1
    assert breaches[0]["severity"] == "alert"
    assert "core profit หลุด" in breaches[0]["detail"]


def test_silent_when_rule_not_tripped(tmp_db):
    from src.agent.invalidation import check_invalidation
    # Operating Margin 31 ไม่ < 10 -> ไม่มี breach (เงียบไว้)
    _seed(tmp_db, op_margin=31.0,
          thesis_rules=[{"metric": "Operating Margin", "op": "<", "value": 10}])
    result = check_invalidation("AAPL")
    assert result["breaches"] == []


def test_missing_metric_skipped_not_breach(tmp_db):
    from src.agent.invalidation import check_invalidation
    # rule อ้างเมตริกที่ไม่มีในงบล่าสุด -> ข้ามเงียบๆ ไม่ใช่ breach
    _seed(tmp_db, op_margin=31.0,
          thesis_rules=[{"metric": "ROIC", "op": "<", "value": 5}])
    result = check_invalidation("AAPL")
    assert result["breaches"] == []


def test_no_margin_safety_when_price_exceeds_fair(tmp_db):
    from src.agent.invalidation import check_invalidation
    # ราคา 100 >= fair value 90 -> margin of safety หาย (severity warn)
    _seed(tmp_db, op_margin=31.0, thesis_rules=[], fair_value=90.0, price=100.0)
    result = check_invalidation("AAPL")
    assert result["no_margin_safety"] is True
    assert any(b["type"] == "no_margin_safety" for b in result["breaches"])


def test_no_thesis_returns_empty(tmp_db):
    from src.agent.invalidation import check_invalidation
    # ไม่มี thesis (แต่ตาราง theses ถูกสร้างแล้วโดย store อื่น) -> ตอบ note ไม่ใช่ error
    save_row(ticker="TSLA", facts=[], price=200.0)
    result = check_invalidation("TSLA")
    assert result["breaches"] == []
    assert result["note"]
