"""Reverse-DCF (Phase 18, per scoring_spec.md, + valuation_guard_growth_lens.md): แทนที่จะ
พยากรณ์ growth แล้วคำนวณราคา (DCF ปกติ, พยากรณ์ผิดง่าย), เราแก้สมการย้อนกลับ — เอา 'ราคาตลาด
ปัจจุบัน' ตั้งเป็นโจทย์ แล้วหาว่า 'ตลาดกำลัง price การเติบโตของ FCF ไว้ที่กี่ % ต่อปี' (implied
growth) ถึงจะได้ราคานี้พอดี แล้วเทียบกับ 'realistic_growth' ห่างกันแค่ไหน

ค่าคงที่ต้องล็อกเหมือนกันทุกหุ้น (ตามกฎเหล็กของสเปก — ห้ามให้อะไรลอยตามใจนอกจาก FCF/β/ตัวที่
solve ไม่งั้น cheap พลิกเป็น expensive ได้ง่ายๆ และเทียบข้ามหุ้นไม่ได้เลย):
- Forecast horizon 10 ปี, Terminal growth 2.5%, ERP มาตรฐาน (ไม่ลอยตามหุ้น)
- WACC = CAPM (Rf + β×ERP) — Rf ล็อกเป็นค่าเดียว ณ วันรัน (ตลาดรวม ไม่ใช่ต่อหุ้น), β ตั้งเพดาน
  [0.7, 1.6] กัน beta เพี้ยนของหุ้นเล็กมาบิด WACC
- FCF base = ค่าเฉลี่ย FCF 3 ปีย้อนหลัง (กันปีที่ผิดปกติปีเดียวมาบิดผลทั้งโมเดล)
- EV target = Market Cap + Net Debt (bridge หนี้เข้าไปด้วยถึงจะเทียบข้ามหุ้นที่มี leverage
  ต่างกันได้ยุติธรรม)

realistic_growth: sustainable_growth (reinvestment_rate × ROIC) เป็น 'value lens' ค่าเริ่มต้น
— แต่สูตรนี้พังกับหุ้น asset-light + deferred-revenue (เช่น DUOL: ΔNWC ติดลบเพราะลูกค้าจ่าย
ล่วงหน้าทำให้ reinvestment_rate ติดลบทั้งที่บริษัทโตจริง 40%+) valuation_guard() ตรวจจับกรณีนี้
(NOPAT บางเฉียบ/reinvestment ติดลบ/sustainable ขัดแย้งกับ CAGR จริงมหาศาล) แล้ว route ไป
'growth lens' แทน — ใช้ growth ล่าสุดจริงที่ fade ลงหา terminal เป็น anchor แทนสูตรที่พัง พร้อม
Rule-of-40 modifier กันหุ้นที่ 'โตไม่จริง+เผาเงิน' ถูกตัดสินว่าถูกอย่างผิดๆ

Phase 19.4 (2026-07, audit): แก้ 2 บั๊ก/design gap ที่พบตอนตรวจ reverse-DCF ต่อจาก 19.3.1 —
(1) `_fcf_base_3yr` เดิม assume fcf_series เรียงใหม่->เก่าเสมอแล้วหยิบ [:3] ตรงๆ แต่พาธที่ใช้
คำนวณ valuation component ของ health score (health.py::_build_duck_fundamentals) ป้อนเรียง
เก่า->ใหม่ (ตรงข้าม) ทำให้หยิบ 3 ปีเก่าสุดแทนที่จะเป็นล่าสุด — ยืนยันจริงกับ NVDA: fcf_base ต่ำกว่า
ความจริงถึง 2 เท่า (30.6B vs 61.5B) เพราะเป็นบริษัทโตเร็ว 3 ปีเก่าสุดกับล่าสุดต่างกันมหาศาล ตอนนี้
sort เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา) เหมือน _rev_growth_recent. (2) growth lens เดิมเทียบ
implied_growth (FCF growth ที่ตลาด price ไว้) กับ realistic_growth ที่ anchor จาก REVENUE growth —
apples-to-oranges เวลา margin กำลังขยายตัว (FCF โตเร็วกว่า revenue เป็นปกติจาก operating leverage)
ตอนนี้ anchor จาก FCF CAGR ก่อนเสมอถ้าคำนวณได้ (unit เดียวกับ implied_growth ตรงๆ) fallback ไป
revenue growth เฉพาะตอน FCF history สั้นเกินไป/สลับเครื่องหมาย. Backfill dry-run บน watchlist จริง:
14/107 แถวคะแนนเปลี่ยน (NVDA/GOOGL/MSFT +1.0 แต้ม จากขา fcf_base — DUOL เจอบั๊กจริงเหมือนกันแต่
score ไม่ขยับเพราะ gap ติดลบมากอยู่แล้วทั้งก่อน/หลัง).
"""
from dataclasses import dataclass

