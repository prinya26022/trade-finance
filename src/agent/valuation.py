"""Reverse-DCF (Phase 18, per scoring_spec.md): แทนที่จะพยากรณ์ growth แล้วคำนวณราคา
(DCF ปกติ, พยากรณ์ผิดง่าย), เราแก้สมการย้อนกลับ — เอา 'ราคาตลาดปัจจุบัน' ตั้งเป็นโจทย์ แล้วหาว่า
'ตลาดกำลัง price การเติบโตของ FCF ไว้ที่กี่ % ต่อปี' (implied growth) ถึงจะได้ราคานี้พอดี
ตัดปัญหาพยากรณ์อนาคตออกไปเลย — เหลือแค่เทียบว่า 'สิ่งที่ตลาดคาดหวัง' กับ 'การเติบโตที่บริษัท
ทำได้จริงอย่างยั่งยืน' (realistic_growth) ห่างกันแค่ไหน ยิ่ง gap เยอะ ยิ่งเสี่ยงถ้าตลาดคาดผิด

ค่าคงที่ต้องล็อกเหมือนกันทุกหุ้น (ตามกฎเหล็กของสเปก — ห้ามให้อะไรลอยตามใจนอกจาก FCF/β/ตัวที่
solve ไม่งั้น cheap พลิกเป็น expensive ได้ง่ายๆ และเทียบข้ามหุ้นไม่ได้เลย):
- Forecast horizon 10 ปี, Terminal growth 2.5%, ERP มาตรฐาน (ไม่ลอยตามหุ้น)
- WACC = CAPM (Rf + β×ERP) — Rf ล็อกเป็นค่าเดียว ณ วันรัน (ตลาดรวม ไม่ใช่ต่อหุ้น), β ตั้งเพดาน
  [0.7, 1.6] กัน beta เพี้ยนของหุ้นเล็กมาบิด WACC
- FCF base = ค่าเฉลี่ย FCF 3 ปีย้อนหลัง (กันปีที่ผิดปกติปีเดียวมาบิดผลทั้งโมเดล)
- EV target = Market Cap + Net Debt (ไม่ใช่ market cap ตรงๆ แบบ Phase 15 เดิม — bridge หนี้เข้าไป
  ด้วยถึงจะเทียบข้ามหุ้นที่มี leverage ต่างกันได้ยุติธรรม)
- realistic_growth = sustainable_growth (reinvestment_rate × ROIC) เป็นหลัก ไม่ใช่ raw CAGR
  (CAGR อดีตเป็นตัวแทนอนาคตที่อันตราย — mean reversion, หุ้นวัฏจักร, บริษัทโตเต็มวัย) cap ไว้ที่
  20%/ปี และ cross-check กับ CAGR — ถ้าห่างกันมหาศาล flag ว่า 'ประเมินยาก' (ไม่ใช่เปลี่ยนค่า)
"""
from dataclasses import dataclass

DEFAULT_TERMINAL_GROWTH = 0.025  # โตตลอดไปเท่า GDP/เงินเฟ้อระยะยาวโดยประมาณ — ห้ามสูงกว่านี้
DEFAULT_YEARS = 10
DEFAULT_ERP = 0.0525              # equity risk premium มาตรฐาน (จุดกึ่งกลาง 5-5.5%) — ล็อกค่าเดียว
FALLBACK_RISK_FREE_PCT = 4.0      # ใช้ตอนดึง ^TNX ไม่ได้ (ดู src/providers/stock/market.py)

BETA_FLOOR = 0.7   # กัน beta ของหุ้นเล็ก/ข้อมูลเพี้ยนมาบิด WACC จนเทียบข้ามหุ้นไม่ได้
BETA_CAP = 1.6

SUSTAINABLE_GROWTH_CAP = 0.20     # ไม่มีบริษัทไหนโตสองหลักสูงได้ตลอด 10 ปี
DIVERGENCE_FLAG_PP = 10.0         # sustainable vs historical CAGR ต่างกันเกินนี้ (จุดร้อยละ) -> flag

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


