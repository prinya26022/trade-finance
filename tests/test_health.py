"""Health score (Phase 18: scoring_spec.md — Fundamental/8 + Valuation reverse-DCF/3 +
News/1 = /12, fixed-denominator Piotroski + DISQUALIFY/EXCLUDE instead of LLM fallback) —
pure logic, offline (reverse_dcf() ที่เรียกข้างในเป็น deterministic bisection ล้วนๆ).

Phase 19.3: ทุกเกณฑ์คืน float 0.0-1.0 (ไล่ระดับ) แทน True/False — ดู _graded_above/_graded_below
ใน health.py. ค่าที่ห่าง threshold+-band มากๆ ยัง approx 1.0/0.0 เหมือนเดิม (ใช้ pytest.approx
กัน floating point เพี้ยนระดับ 1e-9)."""
from types import SimpleNamespace

import pytest

from src.agent.health import (
    compute_health, _fundamental_score, _valuation_score, _sentiment_points,
    _normalize_facts, _criterion_roic_vs_wacc, _criterion_net_margin_level,
    _criterion_fcf_and_accruals, _criterion_revenue_growth, _criterion_leverage,
    _criterion_solvency, _criterion_margin_improving, _criterion_not_diluting,
    DATA_GATE_MIN_CRITERIA,
)

RF = 4.0  # risk-free % คงที่สำหรับ test (ไม่พึ่ง network)


def _summary(sentiment="bullish"):
    return SimpleNamespace(sentiment=sentiment)


def _fact(label, value, period="", unit=""):
    return {"label": label, "value": value, "unit": unit, "period": period}


# --- criteria เดี่ยวๆ (float 0.0-1.0 ไล่ระดับ, audit fix 19.3 — ดู _graded_above/_graded_below) ---

def test_criterion_roic_vs_wacc():
    # WACC = 4% + 1.0*5.25% = 9.25% (beta ไม่มี -> default 1.0), band=3pp
    assert _criterion_roic_vs_wacc([_fact("ROIC", 15.0)], RF) == pytest.approx(1.0)   # >= WACC+3 -> เต็ม
    assert _criterion_roic_vs_wacc([_fact("ROIC", 5.0)], RF) == pytest.approx(0.0)    # <= WACC-3 -> ศูนย์
    assert _criterion_roic_vs_wacc([_fact("ROIC", 9.25)], RF) == pytest.approx(0.5)   # ตรง WACC เป๊ะ -> กึ่งกลาง
    assert _criterion_roic_vs_wacc([], RF) is None


def test_criterion_roic_vs_wacc_uses_beta_when_present():
    # beta สูง -> WACC สูงขึ้น -> ROIC เดิมที่เคยผ่านอาจไม่ผ่าน
    facts = [_fact("ROIC", 10.0), _fact("Beta", 2.5)]   # WACC = 4% + 1.6(cap)*5.25% = 12.4%
    assert _criterion_roic_vs_wacc(facts, RF) == pytest.approx(0.1)   # (10-9.4)/6 = 0.1 (ใกล้ threshold-band)


def test_criterion_net_margin_level():
    # audit fix 19.2: แทน ROIC-level (ซ้ำกับ #1 ROIC>WACC) ด้วย Net Margin >= 10% —
    # คนละ pipeline คำนวณเต็มๆ จาก ROIC/invested-capital ไม่แชร์ input กันเลย. band=3pp
    assert _criterion_net_margin_level([_fact("Net Margin", 20.0, "FY2025")], RF) == pytest.approx(1.0)
    assert _criterion_net_margin_level([_fact("Net Margin", 10.0, "FY2025")], RF) == pytest.approx(0.5)   # ขอบพอดี = กึ่งกลาง
    assert _criterion_net_margin_level([_fact("Net Margin", 10.83, "FY2025")], RF) == pytest.approx(0.638, abs=1e-3)   # AMZN จริง — ใกล้ threshold เปราะ
    assert _criterion_net_margin_level([_fact("Net Margin", 5.0, "FY2025")], RF) == pytest.approx(0.0)
    assert _criterion_net_margin_level([], RF) is None


