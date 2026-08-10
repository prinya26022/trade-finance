"""Health score — Phase 18: implements scoring_spec.md (Fundamental /8 + Valuation
reverse-DCF /3 = /11), replacing Phase 17's fallback-to-LLM-label design.

Phase 19.3.1 (2026-07): sentiment ตัดออกจากผลรวมคะแนนแล้ว (เดิม /12 รวม News/1).
Audit วัดการกระโดดของคะแนนจริงย้อนหลัง (84 คู่ในประวัติ) แยกตาม component พบว่า sentiment
เป็นตัวขับ 57.4% ของทุกรอบที่คะแนนกระโดด >=0.5 (พื้นฐาน 24.3%, ราคา 18.4%) — คะแนนสุขภาพธุรกิจ
เต้นตาม LLM sentiment ที่พลิก bullish<->neutral รายวัน ทั้งที่พื้นฐาน/ราคาไม่ได้เปลี่ยนอะไรเลย
ขัดกับทั้งเจตนาเดิม ("tie-breaker เท่านั้น, ห้ามพลิกผลของ /8+/3" — ดู PART C) และหลักลงทุนของ
โปรเจกต์นี้เอง (ข่าวรายวัน = noise, ไม่ใช่สัญญาณ) sentiment ยังคำนวณและโชว์เป็น metadata/เหตุผล
ประกอบเหมือนเดิม แค่ไม่บวกเข้าคะแนนรวมอีกต่อไป.

การเปลี่ยนแปลงหลักเทียบ Phase 17:
- **Denominator คงที่ที่ 8** เสมอสำหรับ fundamental (สเปกห้าม normalize ด้วยจำนวนเกณฑ์ที่
  คำนวณได้ — จะให้รางวัลหุ้นที่เปิดเผยข้อมูลน้อย) — ข้อมูลขาดของเกณฑ์ที่ "คำนวณได้" (ผ่าน data
  gate แล้ว) แต่ input บางตัวขาด = fail(0) ไม่ใช่ skip
- **Data gate ก่อนให้คะแนน**: ต้องคำนวณเกณฑ์ได้ (มี input ครบ) อย่างน้อย 6/8 ข้อ ไม่งั้น
  DISQUALIFY ทั้งตัว (score=None, tier="excluded") — ไม่ fallback ไป LLM label อีกต่อไป
- **Valuation ที่คำนวณ reverse-DCF ไม่ได้ (ขาดทุน/นอกขอบเขตโมเดล) = ตัดออกทั้งตัวเช่นกัน**
  ไม่ fallback ไป LLM label — ตามหลัก "อย่าปนหุ้นที่ข้อมูลไม่ครบเข้าไปในสนามทดลอง backtest"
- **ไม่มี component 'confidence' ในคะแนนรวมอีกต่อไป** (สเปกไม่รวม — ความมั่นใจของ LLM เป็น
  metadata ไม่ใช่ตัวให้คะแนน) — Total = Fundamental(/8) + Valuation(/3) = /11 (Phase 19.3.1:
  ตัด sentiment ออกจากผลรวมด้วยเหตุผลเดียวกัน — ดูย่อหน้าบน)
- **Crypto / ไม่มีงบ**: อยู่นอกขอบเขตระบบนี้ทั้งหมด (fundamental data gate จะไม่ผ่านเองเพราะ
  ไม่มี Fact ที่เกี่ยวข้องเลย -> DISQUALIFY โดยอัตโนมัติ ไม่ต้องเช็ค asset_type แยก)

`components` ยังคง key เดิม 4 ตัว (strength/valuation/sentiment/breach_penalty) ให้
changes.py::_diff ยัง diff หาตัวขับคะแนนที่กระโดดได้เหมือนเดิม แต่ตอนนี้ sentiment เป็น
metadata ล้วน (ไม่กระทบ score) — changes.py::_health_jump_driver กันไว้แล้วไม่ให้เลือก
sentiment เป็น 'ตัวขับ' เพราะมันไม่มีทางเป็นสาเหตุจริงของคะแนนที่กระโดดอีกต่อไป. ค่าอาจเป็น
None ได้เมื่อ excluded — changes.py ต้อง guard ก่อน diff (ดูคอมเมนต์ที่นั่น).
"""
from types import SimpleNamespace

from src.agent.grading import graded_above as _graded_above, graded_below as _graded_below
from src.agent.valuation import (
    reverse_dcf, capm_wacc, FALLBACK_RISK_FREE_PCT,
    DEFAULT_TERMINAL_GROWTH,
)

DATA_GATE_MIN_CRITERIA = 6   # ต้องคำนวณได้อย่างน้อย 6/8 เกณฑ์ ไม่งั้น disqualify ทั้งตัว
TOTAL_MAX = 11.0             # Fundamental(8) + Valuation(3) — sentiment ไม่รวมแล้ว (19.3.1)
PARTIAL_MAX = 8.0            # Phase 29: พื้นฐานล้วน (ไม่มีขาราคา) — ดู compute_health()


def tier_from_score(score: float, max_score: float = TOTAL_MAX) -> tuple[str, str]:
    """(tier, label) จากคะแนนรวม /max_score — เกณฑ์ 70%/45% เดียวกันทุกที่ที่ใช้ scale นี้.
    Phase 21: ดึงออกมาจาก compute_health() เพราะ screener.py ต้องการ tier แบบเดียวกัน
    (fundamental+valuation ล้วน ไม่มี sentiment/breach) — กันไม่ให้ threshold เพี้ยนกันระหว่าง
    2 จุดที่ใช้ /11 scale เดียวกัน."""
    tier = "strong" if score >= max_score * 0.7 else "ok" if score >= max_score * 0.45 else "weak"
    label = {"strong": "แข็งแรง", "ok": "พอใช้", "weak": "อ่อน"}[tier]
    return tier, label

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
NET_MARGIN_MIN_PCT = 10.0     # เกณฑ์ #2: Net Margin สูง = pricing power + cost discipline (independent จาก ROIC)
REVENUE_CAGR_THRESHOLD_PCT = 3.0   # เกณฑ์ #4: เหนือเงินเฟ้อจริง ไม่ใช่แค่ > 0%
LEVERAGE_MAX_X = 3.0          # เกณฑ์ #5
INTEREST_COVERAGE_MIN_X = 3.0  # เกณฑ์ #6: EBIT/ดอกเบี้ย จ่ายได้สบาย (แทน current-ratio ที่ลงโทษอำนาจต่อรองสูง)
ACCRUALS_TOLERANCE = 0.9      # เกณฑ์ #3: CFO >= 0.9*NI (มี tolerance กัน knife-edge ที่ CFO≈NI)

