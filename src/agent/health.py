"""Health score — Phase 18: implements scoring_spec.md (Fundamental /8 + Valuation
reverse-DCF /3 + News /1 = /12), replacing Phase 17's fallback-to-LLM-label design.

การเปลี่ยนแปลงหลักเทียบ Phase 17:
- **Denominator คงที่ที่ 8** เสมอสำหรับ fundamental (สเปกห้าม normalize ด้วยจำนวนเกณฑ์ที่
  คำนวณได้ — จะให้รางวัลหุ้นที่เปิดเผยข้อมูลน้อย) — ข้อมูลขาดของเกณฑ์ที่ "คำนวณได้" (ผ่าน data
  gate แล้ว) แต่ input บางตัวขาด = fail(0) ไม่ใช่ skip
- **Data gate ก่อนให้คะแนน**: ต้องคำนวณเกณฑ์ได้ (มี input ครบ) อย่างน้อย 6/8 ข้อ ไม่งั้น
  DISQUALIFY ทั้งตัว (score=None, tier="excluded") — ไม่ fallback ไป LLM label อีกต่อไป
- **Valuation ที่คำนวณ reverse-DCF ไม่ได้ (ขาดทุน/นอกขอบเขตโมเดล) = ตัดออกทั้งตัวเช่นกัน**
  ไม่ fallback ไป LLM label — ตามหลัก "อย่าปนหุ้นที่ข้อมูลไม่ครบเข้าไปในสนามทดลอง backtest"
- **ไม่มี component 'confidence' ในคะแนนรวมอีกต่อไป** (สเปกไม่รวม — ความมั่นใจของ LLM เป็น
  metadata ไม่ใช่ตัวให้คะแนน) — Total = Fundamental(/8) + Valuation(/3) + News(/1) = /12
- **Crypto / ไม่มีงบ**: อยู่นอกขอบเขตระบบนี้ทั้งหมด (fundamental data gate จะไม่ผ่านเองเพราะ
  ไม่มี Fact ที่เกี่ยวข้องเลย -> DISQUALIFY โดยอัตโนมัติ ไม่ต้องเช็ค asset_type แยก)

`components` ยังคง key เดิม 4 ตัว (strength/valuation/sentiment/breach_penalty — ตัด
confidence ออก) ให้ changes.py::_diff ยัง diff หาตัวขับคะแนนที่กระโดดได้เหมือนเดิม แต่ตอนนี้
ค่าอาจเป็น None ได้เมื่อ excluded — changes.py ต้อง guard ก่อน diff (ดูคอมเมนต์ที่นั่น).
"""
from types import SimpleNamespace

from src.agent.valuation import reverse_dcf, capm_wacc, FALLBACK_RISK_FREE_PCT

DATA_GATE_MIN_CRITERIA = 6   # ต้องคำนวณได้อย่างน้อย 6/8 เกณฑ์ ไม่งั้น disqualify ทั้งตัว
TOTAL_MAX = 12.0             # Fundamental(8) + Valuation(3) + News(1)

SENTIMENT_PTS = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}   # /1 — tie-breaker เท่านั้น