def test_criterion_fcf_and_accruals_has_tolerance():
    # audit fix: CFO >= 0.9*NI (tolerance 10%) กัน knife-edge ที่ CFO≈NI. band รอบ ratio=0.05
    # CFO/NI = 0.995 (คล้าย AAPL จริง) -> เดิม fail เพราะ < NI เป๊ะๆ, ตอนนี้ pass เต็ม
    assert _criterion_fcf_and_accruals(
        [_fact("FCF Margin", 22.0), _fact("CFO", 99.5), _fact("Net Income", 100.0)], RF) == pytest.approx(1.0)
    # CFO << NI (แต่งงบจริง) -> ยัง fail เต็ม (ratio 0.7 ห่างจาก 0.85 มาก)
    assert _criterion_fcf_and_accruals(
        [_fact("FCF Margin", 10.0), _fact("CFO", 70.0), _fact("Net Income", 100.0)], RF) == pytest.approx(0.0)
    # FCF ติดลบ -> fail เต็ม แม้ accruals ผ่าน (fuzzy AND = min)
    assert _criterion_fcf_and_accruals(
        [_fact("FCF Margin", -5.0), _fact("CFO", 120.0), _fact("Net Income", 100.0)], RF) == pytest.approx(0.0)
    # ขาดทุน (NI<=0): accruals ratio ไร้ความหมาย -> เช็คแค่ FCF margin
    assert _criterion_fcf_and_accruals(
        [_fact("FCF Margin", 5.0), _fact("CFO", -10.0), _fact("Net Income", -50.0)], RF) == pytest.approx(1.0)
    # NVDA จริง: CFO/NI=0.8555 (ต่ำกว่า tolerance 0.9 เล็กน้อย) -> เกือบ fail แต่ไม่ใช่ cliff เต็ม
    assert _criterion_fcf_and_accruals(
        [_fact("FCF Margin", 18.0), _fact("CFO", 85.55), _fact("Net Income", 100.0)], RF) == pytest.approx(0.055, abs=1e-3)
    assert _criterion_fcf_and_accruals([_fact("FCF Margin", 10.0)], RF) is None


def test_criterion_revenue_growth_threshold_is_3pct_not_0():
    # threshold=3%, band=3pp
    assert _criterion_revenue_growth([_fact("Revenue CAGR", 3.5)], RF) == pytest.approx(0.583, abs=1e-3)
    assert _criterion_revenue_growth([_fact("Revenue CAGR", 1.5)], RF) == pytest.approx(0.25)
    assert _criterion_revenue_growth([_fact("Revenue CAGR", 10.0)], RF) == pytest.approx(1.0)   # โตชัดเจนพอ -> เต็ม


def test_criterion_leverage_net_cash_passes():
    # audit fix: net-cash (Net Debt <= 0) ผ่านเต็ม 1.0 ทันที ไม่สนตัวเลข ratio เลย
    assert _criterion_leverage([_fact("Net Debt", -900.0), _fact("Net Debt / EBITDA", -6.29)], RF) == pytest.approx(1.0)
    # มีหนี้: level ต่ำมาก -> เต็ม (เกิน threshold-band=2 ไปเยอะ)
    assert _criterion_leverage([_fact("Net Debt", 500.0), _fact("Net Debt / EBITDA", 1.0)], RF) == pytest.approx(1.0)
    # มีหนี้: level เท่า threshold+band พอดี -> ศูนย์
    assert _criterion_leverage([_fact("Net Debt", 500.0), _fact("Net Debt / EBITDA", 4.0)], RF) == pytest.approx(0.0)
    # SBUX จริง 2.67x — ใกล้เพดาน 3x แต่ยังไม่เกิน -> partial สูง ไม่ใช่เต็ม
    assert _criterion_leverage([_fact("Net Debt", 500.0), _fact("Net Debt / EBITDA", 2.67)], RF) == pytest.approx(0.665, abs=1e-3)
    # มีหนี้แต่ไม่มี ratio -> คำนวณไม่ได้
    assert _criterion_leverage([_fact("Net Debt", 500.0)], RF) is None