# ── audit fix 19.3 (2026-07): ทุกเกณฑ์เดิมเป็น binary cliff ที่ threshold เป๊ะๆ — ตัวเลขขยับ
#    แค่เศษเสี้ยว (เช่น GOOGL operating margin 32.11%->32.03%, ลด 0.08pp) พลิกทั้งเกณฑ์จาก pass
#    เป็น fail เต็มๆ (0->1 เต็มจุด, root ของปัญหา "score กระโดด" เดิม). แก้เป็น graded: ไล่ระดับ
#    0.0-1.0 เชิงเส้นรอบ threshold ภายใน "band" ที่กำหนด แทน step function — ผ่านเต็ม (1.0) ที่
#    threshold+band, ไม่ผ่านเลย (0.0) ที่ threshold-band, ไล่ตรงกลาง. ค่าที่ห่าง threshold มากๆ
#    (ส่วนใหญ่ของ watchlist) ยังได้ 1.0/0.0 เท่าเดิม — กระทบเฉพาะเคสที่ใกล้ threshold จริง
BAND_PCT = 3.0            # % ทั่วไป (ROIC-WACC gap, Net Margin, Revenue CAGR) — เท่ากับ TOLERANCE_ABS ที่ใช้ทั้งโปรเจกต์
BAND_ACCRUALS_RATIO = 0.05   # CFO/NI ratio รอบ ACCRUALS_TOLERANCE
BAND_LEVERAGE_X = 1.0        # Net Debt/EBITDA (x เท่า)
BAND_COVERAGE_X = 1.5        # Interest Coverage (x เท่า)
BAND_MARGIN_TREND_PP = 1.5   # #7 operating margin YoY delta (pp)
BAND_DILUTION_PCT = 1.5      # #8 diluted shares YoY %change


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


# ป้ายหน่วยที่ 'ไม่ใช่สกุลเงิน' — ใช้คัดออกตอนหาว่าฝั่งงบกับฝั่งราคาเป็นสกุลเดียวกันไหม
_NON_CURRENCY_UNITS = {"%", "x", "days", "shares", "pp", ""}


def _currency_mismatch(facts: list[dict]) -> bool:
    """งบกับราคาคนละสกุลไหม — ดูจากป้ายหน่วยของ 'Market Cap' (ฝั่งราคา) เทียบกับตัวเลขจากงบ.

    เจอจริง 2026-08: ADR ต่างชาติยื่นงบสกุลบ้านเกิดแต่ราคาเป็น USD (ASML EUR/USD, TSM TWD/USD)
    -> EV = market_cap + net_debt กลายเป็นการบวกคนละสกุล และคะแนนขาราคาที่ได้ออกมาไม่มีความหมาย.
    ตรวจจากป้ายหน่วยเพราะ path นี้ต้องใช้ได้กับ facts ที่อ่านจาก DB ตอน backfill ด้วย (ไม่มี
    object ต้นทางให้ถามแล้ว) — แถวเก่าที่ติดป้าย 'USD' ทั้งคู่จะได้ False = พฤติกรรมเดิมเป๊ะ
    """
    price_unit = _unit(facts, "Market Cap")
    if not price_unit or price_unit in _NON_CURRENCY_UNITS:
        return False
    for label in ("Net Debt", "Revenue", "Net Income", "CFO", "Free Cash Flow"):
        unit = _unit(facts, label)
        if unit and unit not in _NON_CURRENCY_UNITS:
            return unit != price_unit
    return False


def _unit(facts: list[dict], label: str) -> str | None:
    for f in facts:
        if f["label"] == label:
            return str(f.get("unit") or "")
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
# check(facts, risk_free_pct) -> float 0.0-1.0 (ไล่ระดับผ่าน, audit fix 19.3) | None (ข้อมูลไม่พอคำนวณ)
# ─────────────────────────────────────────────────────────────────────────────
def _criterion_roic_vs_wacc(facts, risk_free_pct):
    """#1: ROIC vs WACC แบบไล่ระดับ (ไม่ใช่ ROIC > 0 — 'โตแล้วเผาเงิน' ต้องได้ 0 เพราะ ROIC>0
    แทบไม่มีความหมาย). audit fix 19.3: เดิม cliff เป๊ะที่ ROIC=WACC พอดี — ไล่ระดับรอบ WACC±3pp แทน."""
    roic = _scalar(facts, "ROIC")
    if roic is None:
        return None
    beta = _scalar(facts, "Beta")
    wacc_pct = capm_wacc(beta, risk_free_pct) * 100.0
    return _graded_above(roic, wacc_pct, BAND_PCT)