DEFAULT_TERMINAL_GROWTH = 0.025  # โตตลอดไปเท่า GDP/เงินเฟ้อระยะยาวโดยประมาณ — ห้ามสูงกว่านี้
DEFAULT_YEARS = 10
DEFAULT_ERP = 0.0525              # equity risk premium มาตรฐาน (จุดกึ่งกลาง 5-5.5%) — ล็อกค่าเดียว
FALLBACK_RISK_FREE_PCT = 4.0      # ใช้ตอนดึง ^TNX ไม่ได้ (ดู src/providers/stock/market.py)

BETA_FLOOR = 0.7   # กัน beta ของหุ้นเล็ก/ข้อมูลเพี้ยนมาบิด WACC จนเทียบข้ามหุ้นไม่ได้
BETA_CAP = 1.6

SUSTAINABLE_GROWTH_CAP = 0.20     # value lens: ไม่มีบริษัทไหนโตสองหลักสูงได้ตลอด 10 ปี
CAP_INITIAL_GROWTH = 0.35         # growth lens: เพดาน growth ปีแรก (ไม่เชื่อว่ายั่งยืนเกินนี้)
MIN_NOPAT_MARGIN = 0.02           # NOPAT/Revenue ต่ำกว่านี้ = ฐานไม่นิ่ง ratio ระเบิด -> NOPAT_UNSTABLE
DIVERGENCE_TRIGGER_PP = 15.0      # |sustainable − historical CAGR| (pp) เกินนี้ = ไม่ไว้ใจ sustainable
RULE40_WEAK = 20.0                # (growth% + FCF margin%) ต่ำกว่านี้ = โตไม่จริง (growth lens เท่านั้น)

# ขอบเขตการเติบโตที่โมเดลนี้ยอมแก้สมการหา (-30% ถึง +60% ต่อปี) — นอกช่วงนี้ถือว่า
# 'ราคาสุดโต่งเกินกว่าจะตีความเป็นตัวเลข growth ที่มีความหมาย'
_GROWTH_LO = -0.30
_GROWTH_HI = 0.60
_TOLERANCE = 1e-6
_MAX_ITER = 200


def intrinsic_value(
    fcf_base: float, growth: float, discount_rate: float, terminal_growth: float, years: int
) -> float:
    """PV ของ FCF ที่โต `growth`/ปี เป็นเวลา `years` ปี + terminal value (Gordon growth)
    ที่ปีสุดท้าย คิดลดกลับมาปัจจุบัน. Monotonic เพิ่มขึ้นตาม growth (growth สูง = value สูง)
    — สมบัตินี้คือสิ่งที่ทำให้ bisection หา implied growth ด้านล่างใช้ได้. เทียบกับ EV (ไม่ใช่
    market cap ตรงๆ) จึง 'fcf_base'/'discount_rate' ต้องเป็น WACC-level ไม่ใช่ cost-of-equity."""
    pv = 0.0
    cash_flow = fcf_base
    for t in range(1, years + 1):
        cash_flow = cash_flow * (1 + growth)
        pv += cash_flow / (1 + discount_rate) ** t
    terminal_fcf = cash_flow * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv += terminal_value / (1 + discount_rate) ** years
    return pv


