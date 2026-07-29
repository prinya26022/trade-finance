"""เรื่องเล่าที่รอพิสูจน์ (Phase 30) — offline ล้วน.

หัวใจที่ต้องพิสูจน์: ข้ออ้างต้องมีเส้นตาย (ไม่มี = ปฏิเสธตั้งแต่ตอนบันทึก), 'ยังไม่ถึงเป้า'
ไม่ใช่ความผิดจนกว่าจะเลยเส้นตาย, และมันต้องไม่ไปปนกับ invalidation (คนละทิศ คนละ severity).
"""
import pytest

from src.agent.invalidation import _check_expectations
from src.thesis.store import _validate_expectations, set_thesis, get_thesis
from datetime import date, timedelta


def _exp(**kw):
    base = {"claim": "Bedrock ดัน AWS จริง", "metric": "Revenue CAGR", "op": ">=",
            "value": 20.0, "by": "2026-12-31"}
    base.update(kw)
    return base


def _facts(**labels):
    return {label: ("FY2026", v) for label, v in labels.items()}


# ---- validation: บังคับให้ข้ออ้าง 'ผิดได้' ----

def test_rejects_claim_without_deadline():
    with pytest.raises(ValueError, match="ไม่มีวันผิด"):
        _validate_expectations([_exp(by="")])


def test_rejects_unparseable_deadline():
    with pytest.raises(ValueError):
        _validate_expectations([_exp(by="สิ้นปีหน้า")])


def test_rejects_claim_without_measurable_metric():
    with pytest.raises(ValueError, match="metric"):
        _validate_expectations([_exp(metric="")])


def test_keeps_source_for_traceability():
    """ต้องจำได้ว่าข้ออ้างนี้มาจากไหน — ไว้ย้อนดูว่าแหล่งไหนพูดถูกบ่อย."""
    out = _validate_expectations([_exp(source="คลิป YouTube 2026-07-29")])
    assert out[0]["source"] == "คลิป YouTube 2026-07-29"


# ---- สถานะ ----

def test_hit_when_target_reached():
    thesis = {"expectations": [_exp()]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 24.0}), thesis, today=date(2026, 7, 29))[0]
    assert got["status"] == "hit"
    assert got["severity"] == "info"


def test_pending_before_deadline_is_not_a_failure():
    thesis = {"expectations": [_exp()]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 11.0}), thesis, today=date(2026, 7, 29))[0]
    assert got["status"] == "pending"
    assert got["severity"] == "info"     # ยังไม่ถึงเป้า != คิดผิด
    assert got["days_left"] > 0


def test_missed_only_after_deadline_passes():
    thesis = {"expectations": [_exp(by="2026-06-30")]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 11.0}), thesis, today=date(2026, 7, 29))[0]
    assert got["status"] == "missed"
    assert got["severity"] == "warn"     # warn ไม่ใช่ alert — เรื่องเล่าตาย != ต้องขายทันที
    assert got["days_left"] < 0


def test_hit_stays_hit_even_after_deadline():
    thesis = {"expectations": [_exp(by="2026-06-30")]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 25.0}), thesis, today=date(2026, 7, 29))[0]
    assert got["status"] == "hit"


def test_unmeasurable_when_metric_missing():
    """ไม่มีเมตริกในงบ = บอกตรงๆ ว่าวัดไม่ได้ ห้ามเดาว่าเข้าเป้าหรือพลาด."""
    thesis = {"expectations": [_exp(metric="AWS Segment Revenue")]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 25.0}), thesis, today=date(2026, 7, 29))[0]
    assert got["status"] == "unmeasurable"
    assert got["actual"] == "—"


def test_no_expectations_means_empty_not_error():
    assert _check_expectations(_facts(), {"expectations": []}) == []
    assert _check_expectations(_facts(), {}) == []      # thesis เก่าที่ยังไม่มี key นี้


# ---- persistence (คอลัมน์เพิ่มทีหลัง ต้องอ่านของเก่าได้ด้วย) ----

def test_roundtrip_through_store(tmp_db):
    set_thesis("AMZN", "AWS + Bedrock", expectations=[_exp()])
    got = get_thesis("AMZN")
    assert got["expectations"][0]["claim"] == "Bedrock ดัน AWS จริง"
    assert got["invalidation"] == []       # ตั้ง expectations อย่างเดียวได้ ไม่บังคับใส่ rule


def test_old_thesis_without_expectations_still_reads(tmp_db):
    set_thesis("MSFT", "cloud + copilot")
    assert get_thesis("MSFT")["expectations"] == []


def test_deadline_far_future_still_counts_days(tmp_db):
    future = (date.today() + timedelta(days=200)).isoformat()
    thesis = {"expectations": [_exp(by=future)]}
    got = _check_expectations(_facts(**{"Revenue CAGR": 1.0}), thesis)[0]
    assert got["status"] == "pending"
    assert 195 <= got["days_left"] <= 200