def _criterion_net_margin_level(facts, _rf):
    """#2: Net Margin (ปีล่าสุด) vs 10% แบบไล่ระดับ — pricing power + cost discipline.
    audit fix 19.2: เดิมใช้ ROIC>=15% ซ้ำกับ #1 (ROIC>WACC) — ตัวเลขเดียวกันขับ 2 เกณฑ์ ถ้า
    invested-capital คำนวณผิดพลาดจะพังพร้อมกันทั้งคู่ (correlated error). Net Margin = Net
    Income/Revenue ไม่แชร์ input กับ NOPAT/invested-capital เลย (คนละ pipeline การคำนวณเต็มๆ)
    จึงกระจายความเสี่ยง และยังเป็นเกณฑ์คุณภาพมาตรฐาน (double-digit net margin) ที่ใช้กันทั่วไป.
    audit fix 19.3: ไล่ระดับรอบ 10%±3pp (AMZN 10.83% เคยผ่านเต็มจุดทั้งที่ห่างเกณฑ์แค่ 0.83pp)."""
    pts = _fy_series(facts, "Net Margin")
    if not pts:
        return None
    degree = _graded_above(pts[-1][1], NET_MARGIN_MIN_PCT, BAND_PCT)

    # ── fix 2026-08 (เจอจากการเทียบกับโมเดลอื่น): Net Margin เพียวๆ ให้เครดิตกำไรที่ 'ธุรกิจไม่ได้
    # ทำเอง' ได้เต็มจุด. เคสสังเคราะห์ที่ชัดที่สุด: Operating Margin 5% แต่ Net Margin 30% เพราะ
    # รายการภาษี -> เกณฑ์นี้ให้ 1.0 เต็ม ทั้งที่ธุรกิจจริงควรได้ 0.0. เคสจริงที่จุดชนวนคือ DUOL
    # (NM 39.91% vs OM 13.07%) ซึ่ง 'บังเอิญ' ไม่เปลี่ยนคะแนนเพราะ OM 13.07 เฉียดขอบ band ที่ 13.0
    # พอดี — บังเอิญรอด ไม่ใช่ถูกต้อง.
    #
    # แก้เป็น fuzzy AND กับ Operating Margin (รูปแบบเดียวกับเกณฑ์ #3 ที่ทำอยู่แล้ว): กำไรสุทธิที่
    # สูงกว่ากำไรจากการดำเนินงานจะไม่ได้เครดิตเกินกว่าที่ธุรกิจทำได้เอง. ทิศตรงข้าม (OM สูงกว่า NM
    # เช่น META) ไม่ถูกลงโทษเพิ่ม เพราะ NM เป็นตัวที่ต่ำกว่าและเป็นตัวผูกอยู่แล้ว — และการที่กำไร
    # ถูกกดใต้เส้น (ดอกเบี้ย/ภาษี) ก็เป็นความอ่อนแอจริงที่ควรนับ.
    #
    # หมายเหตุตั้งใจ: **ไม่เปลี่ยนชื่อ label** เพราะ scorecard.py (Phase 32) จับคู่เกณฑ์ข้ามวันด้วย
    # ชื่อ label ตรงๆ — เปลี่ยนชื่อ = เกณฑ์เก่าหายและเกณฑ์ใหม่โผล่พร้อมกันในวันเดียว ซึ่งจะถูกนับเป็น
    # ถัง 'data' (ข้อมูลฝั่งเราเปลี่ยน) ให้ทุก ticker พร้อมกัน = ตั้งธงปลอมทั้งกระดาน
    op = _fy_series(facts, "Operating Margin")
    if op and op[-1][0] == pts[-1][0]:      # ต้องเป็นงวดเดียวกันเท่านั้นถึงเทียบได้
        degree = min(degree, _graded_above(op[-1][1], NET_MARGIN_MIN_PCT, BAND_PCT))
    return degree


def _criterion_fcf_and_accruals(facts, _rf):
    """#3: FCF margin และ CFO/NI (accruals — คุณภาพกำไร) ไล่ระดับทั้งคู่ แล้วเอาค่าต่ำสุด (fuzzy AND).
    audit fix: เดิมใช้ CFO > NI เป๊ะๆ = knife-edge ไม่มี tolerance — บริษัทคุณภาพที่ CFO≈NI
    (เช่น AAPL CFO/NI=0.995 = กำไรเป็นเงินสดเกือบเต็ม) โดน fail เท่ากับบริษัทแต่งงบจริง เพราะ
    cliff อยู่ที่ CFO=NI พอดี. ใส่ tolerance 10% (CFO >= 0.9*NI) = 'กำไรเป็นเงินสดอย่างน้อย 90%'.
    NI <= 0 (ขาดทุน): accruals ratio ไร้ความหมาย -> เช็คแค่ FCF margin.
    audit fix 19.3: เดิม cliff เป๊ะที่ ratio=0.9 — ไล่ระดับรอบ 0.9±0.05 แทน. band แคบกว่าเกณฑ์อื่น
    โดยตั้งใจ: CFO/NI ต่ำกว่า 0.85 = กำไรไม่เป็นเงินสดจริงเกิน 15% ซึ่งเป็นสัญญาณคุณภาพกำไรที่ควร
    ได้ ~0 จริงๆ ไม่ใช่ให้อภัย (เช่น NVDA 0.8555 -> 0.06 คือยังแทบไม่ได้คะแนน ตามเจตนา) — graded
    ตรงนี้แก้แค่ knife-edge รอบ 0.9 (CFO≈NI) ไม่ได้ตั้งใจยกคะแนนให้เคสที่ accruals สูงจริง"""
    fcf_margin = _scalar(facts, "FCF Margin")
    cfo = _scalar(facts, "CFO")
    net_income = _scalar(facts, "Net Income")
    if fcf_margin is None or cfo is None or net_income is None:
        return None
    fcf_degree = _graded_above(fcf_margin, 0.0, BAND_PCT)
    if net_income <= 0:
        return fcf_degree
    accruals_degree = _graded_above(cfo / net_income, ACCRUALS_TOLERANCE, BAND_ACCRUALS_RATIO)
    return min(fcf_degree, accruals_degree)


def _criterion_revenue_growth(facts, _rf):
    """#4: Revenue CAGR vs 3% แบบไล่ระดับ (เหนือเงินเฟ้อจริง ไม่ใช่แค่ > 0%)."""
    v = _scalar(facts, "Revenue CAGR")
    return None if v is None else _graded_above(v, REVENUE_CAGR_THRESHOLD_PCT, BAND_PCT)


def _criterion_leverage(facts, _rf):
    """#5: มีเงินสดสุทธิ (Net Debt <= 0) ผ่านเต็ม 1.0 ทันที, ไม่งั้นไล่ระดับรอบ Net Debt/EBITDA=3±1x.
    audit fix: เดิมเช็ค trend YoY ด้วย ('ไม่เพิ่มขึ้น') ซึ่งพังกับบริษัท net-cash — ratio เป็นเลข
    ติดลบไร้ความหมาย (เช่น DUOL series -9.95 -> -6.29 fail เพราะ -6.29 > -9.95 ทั้งที่เทียบไม่ได้
    ตั้งแต่แรก). net-cash = ไม่มีความเสี่ยงหนี้เลย ควรผ่าน ไม่ใช่ fail. ตัด trend ออก เหลือ level.
    audit fix 19.3: level เองก็เคย cliff เป๊ะที่ 3x (เช่น SBUX 2.67x ผ่านเต็มจุดทั้งที่ใกล้เพดานมาก)."""
    net_debt = _scalar(facts, "Net Debt")
    if net_debt is not None and net_debt <= 0:
        return 1.0   # เงินสดสุทธิ = ปลอดภัยเรื่องหนี้ 100%
    nde = _scalar(facts, "Net Debt / EBITDA")
    return None if nde is None else _graded_below(nde, LEVERAGE_MAX_X, BAND_LEVERAGE_X)


