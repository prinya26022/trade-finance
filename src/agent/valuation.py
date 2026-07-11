"""Reverse-DCF: แทนที่จะพยากรณ์ growth แล้วคำนวณราคา (DCF ปกติ, พยากรณ์ผิดง่าย),
เราแก้สมการย้อนกลับ — เอา 'ราคาตลาดปัจจุบัน' ตั้งเป็นโจทย์ แล้วหาว่า 'ตลาดกำลัง price
การเติบโตของ FCF ไว้ที่กี่ % ต่อปี' ถึงจะได้ราคานี้พอดี ตัดปัญหาพยากรณ์อนาคตออกไปเลย —
เหลือแค่เทียบว่า 'สิ่งที่ตลาดคาดหวัง' กับ 'การเติบโตจริงในอดีตของบริษัท' (revenue_cagr ที่
มีอยู่แล้วใน StockFundamentals) ห่างกันแค่ไหน ยิ่ง gap เยอะ ยิ่งเสี่ยงถ้าตลาดคาดผิด

โมเดล: two-stage DCF บน Free Cash Flow to Equity แบบง่าย (ใช้ market cap ตรงๆ เป็น
เป้าหมาย ไม่ bridge net debt) — FCF โต g%/ปี เป็นเวลา `years` ปี จากนั้นโตคงที่ที่
terminal_growth ตลอดไป (Gordon growth) แล้วคิดลดกลับด้วย discount_rate
"""
from dataclasses import dataclass

DEFAULT_DISCOUNT_RATE = 0.09    # อัตราผลตอบแทนที่นักลงทุนเรียกร้อง (equity) — ค่าเริ่มต้นกลางๆ
DEFAULT_TERMINAL_GROWTH = 0.025  # โตตลอดไปเท่า GDP/เงินเฟ้อระยะยาวโดยประมาณ
DEFAULT_YEARS = 10

# ขอบเขตการเติบโตที่โมเดลนี้ยอมแก้สมการหา (-30% ถึง +60% ต่อปี) — นอก
# ช่วงนี้ถือว่า 'ราคาสุดโต่งเกินกว่าจะตีความเป็นตัวเลข growth ที่มีความหมาย'
_GROWTH_LO = -0.30
_GROWTH_HI = 0.60
_TOLERANCE = 1e-6
_MAX_ITER = 200


def intrinsic_equity_value(
    fcf: float, growth: float, discount_rate: float, terminal_growth: float, years: int
) -> float:
    """PV ของ FCF ที่โต `growth`/ปี เป็นเวลา `years` ปี + terminal value (Gordon growth)
    ที่ปีสุดท้าย คิดลดกลับมาปัจจุบัน. Monotonic เพิ่มขึ้นตาม growth (growth สูง = value สูง)
    — สมบัตินี้คือสิ่งที่ทำให้ bisection หา implied growth ด้านล่างใช้ได้."""
    pv = 0.0
    cash_flow = fcf
    for t in range(1, years + 1):
        cash_flow = cash_flow * (1 + growth)
        pv += cash_flow / (1 + discount_rate) ** t
    terminal_fcf = cash_flow * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv += terminal_value / (1 + discount_rate) ** years
    return pv


def implied_growth_rate(
    market_cap: float,
    fcf: float,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> float | None:
    """หา growth g ที่ intrinsic_equity_value(fcf, g, ...) == market_cap พอดี (bisection).
    คืน None ถ้าแก้ไม่ได้จริงๆ: โมเดลไม่ valid (discount_rate <= terminal_growth ทำให้
    terminal value คำนวณไม่ได้/ติดลบ) หรือราคาปัจจุบันอยู่นอกช่วง [_GROWTH_LO, _GROWTH_HI]
    ที่โมเดลนี้ตีความได้ (เช่น penny stock ที่ market cap ต่ำกว่ากรณี growth -30% เสียอีก
    — แปลว่าตลาด price ปัจจัยอื่นที่ไม่ใช่ FCF growth ธรรมดา เช่น risk of bankruptcy)."""
    if discount_rate <= terminal_growth:
        return None

    lo, hi = _GROWTH_LO, _GROWTH_HI
    value_lo = intrinsic_equity_value(fcf, lo, discount_rate, terminal_growth, years)
    value_hi = intrinsic_equity_value(fcf, hi, discount_rate, terminal_growth, years)
    if market_cap < value_lo or market_cap > value_hi:
        return None  # นอกขอบเขตที่โมเดลตีความได้

    for _ in range(_MAX_ITER):
        mid = (lo + hi) / 2
        value_mid = intrinsic_equity_value(fcf, mid, discount_rate, terminal_growth, years)
        if abs(value_mid - market_cap) < max(1.0, market_cap * _TOLERANCE):
            return round(mid * 100, 2)
        if value_mid < market_cap:
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) * 100, 2)