def implied_growth_rate(
    target_value: float,
    fcf_base: float,
    discount_rate: float,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> float | None:
    """หา growth g ที่ intrinsic_value(fcf_base, g, ...) == target_value พอดี (bisection).
    คืน None ถ้าแก้ไม่ได้จริงๆ: โมเดลไม่ valid (discount_rate <= terminal_growth) หรือ
    target_value อยู่นอกช่วง [_GROWTH_LO, _GROWTH_HI] ที่โมเดลนี้ตีความได้."""
    if discount_rate <= terminal_growth:
        return None

    lo, hi = _GROWTH_LO, _GROWTH_HI
    value_lo = intrinsic_value(fcf_base, lo, discount_rate, terminal_growth, years)
    value_hi = intrinsic_value(fcf_base, hi, discount_rate, terminal_growth, years)
    if target_value < value_lo or target_value > value_hi:
        return None  # นอกขอบเขตที่โมเดลตีความได้

    for _ in range(_MAX_ITER):
        mid = (lo + hi) / 2
        value_mid = intrinsic_value(fcf_base, mid, discount_rate, terminal_growth, years)
        if abs(value_mid - target_value) < max(1.0, target_value * _TOLERANCE):
            return round(mid * 100, 2)
        if value_mid < target_value:
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) * 100, 2)


def capm_wacc(beta: float | None, risk_free_pct: float, erp: float = DEFAULT_ERP) -> float:
    """WACC มาตรฐาน = Rf + β×ERP (CAPM). β clamp ไว้ [BETA_FLOOR, BETA_CAP] เสมอ — ตัวเดียวใน
    สูตรทั้งหมดที่ 'ต่างกันได้ตามหุ้น' ที่เหลือ (Rf ณ วันรัน, ERP) ล็อกเดียวกันทุกตัวเพื่อให้ gap
    เทียบข้ามหุ้นได้จริง. β ไม่มี (ข้อมูลขาด) -> ใช้ 1.0 (ความเสี่ยงเท่าตลาดเฉลี่ย, ค่ากลาง)."""
    b = 1.0 if beta is None else max(BETA_FLOOR, min(BETA_CAP, beta))
    return (risk_free_pct / 100.0) + b * erp


def reinvestment_rate(
    capex: float | None, da: float | None, nwc_change: float | None, nopat: float | None,
) -> float | None:
    """(Capex_จริง − D&A + ΔNWC_จริง) / NOPAT — สัดส่วนกำไรที่ลงทุนกลับเข้าธุรกิจ.
    capex/nwc_change เป็นเลขลบตามธรรมเนียม cash-flow statement ของ yfinance (เงินสดไหลออก),
    da เป็นเลขบวก (ธรรมเนียม add-back) — พลิกเครื่องหมาย capex/nwc_change ก่อนคำนวณ (ต้องการ
    'เงินลงทุนจริง'/'NWC ที่เพิ่มขึ้นจริง' เป็นบวก ไม่ใช่ทิศทางกระแสเงินสด). บริษัท deferred-
    revenue สูง (ลูกค้าจ่ายล่วงหน้า) จะได้ nwc_change เป็นบวกมาก (เงินสดไหลเข้าจาก NWC) ->
    real_nwc_increase ติดลบมาก -> reinvestment ติดลบได้ทั้งที่บริษัทโตจริง (ดู valuation_guard)."""
    if capex is None or da is None or nwc_change is None or not nopat:
        return None
    real_capex = -capex
    real_nwc_increase = -nwc_change
    return (real_capex - da + real_nwc_increase) / nopat


def sustainable_growth_rate(
    capex: float | None, da: float | None, nwc_change: float | None,
    nopat: float | None, roic_pct: float | None,
) -> float | None:
    """sustainable_growth = reinvestment_rate × ROIC (excess-returns growth model)."""
    rr = reinvestment_rate(capex, da, nwc_change, nopat)
    if rr is None or roic_pct is None:
        return None
    return rr * (roic_pct / 100.0)