def _criterion_solvency(facts, _rf):
    """#6: Interest Coverage ไล่ระดับรอบ 3x±1.5x ถ้ามีข้อมูล, ไม่งั้น fallback ไปเช็ค Net Debt <= 0
    (binary — ไม่มีตัวเลขต่อเนื่องให้ไล่ระดับในกรณี fallback).
    audit fix: แทนเกณฑ์เดิม 'Current Ratio > 1' ที่ลงโทษบริษัทอำนาจต่อรองสูง — AAPL รัน current
    ratio < 1 โดยตั้งใจ (จ่าย supplier ช้า เก็บเงินเร็ว) = จุดแข็ง working-capital ไม่ใช่จุดอ่อน.
    Interest coverage (EBIT/ดอกเบี้ย) วัด 'จ่ายหนี้ไหวไหม' ตรงกว่า.
    audit fix 19.2: เดิมเช็ค net_debt<=0 auto-pass 'ก่อน' Interest Coverage เสมอ — แต่ net-cash
    ไม่ได้แปลว่าไม่มีดอกเบี้ยต้องจ่ายจริง (มีหนี้ก้อนใหญ่ + เงินสดใหญ่กว่า ก็ยังจ่ายดอกเบี้ยจริงได้ ถ้า
    EBIT ไม่พอก็ยัง fail ได้จริง). สลับลำดับ: ใช้ Interest Coverage จริงก่อนเสมอถ้ามี ข้อมูล net-cash
    เป็นแค่ fallback ตอนไม่มี Interest Expense รายงานเลย (เช่น DUOL — ไม่มีหนี้จริง ไม่ใช่ data gap)."""
    cov = _scalar(facts, "Interest Coverage")
    if cov is not None:
        return _graded_above(cov, INTEREST_COVERAGE_MIN_X, BAND_COVERAGE_X)
    net_debt = _scalar(facts, "Net Debt")
    return None if net_debt is None else (1.0 if net_debt <= 0 else 0.0)


def _criterion_margin_improving(facts, _rf):
    """#7: Operating Margin YoY delta ไล่ระดับรอบ 0±1.5pp.
    audit fix 19.3: เดิม cliff เป๊ะที่ delta=0 (เช่น GOOGL 32.11%->32.03%, ลดแค่ 0.08pp ก็ fail
    เต็มจุด — root ของปัญหา score กระโดดเดิม)."""
    pts = _fy_series(facts, "Operating Margin")
    if len(pts) < 2:
        return None
    return _graded_above(pts[-1][1] - pts[-2][1], 0.0, BAND_MARGIN_TREND_PP)


def _criterion_not_diluting(facts, _rf):
    """#8: %เปลี่ยนจำนวนหุ้น YoY ไล่ระดับรอบ 0%±1.5% (ไม่เจือจางสุทธิ — ยิ่งลดยิ่งดี).
    audit fix 19.3: เดิม cliff เป๊ะที่ delta<=0 (เช่น SBUX เพิ่ม 0.22% ซึ่งเป็น noise-level ก็ fail
    เต็มจุดเท่ากับบริษัทที่ dilute หนักจริง). ใช้ %เปลี่ยน ไม่ใช่จำนวนหุ้นดิบ เพราะสเกลต่างกันคนละโลก
    ข้ามบริษัท (MSFT ~7.5พันล้านหุ้น vs DUOL ~46ล้านหุ้น)."""
    pts = _fy_series(facts, "Diluted Shares")
    if len(pts) < 2 or not pts[-2][1]:
        return None
    delta_pct = (pts[-1][1] - pts[-2][1]) / pts[-2][1] * 100.0
    return _graded_below(delta_pct, 0.0, BAND_DILUTION_PCT)


# ─────────────────────────────────────────────────────────────────────────────
# PART A' — ธนาคาร (Phase 33.3)
#
# ทำไมต้องมีชุดแยก ไม่ใช่ปรับเกณฑ์เดิม: เกณฑ์เดิม 5 ใน 8 ข้อ (ROIC>WACC, FCF+คุณภาพกำไร,
# หนี้ไม่บานปลาย, จ่ายดอกเบี้ยไหว, Margin ขยาย) ต้องใช้ตัวเลขที่ไม่มีความหมายกับธนาคาร — เงินฝาก
# ไม่ใช่ 'หนี้ที่บานปลาย' แต่คือวัตถุดิบ, การปล่อยสินเชื่อทำให้ CFO/FCF ติดลบมหาศาลโดยไม่ได้แปลว่า
# เผาเงิน (JPM: FCF -147,782,000,000 USD), และไม่มี Operating Margin ให้ดู trend. ผลคือ JPM
# คำนวณได้ 4/8 ตกด่านข้อมูล -> 'ประเมินไม่ได้' ทุกวันตั้งแต่เพิ่มเข้า watchlist
#
# ชุดนี้จงใจสร้างจาก 'สิ่งที่ดึงได้จริง' ไม่ใช่สิ่งที่อยากได้: CET1 / NPL / provisions ไม่มีใน
# yfinance จึงไม่มีในเกณฑ์ (แทนที่จะประมาณเอาเองแล้วให้คะแนนจากตัวเลขที่แต่งขึ้น) — ตัวหารคงที่ /8
# เหมือนกันเป๊ะ เพื่อให้คะแนนของแบงก์อยู่บนสเกลเดียวกับหุ้นตัวอื่นและเทียบกันได้จริง
# ─────────────────────────────────────────────────────────────────────────────
ROTCE_MIN_PCT = 12.0          # ผลตอบแทนต่อทุนที่จับต้องได้ — เกณฑ์คุณภาพหลักของธนาคาร
BANK_ROE_MIN_PCT = 10.0
BANK_NET_MARGIN_MIN_PCT = 20.0
EQUITY_TO_ASSETS_MIN_PCT = 6.0   # กันชนทุนต่อสินทรัพย์ — ตัวแทนหยาบของ CET1 ที่ดึงไม่ได้
NII_TO_ASSETS_MIN_PCT = 2.0      # กำลังหารายได้ของงบดุล (ตัวแทนหยาบของ NIM)
COST_INCOME_MAX_PCT = 65.0       # ต้นทุนรวม+ค่าเผื่อหนี้สูญต่อรายได้ — ต่ำกว่าดีกว่า
BAND_BANK_PCT = 2.0              # band ของเกณฑ์กลุ่มนี้ (แคบกว่าหุ้นทั่วไป: ตัวเลขแบงก์แกว่งน้อยกว่า)
BAND_COST_INCOME_PP = 5.0