def test_criterion_solvency_interest_coverage():
    # audit fix: แทน current-ratio ด้วย interest coverage (band=1.5x)
    # audit fix 19.2: Interest Coverage มา "ก่อน" net-cash เสมอถ้ามีข้อมูล (net-cash ไม่ได้แปลว่า
    # ไม่มีดอกเบี้ยต้องจ่ายจริง) — net_debt<=0 เป็นแค่ fallback (binary) ตอนไม่มี Interest Coverage เลย
    assert _criterion_solvency([_fact("Net Debt", -900.0)], RF) == pytest.approx(1.0)   # ไม่มี coverage -> fallback net-cash
    assert _criterion_solvency([_fact("Net Debt", 500.0), _fact("Interest Coverage", 10.0)], RF) == pytest.approx(1.0)
    # coverage เท่า threshold-band พอดี (3-1.5=1.5) -> ศูนย์
    assert _criterion_solvency([_fact("Net Debt", 500.0), _fact("Interest Coverage", 1.5)], RF) == pytest.approx(0.0)
    # net-cash แต่มี Interest Coverage จริงและแย่ -> ใช้ข้อมูลจริง ไม่ auto-pass ทับ
    assert _criterion_solvency([_fact("Net Debt", -900.0), _fact("Interest Coverage", 1.0)], RF) == pytest.approx(0.0)
    # มีหนี้ ไม่มี coverage -> fallback net_debt<=0 -> 0.0 (ระวังไว้ก่อน ไม่ใช่ None)
    assert _criterion_solvency([_fact("Net Debt", 500.0)], RF) == pytest.approx(0.0)
    assert _criterion_solvency([], RF) is None   # ไม่มีข้อมูลเลย -> คำนวณไม่ได้จริงๆ