def valuation_guard(
    fcf_base: float | None, nopat: float | None, revenue: float | None,
    capex: float | None, da: float | None, nwc_change: float | None,
    roic_pct: float | None, historical_cagr: float | None,
) -> tuple[str, list[str], float | None]:
    """ตรวจว่า sustainable_growth เชื่อถือได้ไหมก่อนใช้เป็น realistic_growth หลัก (value lens)
    — คืน (route, flags, sustainable_pct). route: 'NA' (คำนวณ reverse-DCF ไม่ได้เลย) |
    'growth' (sustainable ไม่น่าเชื่อถือ -> ใช้ growth lens แทน) | 'standard' (ใช้ sustainable
    ตามปกติ). sustainable_pct เป็น % (เทียบหน่วยกับ historical_cagr ได้ตรงๆ)."""
    if fcf_base is None or fcf_base <= 0:
        return "NA", ["FCF_NONPOSITIVE"], None

    flags: list[str] = []
    nopat_margin = (nopat / revenue) if (nopat and revenue) else None
    if nopat is None or nopat <= 0 or (nopat_margin is not None and nopat_margin < MIN_NOPAT_MARGIN):
        flags.append("NOPAT_UNSTABLE")

    rr = reinvestment_rate(capex, da, nwc_change, nopat)
    if rr is not None and rr < 0:
        flags.append("NEGATIVE_REINVESTMENT")

    sustainable_pct = round(rr * roic_pct, 2) if (rr is not None and roic_pct is not None) else None
    if sustainable_pct is not None and historical_cagr is not None:
        contradiction = sustainable_pct < 0 and historical_cagr > 10.0
        divergence = abs(sustainable_pct - historical_cagr) > DIVERGENCE_TRIGGER_PP
        if contradiction or divergence:
            flags.append("SUSTAINABLE_DIVERGES")

    route = "growth" if flags else "standard"
    return route, flags, sustainable_pct


def growth_lens_realistic(rev_growth_recent_pct: float, terminal_growth: float, years: int) -> float:
    """แทน sustainable_growth ด้วย 'growth จริงล่าสุดที่ fade ลงหา terminal' เมื่อ guard ไม่ไว้ใจ
    sustainable_growth — cap ปีแรกที่ CAP_INITIAL_GROWTH (ไม่เชื่อว่ายั่งยืนเกินนี้) แล้ว fade
    เชิงเส้นลงหา terminal ตลอด horizon คืนค่าเป็น CAGR-equivalent ของ path นั้น (%/ปี) เทียบกับ
    implied_growth ได้ตรงๆ — ไม่ 'โลกสวย' เชื่อว่า 40%+ จะคงอยู่ แต่ก็ไม่ติดลบมั่วเหมือน sustainable."""
    g0 = min(rev_growth_recent_pct / 100.0, CAP_INITIAL_GROWTH)
    factor = 1.0
    for t in range(years):
        g_t = g0 + (terminal_growth - g0) * (t / (years - 1)) if years > 1 else g0
        factor *= (1 + g_t)
    return round((factor ** (1 / years) - 1) * 100, 2)


def _rev_growth_recent(revenue_series: list[tuple[str, float]] | None) -> float | None:
    """% การเติบโตปีล่าสุด 'ปีเดียว' (ไม่ใช่ CAGR หลายปี) จาก revenue_series — sort ตาม period
    เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา). สำคัญ: StockFundamentals.revenue_series (จาก
    fundamentals.py) เรียงใหม่->เก่า แต่ health.py::_fy_series() (ที่ประกอบ duck object ตอน
    วิเคราะห์จริงผ่าน compute_health()) เรียงเก่า->ใหม่ — ถ้าไม่ sort เองตรงนี้จะหยิบผิดปี
    (เจอ bug จริง: DUOL ได้ realistic_growth ติดลบทั้งที่โต 41%/ปี เพราะหยิบ FY2022→FY2023
    แทนที่จะเป็น FY2024→FY2025)."""
    if not revenue_series or len(revenue_series) < 2:
        return None
    ordered = sorted(revenue_series, key=lambda p: p[0])   # เก่า -> ใหม่ (period string เรียงตรงตามเวลา)
    newest, prev = ordered[-1][1], ordered[-2][1]
    if prev <= 0:
        return None
    return round((newest / prev - 1) * 100, 2)