# ขาราคาของแบงก์: ราคาสูงกว่า justified P/B กี่ % -> คะแนน /3 (รูปแบบเดียวกับ _gap_to_score
# แต่คนละ band โดยตั้งใจ — ดูเหตุผลใน _bank_valuation_score). ตั้งจากช่วงที่ P/B ของแบงก์
# กระจายตัวจริง (หลักสิบ %) ไม่ใช่หลักหน่วยแบบส่วนต่างอัตราการเติบโต
BANK_PREMIUM_FULL_PCT = 0.0    # ที่/ต่ำกว่ามูลค่าที่เป็นธรรม -> ~3 เต็ม
BANK_PREMIUM_GOOD_PCT = 15.0   # แพงกว่า ~15% -> ~2
BANK_PREMIUM_FAIR_PCT = 35.0   # แพงกว่า ~35% -> ~1, เกินไปมาก -> เข้าใกล้ 0
BANK_PREMIUM_BAND_PCT = 7.0


def _is_bank(facts: list[dict]) -> bool:
    """ตัดสินจาก 'ดอกเบี้ยรับสุทธิเป็นสัดส่วนหลักของรายได้' — ตรวจจาก facts ล้วนเพื่อให้พาธ
    backfill (อ่านจาก DB) ได้ผลเดียวกับตอนวิเคราะห์สด. ไม่ใช้ sector string เพราะไม่ได้เก็บลง
    facts และ 'Financial Services' รวมประกัน/บลจ. ซึ่งอ่านด้วยกรอบนี้ไม่ได้เหมือนกัน."""
    nii = _scalar(facts, "Net Interest Income")
    revenue = _scalar(facts, "Revenue")
    return nii is not None and bool(revenue) and (nii / revenue) >= 0.20


def _criterion_rotce(facts, _rf):
    v = _scalar(facts, "ROTCE")
    return None if v is None else _graded_above(v, ROTCE_MIN_PCT, BAND_BANK_PCT)


def _criterion_bank_roe(facts, _rf):
    pts = _fy_series(facts, "ROE")
    v = pts[-1][1] if pts else _scalar(facts, "ROE")
    return None if v is None else _graded_above(v, BANK_ROE_MIN_PCT, BAND_BANK_PCT)


def _criterion_bank_net_margin(facts, _rf):
    pts = _fy_series(facts, "Net Margin")
    return None if not pts else _graded_above(pts[-1][1], BANK_NET_MARGIN_MIN_PCT, BAND_BANK_PCT)


def _criterion_capital_cushion(facts, _rf):
    v = _scalar(facts, "Equity / Assets")
    return None if v is None else _graded_above(v, EQUITY_TO_ASSETS_MIN_PCT, BAND_BANK_PCT)


def _criterion_nii_to_assets(facts, _rf):
    v = _scalar(facts, "NII / Assets")
    return None if v is None else _graded_above(v, NII_TO_ASSETS_MIN_PCT, 0.5)


def _criterion_cost_income(facts, _rf):
    v = _scalar(facts, "Cost+Provision / Revenue")
    return None if v is None else _graded_below(v, COST_INCOME_MAX_PCT, BAND_COST_INCOME_PP)


BANK_CRITERIA = [
    ("ROTCE สูง(>=12%)", _criterion_rotce),
    ("ROE สูง(>=10%)", _criterion_bank_roe),
    ("Net Margin สูง(>=20%)", _criterion_bank_net_margin),
    ("กันชนทุน (Equity/Assets>=6%)", _criterion_capital_cushion),
    ("งบดุลหารายได้ได้ (NII/Assets>=2%)", _criterion_nii_to_assets),
    ("คุมต้นทุน+หนี้เสีย(<=65%)", _criterion_cost_income),
    ("รายได้เติบโตจริง(>3%)", _criterion_revenue_growth),
    ("ไม่เจือจางหุ้น", _criterion_not_diluting),
]


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
    """คืน dict: score (float 0.0-8.0 หรือ None ถ้า disqualify), computable, passed, criteria
    (list ของ (label, float 0.0-1.0 | None)), disqualified (bool), reason (str|None).
    audit fix 19.3: score เดิมเป็น int (นับ True ตรงๆ) ตอนนี้เป็นผลรวม degree ต่อเนื่อง — ไล่ระดับ
    ทุกเกณฑ์ (ดู _graded_above/_graded_below) กัน binary-cliff swing คะแนนจากตัวเลขขยับนิดเดียว."""
    # Phase 33.3: ธนาคารใช้เกณฑ์คนละชุด (ตัวหารยัง /8 เท่ากัน -> คะแนนอยู่บนสเกลเดียวกัน
    # เทียบกับหุ้นตัวอื่นในพอร์ตได้ตรงๆ) — ดู BANK_CRITERIA ว่าทำไมปรับเกณฑ์เดิมแทนไม่ได้
    is_bank = _is_bank(facts)
    criteria = BANK_CRITERIA if is_bank else PIOTROSKI_CRITERIA
    results = [(label, check(facts, risk_free_pct)) for label, check in criteria]
    computable = sum(1 for _, d in results if d is not None)
    passed = round(sum(d for _, d in results if d is not None), 2)

    if computable < DATA_GATE_MIN_CRITERIA:
        return {
            "score": None, "computable": computable, "passed": passed, "criteria": results,
            "disqualified": True, "framework": "bank" if is_bank else "standard",
            "reason": f"ข้อมูลไม่พอ: คำนวณเกณฑ์พื้นฐานได้แค่ {computable}/8 (ต้องการ >= {DATA_GATE_MIN_CRITERIA}) — ตัดออกจาก screen นี้",
        }

    passed_labels = [label for label, d in results if d is not None and d >= 0.5]
    prefix = "พื้นฐาน (เกณฑ์ธนาคาร)" if is_bank else "พื้นฐาน"
    reason = f"{prefix}: ผ่าน {passed:.1f}/8 เกณฑ์ ({', '.join(passed_labels) if passed_labels else 'ไม่ผ่านเลย'}) (+{passed:.1f}/8)"
    return {"score": passed, "computable": computable, "passed": passed, "criteria": results,
            "disqualified": False, "framework": "bank" if is_bank else "standard",
            "reason": reason}