def test_criterion_margin_improving():
    # band=1.5pp รอบ delta=0
    assert _criterion_margin_improving(
        [_fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025")], RF) == pytest.approx(1.0)
    assert _criterion_margin_improving(
        [_fact("Operating Margin", 22.0, "FY2024"), _fact("Operating Margin", 20.0, "FY2025")], RF) == pytest.approx(0.0)
    # GOOGL จริง: 32.11% -> 32.03%, ลดแค่ 0.08pp — เดิม cliff เต็มเป็น fail, ตอนนี้ partial ~0.47
    assert _criterion_margin_improving(
        [_fact("Operating Margin", 32.11, "FY2024"), _fact("Operating Margin", 32.03, "FY2025")], RF) == pytest.approx(0.473, abs=1e-3)


def test_criterion_not_diluting():
    # %เปลี่ยน YoY, band=1.5%
    assert _criterion_not_diluting(
        [_fact("Diluted Shares", 100.0, "FY2024"), _fact("Diluted Shares", 95.0, "FY2025")], RF) == pytest.approx(1.0)
    assert _criterion_not_diluting(
        [_fact("Diluted Shares", 95.0, "FY2024"), _fact("Diluted Shares", 100.0, "FY2025")], RF) == pytest.approx(0.0)
    # SBUX จริง: +0.22% (noise-level) — เดิม cliff เต็มเป็น fail, ตอนนี้ partial ~0.43
    assert _criterion_not_diluting(
        [_fact("Diluted Shares", 1137.3, "FY2024"), _fact("Diluted Shares", 1139.8, "FY2025")], RF) == pytest.approx(0.427, abs=1e-3)


# --- _fy_series dedup (scalar period ชนกับ series ปีเดียวกัน) ---

def test_fy_series_dedupes_scalar_and_series_collision():
    from src.agent.health import _fy_series
    # ROE มีทั้ง scalar (period=FY2025, ค่า A) และ series (FY2024, FY2025=ค่า B) — series ต้องชนะ
    facts = [_fact("ROE", 999.0, "FY2025"), _fact("ROE", 20.0, "FY2024"), _fact("ROE", 25.0, "FY2025")]
    pts = _fy_series(facts, "ROE")
    assert pts == [("FY2024", 20.0), ("FY2025", 25.0)]   # ไม่ใช่ [("FY2024",20),("FY2025",999),("FY2025",25)]


# --- fundamental score / data gate ---

# ผ่านครบ 8 เกณฑ์ "เต็ม" (audit-fixed, 19.2+19.3): ทุกค่าอยู่เกิน threshold+band ของแต่ละเกณฑ์
# ไม่ใช่แค่ผ่าน threshold เฉยๆ (ไม่งั้นได้ partial credit ไม่ใช่ 1.0 เต็ม — ดู _graded_above)
# #1 ROIC>WACC, #2 Net Margin>=10 (independent จาก ROIC), #3 FCF+accruals(tol),
# #4 revenue>3%, #5 leverage(net-cash), #6 solvency(net-cash fallback), #7 margin trend, #8 no dilution
_FULL_PASS_FACTS = [
    _fact("ROIC", 20.0), _fact("Beta", 1.0),
    _fact("Net Margin", 20.0, "FY2025"),
    _fact("FCF Margin", 10.0), _fact("CFO", 120.0), _fact("Net Income", 100.0),
    _fact("Revenue CAGR", 10.0),   # >= 3+3=6 (band) ถึงจะได้ 1.0 เต็ม ไม่ใช่แค่ >3
    _fact("Net Debt", -100.0),   # net-cash, ไม่มี Interest Coverage -> ผ่านทั้ง #5 (leverage) และ #6 (fallback)
    _fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025"),
    _fact("Diluted Shares", 100.0, "FY2024"), _fact("Diluted Shares", 95.0, "FY2025"),
]


def test_fundamental_score_all_pass():
    result = _fundamental_score(_FULL_PASS_FACTS, RF)
    assert result["score"] == pytest.approx(8.0)
    assert result["computable"] == 8
    assert result["disqualified"] is False


def test_fundamental_score_disqualifies_below_data_gate():
    # เหลือแค่ 4 เกณฑ์ที่คำนวณได้ (< DATA_GATE_MIN_CRITERIA=6)
    thin_facts = [_fact("ROIC", 20.0), _fact("Revenue CAGR", 5.0),
                  _fact("Operating Margin", 20.0, "FY2024"), _fact("Operating Margin", 22.0, "FY2025")]
    result = _fundamental_score(thin_facts, RF)
    assert result["score"] is None
    assert result["disqualified"] is True
    assert result["computable"] < DATA_GATE_MIN_CRITERIA
    assert f"{result['computable']}/8" in result["reason"]


def test_fundamental_score_missing_criterion_counts_as_fail_not_skip():
    # ผ่าน data gate (>=6 คำนวณได้) แต่มี 1 เกณฑ์ที่คำนวณไม่ได้ -> denominator ยังเป็น 8 เสมอ
    # (ตัด Diluted Shares ออก -> #8 คำนวณไม่ได้ -> เหลือ 7 computable ที่ผ่านเต็มหมด)
    facts = [f for f in _FULL_PASS_FACTS if f["label"] != "Diluted Shares"]
    result = _fundamental_score(facts, RF)
    assert result["computable"] == 7   # #8 (dilution) เช็คไม่ได้
    assert result["score"] == pytest.approx(7.0)   # /8 เสมอ ไม่ใช่ 7/7


def test_fundamental_score_no_facts_at_all_disqualifies():
    result = _fundamental_score([], RF)
    assert result["score"] is None
    assert result["disqualified"] is True
    assert result["computable"] == 0


# --- valuation (reverse-DCF score, 0-3) ---

def test_valuation_score_excluded_when_no_market_data():
    result = _valuation_score([], RF)
    assert result["score"] is None
    assert result["excluded"] is True


def test_valuation_score_excluded_when_fcf_negative():
    facts = [_fact("Market Cap", 1000.0), _fact("FCF Yield", -5.0)]
    result = _valuation_score(facts, RF)
    assert result["score"] is None
    assert result["excluded"] is True
    assert "burn cash" in result["reason"]


def test_valuation_score_computed_when_data_present():
    facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04), _fact("Revenue CAGR", 15.0)]
    result = _valuation_score(facts, RF)
    assert result["score"] is not None
    assert result["excluded"] is False
    assert 0 <= result["score"] <= 3


# --- sentiment (/1, เหมือน Phase 17) ---

def test_sentiment_points():
    assert _sentiment_points(_summary("bullish"))[0] == 1.0
    assert _sentiment_points(_summary("neutral"))[0] == 0.5
    assert _sentiment_points(_summary("bearish"))[0] == 0.0