# เกณฑ์ตัวเลข (heuristic มาตรฐานการเงินทั่วไป ไม่ใช่กฎตายตัว — ปรับตาม backtest ได้ แต่ตั้งก่อนรัน)
# ── audit fix (2026-07): 4 เกณฑ์เดิม (#2 ROE-trend, #3 accruals เป๊ะ, #5 leverage trend,
#    #6 current-ratio) backfire กับบริษัทคุณภาพสูง/net-cash — ลงโทษ AAPL (ROIC 82%, buyback,
#    net-cash-ish) จนได้ 4.5 "อ่อน" ทั้งที่เป็นธุรกิจชั้นเยี่ยม. แก้ให้ robust ตามเหตุผลใต้แต่ละ criterion
# ── audit fix 19.2 (2026-07): ROIC ขับทั้ง #1 (ROIC>WACC) และ #2 เดิม (ROIC>=15%) — วัดผิดที่
#    invested-capital ตัวเดียวพังพร้อมกัน 2 เกณฑ์. #2 เปลี่ยนไปใช้ Net Margin (Net Income/Revenue —
#    ไม่แชร์ input กับ NOPAT/invested-capital เลย) แทน. #6 (solvency) เดิม net_debt<=0 auto-pass
#    ก่อนเช็ค Interest Coverage เสมอ — แต่ net-cash ไม่ได้แปลว่าไม่มีดอกเบี้ยต้องจ่ายจริง (มีหนี้ก้อนใหญ่
#    + เงินสดก้อนใหญ่กว่า ก็ยังจ่ายดอกเบี้ยจริงได้) แก้ให้เช็ค Interest Coverage ตรงๆ ก่อนเสมอถ้ามีข้อมูล
#    เหลือ net-cash เป็น fallback เฉพาะตอนไม่มี Interest Coverage ให้เช็ค (ตรงกับ DUOL: ไม่มีดอกเบี้ยรายงาน
#    เพราะไม่มีหนี้จริง ไม่ใช่ data gap) — ลดจุดที่ Net Debt เครื่องหมายเดียวชี้ชะตา 2 เกณฑ์พร้อมกัน
ROIC_MIN_PCT = 15.0           # เกณฑ์ #1 อ้างอิง WACC เท่านั้น (ระดับ absolute ย้ายไป #2/Net Margin แล้ว)
NET_MARGIN_MIN_PCT = 10.0     # เกณฑ์ #2: Net Margin สูง = pricing power + cost discipline (independent จาก ROIC)
REVENUE_CAGR_THRESHOLD_PCT = 3.0   # เกณฑ์ #4: เหนือเงินเฟ้อจริง ไม่ใช่แค่ > 0%
LEVERAGE_MAX_X = 3.0          # เกณฑ์ #5
INTEREST_COVERAGE_MIN_X = 3.0  # เกณฑ์ #6: EBIT/ดอกเบี้ย จ่ายได้สบาย (แทน current-ratio ที่ลงโทษอำนาจต่อรองสูง)
ACCRUALS_TOLERANCE = 0.9      # เกณฑ์ #3: CFO >= 0.9*NI (มี tolerance กัน knife-edge ที่ CFO≈NI)


def _normalize_facts(facts) -> list[dict]:
    """list[Fact] (dataclass) หรือ list[dict] (จาก JSON) -> list[dict] รูปแบบเดียวกันหมด."""
    if not facts:
        return []
    out = []
    for f in facts:
        if hasattr(f, "label"):
            out.append({"label": f.label, "value": f.value, "unit": f.unit, "period": f.period})
        else:
            out.append(f)
    return out


def _scalar(facts: list[dict], label: str) -> float | None:
    """ค่าสเกลาร์ของ label (มีค่าเดียวต่อ label สำหรับเมตริกกลุ่มนี้ — ไม่ใช่อนุกรมหลายปี)."""
    for f in facts:
        if f["label"] == label and f["value"] is not None:
            return float(f["value"])
    return None


def _fy_series(facts: list[dict], label: str) -> list[tuple[str, float]]:
    """อนุกรมรายปี (period ขึ้นต้นด้วย FY) ของ label หนึ่ง เรียงเก่า -> ใหม่ — dedupe เอาค่า
    ล่าสุดต่อ period (บาง label เช่น ROE/Current Ratio/Net Debt-EBITDA มีทั้ง scalar ที่
    period=self.period ('FYxxxx') และ series ปีเดียวกันชนกันได้ — series ต้องชนะเพราะมาทีหลัง
    ใน to_facts() ของ fundamentals.py)."""
    by_period: dict[str, float] = {}
    for f in facts:
        if f["label"] == label and str(f.get("period", "")).startswith("FY"):
            by_period[f["period"]] = float(f["value"])
    return sorted(by_period.items(), key=lambda p: p[0])