# ─────────────────────────────────────────────────────────────────────────────
# PART B — Valuation reverse-DCF (/3) — ใช้ score จาก reverse_dcf() ตรงๆ (step-function
# gap bands อยู่ในนั้นแล้ว, ดู src/agent/valuation.py::_gap_to_score)
# ─────────────────────────────────────────────────────────────────────────────
def _period_of(facts: list[dict], label: str) -> str | None:
    """ป้ายงวดของ Fact นั้น — สำหรับ 'FCF CAGR (long-run)' งวดคือช่วงที่วัด ('FY2007-FY2025')."""
    return next((f.get("period") for f in facts if f.get("label") == label), None)


def _window_years(window: str | None) -> int | None:
    """จำนวนปีในช่วง 'FY2007-FY2025' — อ่านไม่ออกก็คืน None ไม่เดา."""
    if not window or "-" not in window:
        return None
    try:
        start, end = (int("".join(ch for ch in part if ch.isdigit())) for part in window.split("-", 1))
    except ValueError:
        return None
    return end - start + 1 if end >= start else None


def _build_duck_fundamentals(facts: list[dict]) -> SimpleNamespace:
    """ประกอบ duck-object จาก facts ให้ reverse_dcf() ใช้ — path เดียวกันทั้งตอนวิเคราะห์สด
    (facts จาก fundamentals_obj.to_facts()) และตอน backfill ย้อนหลัง (facts จาก DB/JSON)."""
    fcf_yield = _scalar(facts, "FCF Yield")
    market_cap = _scalar(facts, "Market Cap")
    fcf = (fcf_yield / 100.0 * market_cap) if fcf_yield is not None and market_cap else None
    return SimpleNamespace(
        # ตรวจสกุลเงินจาก 'ป้ายหน่วย' ของ Fact ไม่ใช่จาก object ต้นทาง — path นี้ต้องทำงานกับ
        # facts ที่อ่านจาก DB ตอน backfill ด้วย ซึ่งไม่มี object ให้ถามแล้ว. แถวเก่าที่ยังติดป้าย
        # 'USD' ทั้งคู่จะได้ False = พฤติกรรมเดิมเป๊ะ (ไม่ไปรื้อประวัติ) ส่วนแถวใหม่จะจับได้เอง
        currency_mismatch=_currency_mismatch(facts),
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
        # Phase 36: anchor จากประวัติ FCF ที่ยื่น ก.ล.ต. — เก็บเป็น Fact ไว้ (ไม่ใช่แค่ attribute
        # บน object) ก็เพื่อให้พาธนี้อ่านค่าเดียวกันได้ แถวเก่าที่ไม่มี Fact นี้ -> None -> ใช้
        # หน้าต่างเดิม = ประวัติที่บันทึกไว้แล้วไม่ถูกเขียนใหม่ย้อนหลัง
        fcf_cagr_long=_scalar(facts, "FCF CAGR (long-run)"),
        fcf_long_window=_period_of(facts, "FCF CAGR (long-run)"),
        fcf_long_years=_window_years(_period_of(facts, "FCF CAGR (long-run)")),
    )


def _bank_valuation_score(facts: list[dict], risk_free_pct: float) -> dict:
    """ขาราคาของธนาคาร — reverse-DCF ใช้ไม่ได้เลย (FCF ของแบงก์ไม่ใช่ 'เงินสดอิสระ' แต่คือผลของ
    การปล่อยสินเชื่อ/เงินฝากที่ไหลผ่านงบ) เลนส์มาตรฐานของกลุ่มนี้คือ **justified P/B**:

        P/B ที่เป็นธรรม = (ROTCE − g) / (COE − g)

    ธนาคารที่ทำ ROTCE ได้สูงกว่าต้นทุนส่วนของผู้ถือหุ้นควรซื้อขายเหนือมูลค่าทางบัญชี และสูงกว่า
    มากแค่ไหนขึ้นกับส่วนต่างนั้น — เป็นสูตรเดียวกับที่ใช้กันทั้งอุตสาหกรรม ไม่ใช่ที่คิดขึ้นเอง.
    COE ใช้ CAPM ตัวเดียวกับที่ reverse-DCF ใช้ (capm_wacc = Rf + β×ERP) เพื่อให้สมมติฐาน
    ต้นทุนเงินทุนของทั้งพอร์ตมาจากที่เดียวกัน. g = terminal growth ตัวเดียวกัน.

    ให้คะแนน 0-3 ด้วย **รูปแบบเดียวกับ _gap_to_score (graded ซ้อนสามชั้น) แต่ตั้ง band เอง** —
    จงใจไม่ยืม GAP_PP_* มาใช้ตรงๆ แม้ทั้งคู่จะมีหน่วยเป็น '%' เพราะมันคนละของกัน: ของ reverse-DCF
    คือ 'ส่วนต่างอัตราการเติบโตต่อปี' ซึ่ง 10pp = มหาศาล ส่วนของที่นี่คือ 'ราคาสูงกว่ามูลค่าที่
    เป็นธรรมกี่ %' ซึ่ง 10% = เรื่องปกติมาก. ถ้าใช้ band เดียวกันจริง แบงก์เกือบทุกตัวจะกองอยู่ที่
    0 หรือ 3 โดยแทบไม่มีตรงกลาง = กลับไปเป็น binary cliff ที่ audit 19.3 อุตส่าห์แก้ไปแล้ว.
    """
    rotce = _scalar(facts, "ROTCE")
    pb = _scalar(facts, "P/B")
    beta = _scalar(facts, "Beta")
    if rotce is None or pb is None or pb <= 0:
        return {"score": None, "excluded": True,
                "reason": "ไม่มี ROTCE/P-B พอประเมินราคาแบบธนาคาร — ตัดออกจาก screen นี้"}

    coe_pct = capm_wacc(beta, risk_free_pct) * 100.0
    g_pct = DEFAULT_TERMINAL_GROWTH * 100.0
    if coe_pct - g_pct <= 0:
        return {"score": None, "excluded": True,
                "reason": "ต้นทุนส่วนของผู้ถือหุ้นต่ำกว่าการเติบโตระยะยาว — สูตร justified P/B ใช้ไม่ได้"}

    justified_pb = (rotce - g_pct) / (coe_pct - g_pct)
    if justified_pb <= 0:
        return {"score": None, "excluded": True, "justified_pb": round(justified_pb, 2),
                "reason": "ROTCE ต่ำกว่าการเติบโตระยะยาว — ธนาคารกำลังทำลายมูลค่า ประเมินด้วยสูตรนี้ไม่ได้"}

    # premium เป็น % ของ justified — แปลงเป็น pp เพื่อป้อน _gap_to_score ที่ออกแบบมาสำหรับ
    # 'ตลาดคาดหวังเกินจริงกี่ pp' (บวก = แพงกว่าที่ควร ซึ่งตรงทิศกับ gap ของ reverse-DCF)
    premium_pp = round((pb / justified_pb - 1) * 100, 2)
    score = round(
        _graded_below(premium_pp, BANK_PREMIUM_FULL_PCT, BANK_PREMIUM_BAND_PCT)
        + _graded_below(premium_pp, BANK_PREMIUM_GOOD_PCT, BANK_PREMIUM_BAND_PCT)
        + _graded_below(premium_pp, BANK_PREMIUM_FAIR_PCT, BANK_PREMIUM_BAND_PCT),
        2,
    )
    return {
        "score": score, "excluded": False, "lens": "bank_pb",
        "rotce": rotce, "pb": pb, "justified_pb": round(justified_pb, 2),
        "premium_pct": premium_pp, "coe": round(coe_pct, 2),
        "terminal_growth": round(g_pct, 2),
        "reason": (f"ราคา (เกณฑ์ธนาคาร): P/B {pb:.2f}x เทียบ justified P/B {justified_pb:.2f}x "
                   f"จาก ROTCE {rotce:.1f}% และ COE {coe_pct:.1f}% "
                   f"(premium {premium_pp:+.1f}%) (+{score}/3)"),
    }


