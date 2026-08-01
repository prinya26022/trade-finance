"""ตัวแปลข้ออ้าง (Phase 31) — ฉีด LLM ปลอม ไม่แตะ Gemini.

หัวใจที่ต้องพิสูจน์: ด่านตรวจ deterministic ของเรา *ไม่เชื่อ* LLM — ข้อเสนอที่อ้างเมตริกไม่มีจริง
หรือแปลงเป็นเงื่อนไขตัวเลขไม่ได้ ต้องถูกลดชั้น ไม่ใช่ปล่อยผ่านไปเป็น expectation ที่ 'วัดไม่ได้'
ตลอดกาล. และข้ออ้างที่ผิดไม่ได้ต้องถูกแสดงว่าตกด้วยเหตุผลอะไร ไม่ใช่หายไปเงียบ ๆ.
"""
from datetime import date, timedelta

import pytest

from src.agent.claims import ClaimExtraction, ClaimProposal, extract_claims

METRICS = ["Operating Margin", "Revenue CAGR", "FCF Margin", "Net Margin"]


def _fake_llm(*proposals: ClaimProposal):
    def generate(prompt: str):
        return ClaimExtraction(proposals=list(proposals))
    return generate


def _p(**kw):
    base = {"claim": "รายได้จะโตแรงต่อ", "kind": "checkable", "why": "แปลงเป็นตัวเลขได้",
            "metric": "Revenue CAGR", "op": ">=", "value": 20.0,
            "by": (date.today() + timedelta(days=200)).isoformat()}
    base.update(kw)
    return ClaimProposal(**base)


def test_checkable_proposal_passes_through():
    out = extract_claims("บลาๆ", "AMZN", METRICS, generate=_fake_llm(_p()))
    p = out["proposals"][0]

    assert p["kind"] == "checkable"
    assert p["metric"] == "Revenue CAGR" and p["op"] == ">=" and p["value"] == 20.0
    assert p["deadline_defaulted"] is False
    assert out["counts"]["checkable"] == 1


def test_invented_metric_is_downgraded_not_trusted():
    """กับดักหลัก: LLM แต่งชื่อเมตริกเก่งมาก ถ้าปล่อยผ่านจะได้ expectation ที่ขึ้น 'วัดไม่ได้' ตลอดไป."""
    out = extract_claims("บลาๆ", "AMZN", METRICS,
                         generate=_fake_llm(_p(metric="AWS Segment Revenue Growth")))
    p = out["proposals"][0]

    assert p["kind"] == "needs_data"
    assert p["metric"] == ""          # ไม่ส่งชื่อเมตริกปลอมต่อไปให้ผู้ใช้กดบันทึก
    assert "AWS Segment Revenue Growth" in p["why"]


def test_bad_operator_is_downgraded():
    out = extract_claims("บลาๆ", "AMZN", METRICS, generate=_fake_llm(_p(op="≈")))
    assert out["proposals"][0]["kind"] == "needs_data"


def test_missing_value_is_downgraded():
    out = extract_claims("บลาๆ", "AMZN", METRICS, generate=_fake_llm(_p(value=None)))
    assert out["proposals"][0]["kind"] == "needs_data"


def test_missing_deadline_is_filled_but_flagged():
    """ไม่มีเส้นตาย = ไม่มีวันผิด — เติมค่าเริ่มต้นให้ใช้ต่อได้ แต่ต้องบอกว่าเราเติมเอง."""
    out = extract_claims("บลาๆ", "AMZN", METRICS, generate=_fake_llm(_p(by="")))
    p = out["proposals"][0]

    assert p["kind"] == "checkable"
    assert p["deadline_defaulted"] is True
    assert date.fromisoformat(p["by"]) > date.today()


def test_unfalsifiable_claim_is_kept_and_explained():
    """คุณค่าหลักคือ 'เห็นว่ามีกี่ข้อที่วัดไม่ได้' — ห้ามกรองทิ้งเงียบ ๆ."""
    out = extract_claims("บลาๆ", "TSM", METRICS, generate=_fake_llm(
        _p(claim="ลงไปก็ไม่ขาดทุน", kind="unfalsifiable", why="ไม่มีตัวเลขไหนพิสูจน์ว่าผิดได้",
           metric="", op="", value=None, by="")))
    p = out["proposals"][0]

    assert p["kind"] == "unfalsifiable"
    assert p["why"]
    assert out["counts"]["unfalsifiable"] == 1
    assert "ผิดไม่ได้" in out["kind_labels"]["unfalsifiable"]