# ─────────────────────────────────────────────────────────────────────────────
# PART A — Fundamental (/8), 8 เกณฑ์ตาม scoring_spec.md
# check(facts, risk_free_pct) -> True (ผ่าน) | False (ไม่ผ่าน) | None (ข้อมูลไม่พอคำนวณ)
# ─────────────────────────────────────────────────────────────────────────────
def _criterion_roic_vs_wacc(facts, risk_free_pct):
    """#1: ROIC > WACC (ไม่ใช่ ROIC > 0 — 'โตแล้วเผาเงิน' ต้องได้ 0 เพราะ ROIC>0 แทบไม่มีความหมาย)."""
    roic = _scalar(facts, "ROIC")
    if roic is None:
        return None
    beta = _scalar(facts, "Beta")
    wacc_pct = capm_wacc(beta, risk_free_pct) * 100.0
    return roic > wacc_pct


def _criterion_net_margin_level(facts, _rf):
    """#2: Net Margin (ปีล่าสุด) >= 10% — pricing power + cost discipline.
    audit fix 19.2: เดิมใช้ ROIC>=15% ซ้ำกับ #1 (ROIC>WACC) — ตัวเลขเดียวกันขับ 2 เกณฑ์ ถ้า
    invested-capital คำนวณผิดพลาดจะพังพร้อมกันทั้งคู่ (correlated error). Net Margin = Net
    Income/Revenue ไม่แชร์ input กับ NOPAT/invested-capital เลย (คนละ pipeline การคำนวณเต็มๆ)
    จึงกระจายความเสี่ยง และยังเป็นเกณฑ์คุณภาพมาตรฐาน (double-digit net margin) ที่ใช้กันทั่วไป."""
    pts = _fy_series(facts, "Net Margin")
    return None if not pts else pts[-1][1] >= NET_MARGIN_MIN_PCT


def _criterion_fcf_and_accruals(facts, _rf):
    """#3: FCF > 0 และ CFO >= 0.9*Net Income (accruals — คุณภาพกำไร) ทั้งคู่ต้องผ่าน.
    audit fix: เดิมใช้ CFO > NI เป๊ะๆ = knife-edge ไม่มี tolerance — บริษัทคุณภาพที่ CFO≈NI
    (เช่น AAPL CFO/NI=0.995 = กำไรเป็นเงินสดเกือบเต็ม) โดน fail เท่ากับบริษัทแต่งงบจริง เพราะ
    cliff อยู่ที่ CFO=NI พอดี. ใส่ tolerance 10% (CFO >= 0.9*NI) = 'กำไรเป็นเงินสดอย่างน้อย 90%'.
    NI <= 0 (ขาดทุน): accruals ratio ไร้ความหมาย -> เช็คแค่ FCF > 0."""
    fcf_margin = _scalar(facts, "FCF Margin")
    cfo = _scalar(facts, "CFO")
    net_income = _scalar(facts, "Net Income")
    if fcf_margin is None or cfo is None or net_income is None:
        return None
    if net_income <= 0:
        return fcf_margin > 0
    return fcf_margin > 0 and cfo >= ACCRUALS_TOLERANCE * net_income


def _criterion_revenue_growth(facts, _rf):
    """#4: Revenue CAGR > 3% (เหนือเงินเฟ้อจริง ไม่ใช่แค่ > 0%)."""
    v = _scalar(facts, "Revenue CAGR")
    return None if v is None else v > REVENUE_CAGR_THRESHOLD_PCT