def _fcf_base_3yr(fcf_series: list[tuple[str, float]], fallback_fcf: float | None) -> float | None:
    """ค่าเฉลี่ย FCF 3 ปีล่าสุด — sort ตาม period เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา) กันปีที่
    ผิดปกติปีเดียวมาบิดผลทั้งโมเดล. ไม่มี series เลย (ข้อมูลขาด) -> fallback ไป TTM free_cash_flow
    ตัวเดียว (ดีกว่าคำนวณไม่ได้เลย).
    audit fix (2026-07, bug เดียวกับ _rev_growth_recent): เดิม assume fcf_series เรียงใหม่->เก่า
    เสมอ (ตามที่ fundamentals.py คืนมา) แล้วหยิบ [:3] ตรงๆ — แต่ health.py::_build_duck_fundamentals
    (ใช้ตอนคำนวณ valuation component ของ health score ผ่าน compute_health()) ประกอบ fcf_series
    ด้วย _fy_series() ซึ่งเรียงเก่า->ใหม่ (ตรงข้าม) ทำให้หยิบ 3 ปีเก่าสุดแทนที่จะเป็น 3 ปีล่าสุด —
    เจอบั๊กจริงกับ DUOL: fcf_base จากพาธ health.py ต่ำกว่าพาธจริง (loop.py) ถึง 71%
    (149M vs 255M) ทำให้ implied_growth ที่ใช้ตัดสิน valuation component ของ health score เพี้ยน
    (ฐานเล็กกว่าจริง -> ต้องการ growth สูงกว่าจริงถึงจะ justify EV เดียวกัน -> gap ดูแพงเกินจริง)."""
    if not fcf_series:
        return fallback_fcf
    ordered = sorted(fcf_series, key=lambda p: p[0])   # เก่า -> ใหม่ เสมอ ไม่พึ่ง order ที่ caller ส่งมา
    recent = ordered[-3:]
    return sum(v for _, v in recent) / len(recent)


def _fcf_growth_multiyear(fcf_series: list[tuple[str, float]] | None) -> float | None:
    """CAGR ของ FCF ตลอดช่วงที่มีข้อมูล (ล่าสุด vs เก่าสุด) — sort เองเสมอเหมือน _rev_growth_recent.
    None ถ้าข้อมูลไม่พอ หรือปลายทางฝั่งใดฝั่งหนึ่งไม่เป็นบวก (FCF ติดลบ/ศูนย์ช่วงต้น พบได้ทั่วไปกับ
    บริษัทโตเร็วที่ยัง burn cash อยู่ตอนเริ่ม — CAGR ไม่มีความหมายทางคณิตศาสตร์ ต้อง fallback ไป
    revenue growth แทน).

    audit fix 19.4 (2026-07, valuation unit mismatch): growth lens เดิมเทียบ implied_growth
    (FCF growth ที่ตลาด price ไว้ — มาจาก intrinsic_value ที่ compound fcf_base) กับ realistic_growth
    ที่ anchor จาก REVENUE growth (rev_growth_recent/historical_cagr) — apples-to-oranges เวลา
    margin กำลังขยายตัว (บริษัท asset-light ที่กำลัง scale, operating leverage สูง) FCF จะโตเร็วกว่า
    revenue เป็นปกติ (เช่น DUOL จริง: revenue CAGR 41.08%/ปี แต่ FCF CAGR ช่วงเดียวกัน 102.3%/ปี
    — margin ขยายจาก -17.64% เป็น 13.07% operating margin) ใช้ revenue growth มาเป็น proxy ของ
    FCF growth เลยประเมิน 'ความเร็วที่ยั่งยืนได้จริง' ต่ำกว่าความเป็นจริงไปมาก. ตอนนี้ใช้ FCF CAGR
    เป็น anchor หลักเมื่อคำนวณได้ (unit เดียวกับ implied_growth ตรงๆ) fallback ไป revenue growth
    เฉพาะตอน FCF history สั้นเกินไป/สลับเครื่องหมาย (CAGR ไร้ความหมาย) เท่านั้น."""
    if not fcf_series or len(fcf_series) < 2:
        return None
    ordered = sorted(fcf_series, key=lambda p: p[0])
    oldest, newest = ordered[0][1], ordered[-1][1]
    years = len(ordered) - 1
    if oldest <= 0 or newest <= 0:
        return None
    return round(((newest / oldest) ** (1 / years) - 1) * 100, 2)


# gap band ของ valuation /3 — ดึงออกมาเป็น constant (เดิม hardcode 0/5/10 ใน _gap_to_score)
# เพื่อให้ sensitivity analysis sweep ได้ และมองเห็นว่าเป็น 'prior ที่ปรับได้' ไม่ใช่เลขศักดิ์สิทธิ์
GAP_PP_FULL = 0.0    # gap < นี้ (implied < realistic = ตลาดคาดต่ำกว่าที่ทำได้จริง) -> 3 เต็ม
GAP_PP_GOOD = 5.0    # gap < นี้ -> 2
GAP_PP_FAIR = 10.0   # gap < นี้ -> 1, ไม่งั้น 0 (แพงเกินกว่าจะ justify ด้วย growth ที่ทำได้จริง)