# --- compute_health end-to-end ---

def test_compute_health_normal_case():
    valuation_facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04)]
    h = compute_health(_summary("bullish"), None, _FULL_PASS_FACTS + valuation_facts, RF)
    assert h["score"] is not None
    assert h["tier"] in ("strong", "ok", "weak")
    assert h["components"]["strength"] == pytest.approx(8.0)
    assert 0.0 <= h["score"] <= 12.0
    assert round(sum(h["components"].values()), 6) == h["score"]


def test_compute_health_disqualified_when_fundamental_data_thin():
    h = compute_health(_summary(), None, [_fact("ROIC", 20.0)], RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_excluded_when_valuation_unresolvable():
    # fundamental ผ่าน data gate (8/8) แต่ FCF ติดลบ -> valuation excluded -> total ก็ excluded ด้วย
    facts = _FULL_PASS_FACTS + [_fact("Market Cap", 1000.0), _fact("FCF Yield", -5.0)]
    h = compute_health(_summary(), None, facts, RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_crypto_like_facts_disqualified():
    # crypto ไม่มี Fact ที่เกี่ยวข้องกับ Piotroski เลย -> data gate ไม่ผ่านอัตโนมัติ ไม่ต้องเช็ค asset_type แยก
    crypto_facts = [_fact("Market Cap", 500.0, "TTM"), _fact("Volume/Market Cap", 5.0, "TTM")]
    h = compute_health(_summary(), None, crypto_facts, RF)
    assert h["score"] is None
    assert h["tier"] == "excluded"


def test_compute_health_breach_penalizes_and_floors_at_zero():
    # ทุกเกณฑ์ fail หนัก -> fundamental ~0/8 (ไล่ระดับ 19.3 ทำให้ไม่เป๊ะ 0 เสมอไป แต่ใกล้ 0 มาก) + valuation resolvable
    low_facts = [
        _fact("ROIC", 1.0), _fact("Beta", 1.0),          # #1 ROIC<WACC -> fail
        _fact("Net Margin", 2.0, "FY2025"),               # #2 Net Margin<10 -> fail
        _fact("FCF Margin", -5.0), _fact("CFO", 70.0), _fact("Net Income", 100.0),  # #3 FCF<0 -> fail
        _fact("Revenue CAGR", 1.0),                       # #4 <3% -> fail
        _fact("Net Debt", 500.0), _fact("Net Debt / EBITDA", 4.0),  # #5 มีหนี้ ratio>=3 -> fail
        _fact("Interest Coverage", 1.0),                  # #6 coverage<3 -> fail
        _fact("Operating Margin", 22.0, "FY2024"), _fact("Operating Margin", 20.0, "FY2025"),  # #7 ลด -> fail
        _fact("Diluted Shares", 95.0, "FY2024"), _fact("Diluted Shares", 100.0, "FY2025"),     # #8 เพิ่ม -> fail
        _fact("Market Cap", 900.0), _fact("FCF Yield", 5.0),   # valuation resolvable
    ]
    breaches = [{"severity": "alert"}]
    h = compute_health(_summary("bearish"), breaches, low_facts, RF)
    assert h["score"] is not None
    assert h["components"]["breach_penalty"] == -3.0
    assert h["score"] >= 0.0   # floored, ไม่ติดลบ


def test_compute_health_json_serializable():
    import json
    valuation_facts = [_fact("Market Cap", 905.78), _fact("FCF Yield", 11.04)]
    h = compute_health(_summary(), None, _FULL_PASS_FACTS + valuation_facts, RF)
    json.dumps(h)   # ไม่ raise = pass

    h_excluded = compute_health(_summary(), None, [], RF)
    json.dumps(h_excluded)


def test_normalize_facts_accepts_dataclass_and_dict():
    from src.domain.interfaces import Fact
    dc = [Fact(label="ROIC", value=15.0, unit="%", period="FY2025")]
    d = [{"label": "ROIC", "value": 15.0, "unit": "%", "period": "FY2025"}]
    assert _normalize_facts(dc) == _normalize_facts(d)