def sustainable_growth_rate(
    capex: float | None, da: float | None, nwc_change: float | None,
    nopat: float | None, roic_pct: float | None,
) -> float | None:
    """sustainable_growth = reinvestment_rate × ROIC (excess-returns growth model) — ใช้แทน raw
    CAGR เป็น 'realistic_growth' หลัก เพราะ CAGR อดีตเป็นตัวแทนอนาคตที่อันตราย (mean reversion,
    หุ้นวัฏจักร, บริษัทโตเต็มวัย). reinvestment_rate = (Capex − D&A + ΔNWC) / NOPAT.
    capex/nwc_change เป็นเลขลบตามธรรมเนียม cash-flow statement ของ yfinance (เงินสดไหลออก),
    da เป็นเลขบวก (ธรรมเนียม add-back) — พลิกเครื่องหมาย capex/nwc_change ก่อนคำนวณ (ต้องการ
    'เงินลงทุนจริง'/'NWC ที่เพิ่มขึ้นจริง' เป็นบวก ไม่ใช่ทิศทางกระแสเงินสด)."""
    if capex is None or da is None or nwc_change is None or not nopat or roic_pct is None:
        return None
    real_capex = -capex               # ลบ (ไหลออก) -> บวก (เงินลงทุนจริง)
    real_nwc_increase = -nwc_change   # เช่นกัน: ลบ = NWC เพิ่ม (ใช้เงินสด) -> บวก
    reinvestment_rate = (real_capex - da + real_nwc_increase) / nopat
    return reinvestment_rate * (roic_pct / 100.0)


def _fcf_base_3yr(fcf_series: list[tuple[str, float]], fallback_fcf: float | None) -> float | None:
    """ค่าเฉลี่ย FCF 3 ปีล่าสุด (fcf_series เรียงใหม่->เก่า ตามที่ fundamentals.py คืนมา — คอลัมน์
    ล่าสุดอยู่ซ้ายสุดในงบต้นทาง; ตรวจสอบสดแล้ว) กันปีที่ผิดปกติปีเดียวมาบิดผลทั้งโมเดล. ไม่มี series
    เลย (ข้อมูลขาด) -> fallback ไป TTM free_cash_flow ตัวเดียว (ดีกว่าคำนวณไม่ได้เลย)."""
    if not fcf_series:
        return fallback_fcf
    recent = fcf_series[:3]
    return sum(v for _, v in recent) / len(recent)


def _gap_to_score(gap_pp: float) -> int:
    """gap = implied − realistic (จุดร้อยละ) -> คะแนน /3 แบบ step function (ตามสเปก, ไม่ใช่
    สูตร linear ต่อเนื่องแบบ Phase 15/17 เดิม — เทียบข้ามหุ้นได้ตรงไปตรงมากว่า)."""
    if gap_pp < 0:
        return 3
    if gap_pp < 5:
        return 2
    if gap_pp < 10:
        return 1
    return 0


@dataclass
class ReverseDcfResult:
    implied_growth: float | None      # % ต่อปีที่ตลาด 'price ไว้' — None ถ้าคำนวณไม่ได้/นอกขอบเขต
    realistic_growth: float | None    # % ต่อปี — sustainable_growth (capped) เป็นหลัก, ใช้เทียบ gap
    historical_cagr: float | None     # % ต่อปี — raw revenue CAGR (อ้างอิง/cross-check เท่านั้น)
    gap: float | None                 # implied − realistic (pp)
    score: int | None                 # 0-3 (step function จาก gap) — None ถ้า implied/realistic ขาด
    wacc: float                       # % CAPM ที่ใช้จริง (หลัง clamp β)
    beta_used: float                  # β หลัง clamp [BETA_FLOOR, BETA_CAP]
    terminal_growth: float            # %
    years: int
    ev: float | None                  # Market Cap + Net Debt ที่ใช้เป็นเป้าหมายแก้สมการ
    fcf_base: float | None            # ค่าเฉลี่ย FCF 3 ปีที่ใช้เป็นฐานโมเดล
    divergence_flag: str | None = None  # เตือนถ้า sustainable vs CAGR ต่างกันมหาศาล — 'ประเมินยาก'
    note: str | None = None           # เหตุผลเวลาคำนวณไม่ได้ (fcf ติดลบ/นอกขอบเขต/ข้อมูลขาด)

    def to_dict(self) -> dict:
        return {
            "implied_growth": self.implied_growth,
            "realistic_growth": self.realistic_growth,
            "historical_cagr": self.historical_cagr,
            "gap": self.gap,
            "score": self.score,
            "wacc": self.wacc,
            "beta_used": self.beta_used,
            "terminal_growth": self.terminal_growth,
            "years": self.years,
            "ev": self.ev,
            "fcf_base": self.fcf_base,
            "divergence_flag": self.divergence_flag,
            "note": self.note,
        }