def _gap_to_score(gap_pp: float) -> int:
    """gap = implied − realistic (จุดร้อยละ) -> คะแนน /3 แบบ step function (ตามสเปก)."""
    if gap_pp < GAP_PP_FULL:
        return 3
    if gap_pp < GAP_PP_GOOD:
        return 2
    if gap_pp < GAP_PP_FAIR:
        return 1
    return 0


@dataclass
class ReverseDcfResult:
    implied_growth: float | None      # % ต่อปีที่ตลาด 'price ไว้' — None ถ้าคำนวณไม่ได้/นอกขอบเขต
    realistic_growth: float | None    # % ต่อปี — anchor ที่ใช้เทียบ gap จริง (มาจาก lens ไหนดู field lens)
    historical_cagr: float | None     # % ต่อปี — raw revenue CAGR (อ้างอิง/cross-check เท่านั้น)
    gap: float | None                 # implied − realistic (pp)
    score: int | None                 # 0-3 (step function จาก gap, ปรับด้วย Rule of 40 ถ้า lens='growth')
    lens: str                         # "standard" | "growth" | "NA" — ใช้แยกกลุ่มตอน backtest ห้ามปนกัน
    flags: list[str]                  # เหตุผลที่ route (FCF_NONPOSITIVE/NOPAT_UNSTABLE/NEGATIVE_REINVESTMENT/SUSTAINABLE_DIVERGES)
    rule_of_40: float | None          # rev_growth_recent% + fcf_margin% (เฉพาะ lens='growth')
    wacc: float                       # % CAPM ที่ใช้จริง (หลัง clamp β)
    beta_used: float                  # β หลัง clamp [BETA_FLOOR, BETA_CAP]
    terminal_growth: float            # %
    years: int
    ev: float | None                  # Market Cap + Net Debt ที่ใช้เป็นเป้าหมายแก้สมการ
    fcf_base: float | None            # ค่าเฉลี่ย FCF 3 ปีที่ใช้เป็นฐานโมเดล
    note: str | None = None           # เหตุผลเวลาคำนวณไม่ได้ (fcf ติดลบ/นอกขอบเขต/ข้อมูลขาด)

    def to_dict(self) -> dict:
        return {
            "implied_growth": self.implied_growth,
            "realistic_growth": self.realistic_growth,
            "historical_cagr": self.historical_cagr,
            "gap": self.gap,
            "score": self.score,
            "lens": self.lens,
            "flags": self.flags,
            "rule_of_40": self.rule_of_40,
            "wacc": self.wacc,
            "beta_used": self.beta_used,
            "terminal_growth": self.terminal_growth,
            "years": self.years,
            "ev": self.ev,
            "fcf_base": self.fcf_base,
            "note": self.note,
        }