def _valuation_score(facts: list[dict], risk_free_pct: float) -> dict:
    """คืน dict: score (0-3 หรือ None), excluded (bool), reason (str|None), + field อื่นจาก
    reverse_dcf() ทั้งหมด (implied_growth/realistic_growth/gap/wacc/...) เพื่อความโปร่งใส."""
    duck = _build_duck_fundamentals(facts)
    dcf = reverse_dcf(duck, risk_free_pct=risk_free_pct)
    if dcf is None:
        reason = ("งบกับราคาคนละสกุลเงิน — คำนวณ EV/reverse-DCF ไม่ได้"
                  if duck.currency_mismatch else "ไม่มี Market Cap/FCF พอคำนวณ reverse-DCF")
        return {"score": None, "excluded": True, "reason": f"{reason} — ตัดออกจาก screen นี้"}
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
# PART C — News/sentiment — metadata เท่านั้น (Phase 19.3.1: ไม่รวมในคะแนนแล้ว)
# เดิมตั้งใจให้เป็น "tie-breaker, ห้ามพลิกผลของ /8+/3" แต่วัดจริงจากประวัติ (84 คู่) พบว่า
# sentiment เป็นตัวขับ 57.4% ของทุกรอบที่คะแนนกระโดด >=0.5 — พลิก bullish<->neutral รายวัน
# ทำให้คะแนนสุขภาพธุรกิจเต้นตามข่าว ทั้งที่พื้นฐาน/ราคาไม่ได้เปลี่ยน (ขัดทั้งเจตนาเดิมและหลัก
# ข่าวรายวัน=noise ของโปรเจกต์) ยังคำนวณ+โชว์ไว้เป็นเหตุผลประกอบ (reasons/components) แต่ไม่บวก
# เข้า score อีกต่อไป
# ─────────────────────────────────────────────────────────────────────────────
def _sentiment_points(summary) -> tuple[float, str]:
    pts = SENTIMENT_PTS.get(summary.sentiment, 0.5)
    return pts, f"มุมมองข่าว {summary.sentiment} (ไม่กระทบคะแนน, อ้างอิงเท่านั้น)"