def _criterion_leverage(facts, _rf):
    """#5: มีเงินสดสุทธิ (Net Debt <= 0) ผ่านทันที, ไม่งั้น Net Debt/EBITDA < 3.
    audit fix: เดิมเช็ค trend YoY ด้วย ('ไม่เพิ่มขึ้น') ซึ่งพังกับบริษัท net-cash — ratio เป็นเลข
    ติดลบไร้ความหมาย (เช่น DUOL series -9.95 -> -6.29 fail เพราะ -6.29 > -9.95 ทั้งที่เทียบไม่ได้
    ตั้งแต่แรก). net-cash = ไม่มีความเสี่ยงหนี้เลย ควรผ่าน ไม่ใช่ fail. ตัด trend ออก เหลือ level."""
    net_debt = _scalar(facts, "Net Debt")
    if net_debt is not None and net_debt <= 0:
        return True   # เงินสดสุทธิ = ปลอดภัยเรื่องหนี้ 100%
    nde = _scalar(facts, "Net Debt / EBITDA")
    return None if nde is None else nde < LEVERAGE_MAX_X


def _criterion_solvency(facts, _rf):
    """#6: Interest Coverage >= 3x ถ้ามีข้อมูล, ไม่งั้น fallback ไปเช็ค Net Debt <= 0 (net-cash).
    audit fix: แทนเกณฑ์เดิม 'Current Ratio > 1' ที่ลงโทษบริษัทอำนาจต่อรองสูง — AAPL รัน current
    ratio < 1 โดยตั้งใจ (จ่าย supplier ช้า เก็บเงินเร็ว) = จุดแข็ง working-capital ไม่ใช่จุดอ่อน.
    Interest coverage (EBIT/ดอกเบี้ย) วัด 'จ่ายหนี้ไหวไหม' ตรงกว่า.
    audit fix 19.2: เดิมเช็ค net_debt<=0 auto-pass 'ก่อน' Interest Coverage เสมอ — แต่ net-cash
    ไม่ได้แปลว่าไม่มีดอกเบี้ยต้องจ่ายจริง (มีหนี้ก้อนใหญ่ + เงินสดใหญ่กว่า ก็ยังจ่ายดอกเบี้ยจริงได้ ถ้า
    EBIT ไม่พอก็ยัง fail ได้จริง). สลับลำดับ: ใช้ Interest Coverage จริงก่อนเสมอถ้ามี ข้อมูล net-cash
    เป็นแค่ fallback ตอนไม่มี Interest Expense รายงานเลย (เช่น DUOL — ไม่มีหนี้จริง ไม่ใช่ data gap)."""
    cov = _scalar(facts, "Interest Coverage")
    if cov is not None:
        return cov >= INTEREST_COVERAGE_MIN_X
    net_debt = _scalar(facts, "Net Debt")
    return None if net_debt is None else net_debt <= 0


def _criterion_margin_improving(facts, _rf):
    """#7: Operating Margin ปีนี้ >= ปีก่อน (trend ล้วน)."""
    pts = _fy_series(facts, "Operating Margin")
    return None if len(pts) < 2 else pts[-1][1] >= pts[-2][1]


def _criterion_not_diluting(facts, _rf):
    """#8: จำนวนหุ้นปีนี้ <= ปีก่อน (ไม่เจือจางสุทธิ)."""
    pts = _fy_series(facts, "Diluted Shares")
    return None if len(pts) < 2 else pts[-1][1] <= pts[-2][1]


PIOTROSKI_CRITERIA = [
    ("ROIC>WACC", _criterion_roic_vs_wacc),
    ("Net Margin สูง(>=10%)", _criterion_net_margin_level),
    ("FCF+คุณภาพกำไร", _criterion_fcf_and_accruals),
    ("รายได้เติบโตจริง(>3%)", _criterion_revenue_growth),
    ("หนี้ไม่บานปลาย", _criterion_leverage),
    ("จ่ายดอกเบี้ยไหว/net-cash", _criterion_solvency),
    ("Margin ขยาย", _criterion_margin_improving),
    ("ไม่เจือจางหุ้น", _criterion_not_diluting),
]