def reverse_dcf(
    fundamentals,
    risk_free_pct: float = FALLBACK_RISK_FREE_PCT,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> dict | None:
    """รับ StockFundamentals (หรือ duck-object แบบเดียวกัน — ต้องมี free_cash_flow, market_cap,
    revenue_cagr, fcf_series, net_debt, beta, capex, depreciation_amortization, nwc_change,
    nopat, roic) -> dict (ผ่าน ReverseDcfResult.to_dict()). คืน None ถ้าข้อมูลพื้นฐาน (fcf/market
    cap) ไม่มีเลย — คำนวณไม่ได้ตั้งแต่ต้น. risk_free_pct ควรมาจาก
    src.providers.stock.market.get_risk_free_rate_pct() (ล็อกค่าเดียว ณ วันรัน ทุก ticker)."""
    market_cap = fundamentals.market_cap
    if market_cap is None or market_cap <= 0:
        return None

    fcf_base = _fcf_base_3yr(getattr(fundamentals, "fcf_series", None), fundamentals.free_cash_flow)
    if fcf_base is None:
        return None

    net_debt = getattr(fundamentals, "net_debt", None) or 0.0
    ev = market_cap + net_debt

    beta = getattr(fundamentals, "beta", None)
    beta_used = 1.0 if beta is None else max(BETA_FLOOR, min(BETA_CAP, beta))
    wacc = capm_wacc(beta, risk_free_pct)

    historical_cagr = fundamentals.revenue_cagr
    sg = sustainable_growth_rate(
        getattr(fundamentals, "capex", None), getattr(fundamentals, "depreciation_amortization", None),
        getattr(fundamentals, "nwc_change", None), getattr(fundamentals, "nopat", None),
        getattr(fundamentals, "roic", None),
    )
    if sg is not None:
        realistic_growth = round(max(-100.0, min(SUSTAINABLE_GROWTH_CAP, sg)) * 100, 2)
    else:
        realistic_growth = historical_cagr  # ไม่มีข้อมูลพอคิด sustainable -> fallback ไป raw CAGR

    divergence_flag = None
    if realistic_growth is not None and historical_cagr is not None and sg is not None:
        if abs(realistic_growth - historical_cagr) > DIVERGENCE_FLAG_PP:
            divergence_flag = (
                f"sustainable growth ({realistic_growth:.1f}%/ปี) ต่างจาก historical CAGR "
                f"({historical_cagr:.1f}%/ปี) มาก — ประเมิน realistic growth ยาก ลดความเชื่อมั่น"
            )

    base_result = dict(
        historical_cagr=historical_cagr, realistic_growth=realistic_growth, wacc=round(wacc * 100, 2),
        beta_used=round(beta_used, 2), terminal_growth=round(terminal_growth * 100, 2), years=years,
        ev=round(ev, 2), fcf_base=round(fcf_base, 2),
    )

    if fcf_base <= 0:
        return ReverseDcfResult(
            implied_growth=None, gap=None, score=None,
            note="FCF ฐาน (เฉลี่ย 3 ปี) ติดลบ/เป็นศูนย์ — reverse-DCF ใช้ไม่ได้กับบริษัทที่ยัง burn cash อยู่",
            divergence_flag=divergence_flag, **base_result,
        ).to_dict()

    implied = implied_growth_rate(ev, fcf_base, wacc, terminal_growth, years)
    note = None
    if implied is None:
        note = (
            f"ราคาปัจจุบันอยู่นอกช่วงที่โมเดลนี้ตีความได้ ({_GROWTH_LO*100:.0f}% ถึง "
            f"{_GROWTH_HI*100:.0f}% ต่อปี) — อาจกำลัง price ปัจจัยอื่นที่ไม่ใช่ FCF growth ธรรมดา"
        )
    gap = round(implied - realistic_growth, 2) if implied is not None and realistic_growth is not None else None
    score = _gap_to_score(gap) if gap is not None else None

    return ReverseDcfResult(
        implied_growth=implied, gap=gap, score=score, note=note, divergence_flag=divergence_flag,
        **base_result,
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