# ─────────────────────────────────────────────────────────────────────────────
# รวมคะแนน
# ─────────────────────────────────────────────────────────────────────────────
def compute_health(summary, breaches: list[dict] | None = None, facts=None,
                    risk_free_pct: float = FALLBACK_RISK_FREE_PCT) -> dict:
    """summary = Pydantic Summary (ต้องการ sentiment เท่านั้นตอนนี้ — ใช้เป็น metadata/เหตุผล
    ประกอบเท่านั้นตั้งแต่ 19.3.1, ไม่บวกเข้าคะแนน — fundamental_strength/valuation_view ของ LLM
    ก็ไม่ได้ใช้ในคะแนนแล้วเช่นกัน เพราะ Phase 18 ยึดตัวเลขจริงล้วนไม่มี fallback),
    breaches = check_invalidation()['breaches'], facts = list[Fact]/list[dict] ของรอบนี้,
    risk_free_pct = อัตราพันธบัตร 10 ปี ณ วันรัน (จาก src.providers.stock.market).

    คืน dict: score (0-11 หรือ None ถ้า 'excluded' — ข้อมูลไม่พอ/ขาดทุน/crypto ไม่เข้าเกณฑ์ระบบนี้),
    tier (strong/ok/weak/excluded), label, reasons, fundamental (dict ละเอียด),
    valuation (dict ละเอียดจาก reverse_dcf), components (4 key เดิม — sentiment เป็น metadata
    ไม่กระทบ score, ค่าเป็น None ได้เมื่อ excluded)."""
    facts = _normalize_facts(facts)

    fundamental = _fundamental_score(facts, risk_free_pct)
    # ธนาคารใช้เลนส์ราคาคนละตัว (justified P/B) เพราะ reverse-DCF ตีความ FCF ของแบงก์ไม่ได้ —
    # คะแนนยังเป็น /3 บนสเกลเดียวกัน (ยืม _gap_to_score ตัวเดียวกัน) จึงรวมเป็น /11 ได้ตามปกติ
    valuation = (_bank_valuation_score(facts, risk_free_pct) if _is_bank(facts)
                 else _valuation_score(facts, risk_free_pct))
    sentiment_pts, sentiment_reason = _sentiment_points(summary)

    # พื้นฐานไม่ผ่าน data gate = ประเมินอะไรไม่ได้เลยจริงๆ (เช่น crypto: คำนวณได้ 0/8) -> excluded
    if fundamental["disqualified"]:
        return {
            "score": None, "max": TOTAL_MAX, "tier": "excluded", "label": "ประเมินไม่ได้",
            "partial": False, "reasons": [fundamental["reason"]],
            "fundamental": fundamental, "valuation": valuation,
            "components": {"strength": fundamental["score"], "valuation": valuation["score"],
                            "sentiment": sentiment_pts, "breach_penalty": None},
        }

    # Phase 29: พื้นฐานคำนวณได้ แต่ขาราคาไม่ได้ (ส่วนใหญ่ = FCF ฐานติดลบ -> reverse-DCF ใช้ไม่ได้
    # กับบริษัทที่ยัง burn cash) — เดิมเคสนี้ถูกตัดทิ้งทั้งก้อนเป็น excluded ทำให้ SPCX ถูกวิเคราะห์
    # ทุกวันแต่ 'ตัวเลขที่ผู้ใช้อ่านจริง' ว่างเปล่าตลอด ทั้งที่ฝั่งพื้นฐาน /8 คำนวณได้ปกติ และกลุ่ม
    # 'โตเร็วแต่ยังไม่กำไร' คือกลุ่มที่มือใหม่ต้องการตัวช่วยที่สุด (DUOL เองก็เคยอยู่สถานะนี้).
    #
    # คืนคะแนน 'พื้นฐานล้วน /8' แทน โดย **ไม่** normalize ขึ้นเป็น /11 (นั่นคือการเสกคะแนนราคา
    # ที่ไม่มีอยู่จริง = fake precision) — max=8 ติดไปกับผลลัพธ์ และ partial=True ให้ทุกฝั่งที่
    # 'เปรียบเทียบ/จัดอันดับ/ลากกราฟ' รู้ว่าห้ามเอาไปเทียบกับ /11 ตรงๆ (ดู comparable_score()
    # ที่ตัดค่าพวกนี้ออกจากคอลัมน์ health_score ก่อนลง DB)
    if valuation["excluded"]:
        score = fundamental["score"]
        reasons = [
            fundamental["reason"],
            f"ราคา: {valuation['reason']}",
            f"คะแนนนี้เป็น 'พื้นฐานล้วน' เต็ม {PARTIAL_MAX:.0f} (ไม่มีขาราคา) — เทียบกับตัวที่ได้เต็ม "
            f"{TOTAL_MAX:.0f} ตรงๆ ไม่ได้",
            sentiment_reason,
        ]
        has_breach = any(b.get("severity") == "alert" for b in (breaches or []))
        breach_penalty = -3.0 if has_breach else 0.0
        if has_breach:
            score += breach_penalty
            reasons.append("เงื่อนไขออกโดนแตะ (−3)")
        score = round(max(0.0, min(PARTIAL_MAX, score)), 1)
        tier, label = tier_from_score(score, PARTIAL_MAX)
        return {
            "score": score, "max": PARTIAL_MAX, "tier": tier, "label": label,
            "partial": True, "reasons": reasons,
            "fundamental": fundamental, "valuation": valuation,
            "components": {"strength": fundamental["score"], "valuation": None,
                            "sentiment": sentiment_pts, "breach_penalty": breach_penalty},
        }

    # sentiment_reason ยังโชว์ให้เห็นมุมมองข่าววันนี้ (โปร่งใส) แต่ sentiment_pts ไม่บวกเข้า score
    # อีกต่อไป (19.3.1) — ดูเหตุผลที่ PART C ด้านบน
    reasons = [fundamental["reason"], valuation["reason"], sentiment_reason]
    score = fundamental["score"] + valuation["score"]

    has_breach = any(b.get("severity") == "alert" for b in (breaches or []))
    breach_penalty = -3.0 if has_breach else 0.0
    if has_breach:
        score += breach_penalty
        reasons.append("เงื่อนไขออกโดนแตะ (−3)")

    score = max(0.0, min(TOTAL_MAX, score))
    rounded = round(score, 1)
    tier, label = tier_from_score(rounded)

    return {
        "score": rounded, "max": TOTAL_MAX, "tier": tier, "label": label, "reasons": reasons,
        "partial": False,
        "fundamental": fundamental, "valuation": valuation,
        "components": {"strength": fundamental["score"], "valuation": valuation["score"],
                        "sentiment": sentiment_pts, "breach_penalty": breach_penalty},
    }


def comparable_score(health: dict | None) -> float | None:
    """คะแนนที่เอาไป 'เทียบข้ามตัว/ข้ามเวลา' ได้จริง — None ถ้าเป็น partial (Phase 29) หรือ excluded.

    เหตุผลที่ต้องมีตัวกรองนี้แทนที่จะเก็บดิบๆ: คอลัมน์ analyses.health_score ถูกใช้เป็น 'สนาม
    เปรียบเทียบ' หลายที่ (sparkline รายวัน, health-at-entry ของ Phase 20.3, changes.py health_jump)
    ซึ่งทุกที่สมมติเงียบๆ ว่าทุกค่าอยู่บนสเกลเดียวกัน. ถ้าปล่อยคะแนน /8 ลงคอลัมน์เดียวกับ /11
    กราฟจะกระโดดเองตอนบริษัทเริ่มมี FCF เป็นบวก (สเกลเปลี่ยน ไม่ใช่ธุรกิจเปลี่ยน) และการวัดว่า
    'ซื้อตอน health สูงชนะ VT ไหม' จะปนคนละหน่วยกัน. คะแนน partial จึงอยู่ใน health JSON
    (ให้ UI แสดงได้เต็มที่) แต่ไม่ลงคอลัมน์ตัวเลขที่ใช้เทียบ."""
    if not health or health.get("partial"):
        return None
    return health.get("score")