def _fundamental_score(facts: list[dict], risk_free_pct: float) -> dict:
    """คืน dict: score (int 0-8 หรือ None ถ้า disqualify), computable, passed, criteria
    (list ของ (label, True/False/None)), disqualified (bool), reason (str|None)."""
    results = [(label, check(facts, risk_free_pct)) for label, check in PIOTROSKI_CRITERIA]
    computable = sum(1 for _, ok in results if ok is not None)
    passed = sum(1 for _, ok in results if ok is True)

    if computable < DATA_GATE_MIN_CRITERIA:
        return {
            "score": None, "computable": computable, "passed": passed, "criteria": results,
            "disqualified": True,
            "reason": f"ข้อมูลไม่พอ: คำนวณเกณฑ์พื้นฐานได้แค่ {computable}/8 (ต้องการ >= {DATA_GATE_MIN_CRITERIA}) — ตัดออกจาก screen นี้",
        }

    passed_labels = [label for label, ok in results if ok is True]
    reason = f"พื้นฐาน: ผ่าน {passed}/8 เกณฑ์ ({', '.join(passed_labels) if passed_labels else 'ไม่ผ่านเลย'}) (+{passed}/8)"
    return {"score": passed, "computable": computable, "passed": passed, "criteria": results,
            "disqualified": False, "reason": reason}


# ─────────────────────────────────────────────────────────────────────────────
# PART B — Valuation reverse-DCF (/3) — ใช้ score จาก reverse_dcf() ตรงๆ (step-function
# gap bands อยู่ในนั้นแล้ว, ดู src/agent/valuation.py::_gap_to_score)
# ─────────────────────────────────────────────────────────────────────────────
def _build_duck_fundamentals(facts: list[dict]) -> SimpleNamespace:
    """ประกอบ duck-object จาก facts ให้ reverse_dcf() ใช้ — path เดียวกันทั้งตอนวิเคราะห์สด
    (facts จาก fundamentals_obj.to_facts()) และตอน backfill ย้อนหลัง (facts จาก DB/JSON)."""
    fcf_yield = _scalar(facts, "FCF Yield")
    market_cap = _scalar(facts, "Market Cap")
    fcf = (fcf_yield / 100.0 * market_cap) if fcf_yield is not None and market_cap else None
    return SimpleNamespace(
        free_cash_flow=fcf,
        market_cap=market_cap,
        revenue=_scalar(facts, "Revenue"),
        revenue_cagr=_scalar(facts, "Revenue CAGR"),
        revenue_series=_fy_series(facts, "Revenue FY"),
        fcf_series=_fy_series(facts, "Free Cash Flow"),
        fcf_margin=_scalar(facts, "FCF Margin"),
        net_debt=_scalar(facts, "Net Debt"),
        beta=_scalar(facts, "Beta"),
        capex=_scalar(facts, "Capex"),
        depreciation_amortization=_scalar(facts, "D&A"),
        nwc_change=_scalar(facts, "NWC Change"),
        nopat=_scalar(facts, "NOPAT"),
        roic=_scalar(facts, "ROIC"),
    )


def _valuation_score(facts: list[dict], risk_free_pct: float) -> dict:
    """คืน dict: score (0-3 หรือ None), excluded (bool), reason (str|None), + field อื่นจาก
    reverse_dcf() ทั้งหมด (implied_growth/realistic_growth/gap/wacc/...) เพื่อความโปร่งใส."""
    duck = _build_duck_fundamentals(facts)
    dcf = reverse_dcf(duck, risk_free_pct=risk_free_pct)
    if dcf is None:
        return {"score": None, "excluded": True, "reason": "ไม่มี Market Cap/FCF พอคำนวณ reverse-DCF — ตัดออกจาก screen นี้"}
    if dcf["score"] is None:
        reason = dcf.get("note") or "reverse-DCF คำนวณไม่ได้"
        return {"score": None, "excluded": True, "reason": f"{reason} — ตัดออกจาก screen นี้", **dcf}
    lens_note = f", {dcf['lens']} lens ({', '.join(dcf['flags'])})" if dcf["flags"] else ""
    reason = (
        f"ราคา: ตลาดคาด FCF โต {dcf['implied_growth']:.1f}%/ปี เทียบ realistic growth "
        f"{dcf['realistic_growth']:.1f}%/ปี (gap {dcf['gap']:+.1f}pp, WACC {dcf['wacc']:.1f}%{lens_note}) (+{dcf['score']}/3)"
    )
    return {"score": dcf["score"], "excluded": False, "reason": reason, **dcf}