@dataclass
class ReverseDcfResult:
    implied_growth: float | None   # % ต่อปีที่ตลาด 'price ไว้' — None ถ้าคำนวณไม่ได้/นอกขอบเขต
    historical_cagr: float | None  # % ต่อปีที่บริษัทโตจริงในอดีต (จาก StockFundamentals เดิม)
    gap: float | None              # implied - historical: บวก = ตลาดคาดหวังมากกว่าที่เคยทำได้จริง
    discount_rate: float
    terminal_growth: float
    years: int
    note: str | None = None        # เหตุผลเวลาคำนวณไม่ได้ (fcf ติดลบ/นอกขอบเขต)

    def to_dict(self) -> dict:
        return {
            "implied_growth": self.implied_growth,
            "historical_cagr": self.historical_cagr,
            "gap": self.gap,
            "discount_rate": self.discount_rate,
            "terminal_growth": self.terminal_growth,
            "years": self.years,
            "note": self.note,
        }


def reverse_dcf(
    fundamentals,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> dict | None:
    """รับ StockFundamentals -> dict (ผ่าน ReverseDcfResult.to_dict()) พร้อม persist/ส่งให้ UI.
    คืน None ถ้าข้อมูลพื้นฐาน (fcf, market_cap) ไม่มีเลย — คำนวณไม่ได้ตั้งแต่ต้น."""
    fcf = fundamentals.free_cash_flow
    market_cap = fundamentals.market_cap
    if fcf is None or market_cap is None or market_cap <= 0:
        return None

    historical = fundamentals.revenue_cagr

    if fcf <= 0:
        return ReverseDcfResult(
            implied_growth=None,
            historical_cagr=historical,
            gap=None,
            discount_rate=round(discount_rate * 100, 2),
            terminal_growth=round(terminal_growth * 100, 2),
            years=years,
            note="FCF ติดลบ/เป็นศูนย์ — reverse-DCF ใช้ไม่ได้กับบริษัทที่ยัง burn cash อยู่",
        ).to_dict()

    implied = implied_growth_rate(market_cap, fcf, discount_rate, terminal_growth, years)
    note = None
    if implied is None:
        note = (
            f"ราคาปัจจุบันอยู่นอกช่วงที่โมเดลนี้ตีความได้ ({_GROWTH_LO*100:.0f}% ถึง "
            f"{_GROWTH_HI*100:.0f}% ต่อปี) — อาจกำลัง price ปัจจัยอื่นที่ไม่ใช่ FCF growth ธรรมดา"
        )
    gap = round(implied - historical, 2) if implied is not None and historical is not None else None

    return ReverseDcfResult(
        implied_growth=implied,
        historical_cagr=historical,
        gap=gap,
        discount_rate=round(discount_rate * 100, 2),
        terminal_growth=round(terminal_growth * 100, 2),
        years=years,
        note=note,
    ).to_dict()


if __name__ == "__main__":
    # เครื่องมือ debug: python -m src.agent.valuation AAPL
    import sys
    from src.providers.stock.fundamentals import StockFundamentalsProvider

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    f = StockFundamentalsProvider().get_fundamentals(ticker)
    result = reverse_dcf(f)
    print(f"=== {ticker} reverse-DCF ===")
    print(f"FCF (TTM)     = {f.free_cash_flow:,.0f}" if f.free_cash_flow else "FCF (TTM)     = N/A")
    print(f"Market Cap    = {f.market_cap:,.0f}" if f.market_cap else "Market Cap    = N/A")
    print(result)