def reverse_dcf(
    fundamentals,
    risk_free_pct: float = FALLBACK_RISK_FREE_PCT,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> dict | None:
    """รับ StockFundamentals (หรือ duck-object แบบเดียวกัน — ต้องมี free_cash_flow, market_cap,
    revenue_cagr, revenue, fcf_series, revenue_series, net_debt, beta, capex,
    depreciation_amortization, nwc_change, nopat, roic, fcf_margin) -> dict (ผ่าน
    ReverseDcfResult.to_dict()). คืน None ถ้าข้อมูลพื้นฐาน (market_cap) ไม่มีเลย — คำนวณไม่ได้
    ตั้งแต่ต้น. risk_free_pct ควรมาจาก src.providers.stock.market.get_risk_free_rate_pct()."""
    market_cap = fundamentals.market_cap
    if market_cap is None or market_cap <= 0:
        return None

    fcf_base = _fcf_base_3yr(getattr(fundamentals, "fcf_series", None), fundamentals.free_cash_flow)

    net_debt = getattr(fundamentals, "net_debt", None) or 0.0
    ev = market_cap + net_debt

    beta = getattr(fundamentals, "beta", None)
    beta_used = 1.0 if beta is None else max(BETA_FLOOR, min(BETA_CAP, beta))
    wacc = capm_wacc(beta, risk_free_pct)

    historical_cagr = fundamentals.revenue_cagr
    nopat = getattr(fundamentals, "nopat", None)
    roic = getattr(fundamentals, "roic", None)
    capex = getattr(fundamentals, "capex", None)
    da = getattr(fundamentals, "depreciation_amortization", None)
    nwc_change = getattr(fundamentals, "nwc_change", None)
    revenue = getattr(fundamentals, "revenue", None)

    route, flags, sustainable = valuation_guard(
        fcf_base, nopat, revenue, capex, da, nwc_change, roic, historical_cagr
    )

    base_result = dict(
        historical_cagr=historical_cagr, wacc=round(wacc * 100, 2), beta_used=round(beta_used, 2),
        terminal_growth=round(terminal_growth * 100, 2), years=years,
        ev=round(ev, 2), fcf_base=round(fcf_base, 2) if fcf_base is not None else None, flags=flags,
    )

    if route == "NA":
        return ReverseDcfResult(
            implied_growth=None, realistic_growth=None, gap=None, score=None,
            lens="NA", rule_of_40=None,
            note="FCF ฐาน (เฉลี่ย 3 ปี) ติดลบ/เป็นศูนย์ — reverse-DCF ใช้ไม่ได้กับบริษัทที่ยัง burn cash อยู่",
            **base_result,
        ).to_dict()

    rev_growth_recent = _rev_growth_recent(getattr(fundamentals, "revenue_series", None))
    fcf_margin = getattr(fundamentals, "fcf_margin", None)
    r40 = (
        round(rev_growth_recent + fcf_margin, 2)
        if rev_growth_recent is not None and fcf_margin is not None else None
    )

    if route == "growth":
        lens = "growth"
        # audit fix 19.4: anchor บน FCF growth ก่อนเสมอถ้าคำนวณได้ (unit เดียวกับ implied_growth
        # ตรงๆ — ดู docstring _fcf_growth_multiyear) revenue growth เป็นแค่ fallback ตอน FCF
        # history สั้นเกินไป/สลับเครื่องหมาย
        fcf_growth = _fcf_growth_multiyear(getattr(fundamentals, "fcf_series", None))
        anchor_growth = fcf_growth if fcf_growth is not None else (
            rev_growth_recent if rev_growth_recent is not None else historical_cagr)
        realistic_growth = (
            growth_lens_realistic(anchor_growth, terminal_growth, years)
            if anchor_growth is not None else historical_cagr
        )
    else:
        lens = "standard"
        realistic_growth = (
            round(max(-100.0, min(SUSTAINABLE_GROWTH_CAP * 100, sustainable)), 2)
            if sustainable is not None else historical_cagr
        )

    implied = implied_growth_rate(ev, fcf_base, wacc, terminal_growth, years)
    note = None
    if implied is None:
        note = (
            f"ราคาปัจจุบันอยู่นอกช่วงที่โมเดลนี้ตีความได้ ({_GROWTH_LO*100:.0f}% ถึง "
            f"{_GROWTH_HI*100:.0f}% ต่อปี) — อาจกำลัง price ปัจจัยอื่นที่ไม่ใช่ FCF growth ธรรมดา"
        )
    gap = round(implied - realistic_growth, 2) if implied is not None and realistic_growth is not None else None
    score = _gap_to_score(gap) if gap is not None else None

    # Rule of 40: growth lens เท่านั้น — โตไม่จริง+เผาเงิน ห้ามตัดสินว่า "ถูก" (score เพดานที่ 1)
    if lens == "growth" and score is not None and r40 is not None and r40 < RULE40_WEAK:
        score = min(score, 1)

    return ReverseDcfResult(
        implied_growth=implied, realistic_growth=realistic_growth, gap=gap, score=score,
        lens=lens, rule_of_40=r40, note=note, **base_result,
    ).to_dict()


if __name__ == "__main__":
    # เครื่องมือ debug: python -m src.agent.valuation AAPL
    import sys
    from src.providers.stock.fundamentals import StockFundamentalsProvider
    from src.providers.stock.market import get_risk_free_rate_pct

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    f = StockFundamentalsProvider().get_fundamentals(ticker)
    rf = get_risk_free_rate_pct()
    result = reverse_dcf(f, risk_free_pct=rf)
    print(f"=== {ticker} reverse-DCF (Rf={rf:.2f}%) ===")
    print(f"Market Cap = {f.market_cap:,.0f}" if f.market_cap else "Market Cap = N/A")
    print(f"Beta       = {f.beta}")
    for k, v in (result or {}).items():
        print(f"  {k:18} = {v}")