# ─────────────────────────────────────────────────────────────────────────────
# PART C — News/sentiment (/1) — tie-breaker เท่านั้น, ห้ามพลิกผลของ /8 + /3
# ─────────────────────────────────────────────────────────────────────────────
def _sentiment_points(summary) -> tuple[float, str]:
    pts = SENTIMENT_PTS.get(summary.sentiment, 0.5)
    return pts, f"มุมมองข่าว {summary.sentiment} (+{pts:g}/1)"


# ─────────────────────────────────────────────────────────────────────────────
# รวมคะแนน
# ─────────────────────────────────────────────────────────────────────────────
def compute_health(summary, breaches: list[dict] | None = None, facts=None,
                    risk_free_pct: float = FALLBACK_RISK_FREE_PCT) -> dict:
    """summary = Pydantic Summary (ต้องการ sentiment เท่านั้นตอนนี้ — fundamental_strength/
    valuation_view ของ LLM ไม่ได้ใช้ในคะแนนแล้ว เพราะ Phase 18 ยึดตัวเลขจริงล้วนไม่มี fallback),
    breaches = check_invalidation()['breaches'], facts = list[Fact]/list[dict] ของรอบนี้,
    risk_free_pct = อัตราพันธบัตร 10 ปี ณ วันรัน (จาก src.providers.stock.market).

    คืน dict: score (0-12 หรือ None ถ้า 'excluded' — ข้อมูลไม่พอ/ขาดทุน/crypto ไม่เข้าเกณฑ์ระบบนี้),
    tier (strong/ok/weak/excluded), label, reasons, fundamental (dict ละเอียด),
    valuation (dict ละเอียดจาก reverse_dcf), components (4 key เดิม, ค่าเป็น None ได้เมื่อ excluded)."""
    facts = _normalize_facts(facts)

    fundamental = _fundamental_score(facts, risk_free_pct)
    valuation = _valuation_score(facts, risk_free_pct)
    sentiment_pts, sentiment_reason = _sentiment_points(summary)

    if fundamental["disqualified"] or valuation["excluded"]:
        reason = fundamental["reason"] if fundamental["disqualified"] else valuation["reason"]
        return {
            "score": None, "max": TOTAL_MAX, "tier": "excluded", "label": "ประเมินไม่ได้",
            "reasons": [reason],
            "fundamental": fundamental, "valuation": valuation,
            "components": {"strength": fundamental["score"], "valuation": valuation["score"],
                            "sentiment": sentiment_pts, "breach_penalty": None},
        }

    reasons = [fundamental["reason"], valuation["reason"], sentiment_reason]
    score = fundamental["score"] + valuation["score"] + sentiment_pts

    has_breach = any(b.get("severity") == "alert" for b in (breaches or []))
    breach_penalty = -3.0 if has_breach else 0.0
    if has_breach:
        score += breach_penalty
        reasons.append("เงื่อนไขออกโดนแตะ (−3)")

    score = max(0.0, min(TOTAL_MAX, score))
    rounded = round(score, 1)
    # tier boundary สัดส่วนเท่าเดิม (70%/45%) แค่สเกลจาก /10 เดิมมาเป็น /12
    tier = "strong" if rounded >= TOTAL_MAX * 0.7 else "ok" if rounded >= TOTAL_MAX * 0.45 else "weak"
    label = {"strong": "แข็งแรง", "ok": "พอใช้", "weak": "อ่อน"}[tier]

    return {
        "score": rounded, "max": TOTAL_MAX, "tier": tier, "label": label, "reasons": reasons,
        "fundamental": fundamental, "valuation": valuation,
        "components": {"strength": fundamental["score"], "valuation": valuation["score"],
                        "sentiment": sentiment_pts, "breach_penalty": breach_penalty},
    }