def test_timing_and_factual_kinds_survive_vetting():
    out = extract_claims("บลาๆ", "CVX", METRICS, generate=_fake_llm(
        _p(claim="ระยะสั้นโอเค", kind="timing", metric="", op="", value=None, by=""),
        _p(claim="ASML ผูกขาดเครื่อง EUV", kind="factual", metric="", op="", value=None, by="")))

    assert [p["kind"] for p in out["proposals"]] == ["timing", "factual"]
    assert out["counts"] == {"timing": 1, "factual": 1}


def test_mixed_batch_counts_every_kind():
    out = extract_claims("บลาๆ", "AMZN", METRICS, generate=_fake_llm(
        _p(),
        _p(claim="AWS จะโต", metric="AWS Revenue"),
        _p(claim="ของมันดี", kind="unfalsifiable", metric="", op="", value=None, by=""),
    ))
    assert out["counts"] == {"checkable": 1, "needs_data": 1, "unfalsifiable": 1}
    assert len(out["proposals"]) == 3


def test_empty_text_rejected_before_calling_llm():
    called = []

    def generate(prompt):
        called.append(prompt)
        return ClaimExtraction(proposals=[])

    with pytest.raises(ValueError):
        extract_claims("   ", "AMZN", METRICS, generate=generate)
    assert called == []      # ไม่เผาโควตากับข้อความว่าง


def test_llm_returning_nothing_raises_clearly():
    with pytest.raises(RuntimeError, match="parse"):
        extract_claims("บลาๆ", "AMZN", METRICS, generate=lambda p: None)


def test_prompt_contains_only_real_metrics():
    """LLM ต้องเห็นรายชื่อเมตริกจริงเท่านั้น — นี่คือสิ่งที่ทำให้มันไม่ต้องเดาชื่อเอง."""
    seen = {}

    def generate(prompt):
        seen["prompt"] = prompt
        return ClaimExtraction(proposals=[])

    extract_claims("บลาๆ", "AMZN", METRICS, generate=generate)
    for m in METRICS:
        assert m in seen["prompt"]
    assert "AMZN" in seen["prompt"]

# ---- ค่าปัจจุบันต้องอยู่ใน prompt (กันตั้งเป้าผิดหน่วย — เจอจริงตอน verify) ----

def test_prompt_shows_current_values_so_thresholds_match_scale():
    """เคสจริง: ให้แค่ชื่อเมตริก โมเดลตอบ 'Revenue > 700000' ให้ AMZN ทั้งที่ fact เก็บเป็น 6.4e11
    (คิดเป็นหน่วยล้าน) -> expectation ที่ 'เข้าเป้า' ตลอดกาล = ไม่มีวันผิด ซึ่งค้านกับทั้งฟีเจอร์."""
    seen = {}

    def generate(prompt):
        seen["prompt"] = prompt
        return ClaimExtraction(proposals=[])

    rich = [{"label": "Revenue", "value": 637959000000.0, "unit": "USD", "period": "FY2025"},
            {"label": "Operating Margin", "value": 11.2, "unit": "%", "period": "FY2025"}]
    extract_claims("บลาๆ", "AMZN", rich, generate=generate)

    assert "637,959,000,000" in seen["prompt"]   # เห็นสเกลจริง ไม่ใช่ 6.37959e+11
    assert "11.2" in seen["prompt"]
    assert "SAME UNIT AND SCALE" in seen["prompt"]


def test_rich_metrics_still_validate_by_label():
    rich = [{"label": "Revenue", "value": 1.0, "unit": "USD", "period": "FY2025"}]
    ok = extract_claims("บลาๆ", "AMZN", rich, generate=_fake_llm(_p(metric="Revenue")))
    bad = extract_claims("บลาๆ", "AMZN", rich, generate=_fake_llm(_p(metric="Revenue CAGR")))

    assert ok["proposals"][0]["kind"] == "checkable"
    assert bad["proposals"][0]["kind"] == "needs_data"   # label ไม่อยู่ในชุดที่มีจริง
