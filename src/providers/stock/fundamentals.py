import yfinance as yf
import pandas as pd
from dataclasses import dataclass, field
from src.domain.interfaces import Fundamentals, FundamentalsProvider, Fact


# ─────────────────────────────────────────────────────────────────────────────
# DATA SHAPE
# เก็บทั้ง "ค่าล่าสุด/TTM" (สเกลาร์) และ "อนุกรมหลายปี" (series) แยกกัน
# series = list ของ (ป้ายงวด, ค่า) เช่น [("FY2025", 0.32), ("FY2024", 0.31), ...]
# ให้ LLM เห็นตัวเลขรายปีเอง แล้วตัดสิน trend เอง (grounded กว่าให้เราตีป้ายให้)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StockFundamentals(Fundamentals):
    period: str = "N/A"

    # --- ความสามารถทำกำไร / ผลตอบแทนต่อทุน ---
    revenue: float | None = None
    free_cash_flow: float | None = None
    fcf_margin: float | None = None          # FCF / Revenue (%)
    roic: float | None = None                # NOPAT / invested capital (%)
    roe: float | None = None                 # Net Income / equity (%)
    revenue_cagr: float | None = None        # CAGR ตลอดช่วงที่มีข้อมูล (%)

    # --- งบดุล / ความปลอดภัย ---
    net_debt_to_ebitda: float | None = None  # เกิน 3 เท่าเริ่มเสี่ยง
    interest_coverage: float | None = None   # EBIT / ดอกเบี้ย
    current_ratio: float | None = None

    # --- Phase 18: ดิบสำหรับ Piotroski data-gate + reverse-DCF (CAPM/sustainable growth) ---
    net_income: float | None = None          # scoring_spec.md เกณฑ์ #3 (accruals: CFO > Net Income)
    cfo: float | None = None                 # Operating Cash Flow — คู่กับ net_income เช็คคุณภาพกำไร
    net_debt: float | None = None            # ดอลลาร์ดิบ (ไม่ใช่ ratio) — ใช้ผูก EV = Market Cap + Net Debt
    capex: float | None = None               # เข้า reinvestment_rate = (Capex − D&A + ΔNWC) / NOPAT
    depreciation_amortization: float | None = None
    nwc_change: float | None = None          # Change In Working Capital
    nopat: float | None = None               # จาก ROIC calc — เป็นตัวหารของ reinvestment_rate
    invested_capital: float | None = None    # จาก ROIC calc
    beta: float | None = None                # β หุ้น — เข้า CAPM WACC (Rf + β×ERP)

    # --- Red flags (ด่าน 8) ---
    goodwill: float | None = None            # ถ้าเยอะระวัง write-off
    goodwill_pct_assets: float | None = None # goodwill เป็น % ของสินทรัพย์รวม

    # --- Valuation (ณ ปัจจุบัน, จาก info) ---
    pe: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    peg: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    fcf_yield: float | None = None           # FCF / market cap (%)
    market_cap: float | None = None
    avg_volume: float | None = None          # สภาพคล่อง (ด่าน 0)

    # --- อนุกรมหลายปี (ดู trend) ---
    gross_margin_series: list[tuple[str, float]] = field(default_factory=list)
    operating_margin_series: list[tuple[str, float]] = field(default_factory=list)
    net_margin_series: list[tuple[str, float]] = field(default_factory=list)
    share_count_series: list[tuple[str, float]] = field(default_factory=list)
    fcf_series: list[tuple[str, float]] = field(default_factory=list)          # FCF trend หลายปี
    dso_series: list[tuple[str, float]] = field(default_factory=list)          # วันเก็บหนี้ (พุ่ง = red flag)
    inventory_pct_series: list[tuple[str, float]] = field(default_factory=list)  # inventory เทียบยอดขาย (บวม = red flag)

    # --- Phase 18: อนุกรมหลายปีเพิ่ม — scoring_spec.md เกณฑ์ #2/#5/#6 ต้องเช็ค trend YoY ไม่ใช่แค่ level ---
    roe_series: list[tuple[str, float]] = field(default_factory=list)
    net_debt_to_ebitda_series: list[tuple[str, float]] = field(default_factory=list)
    current_ratio_series: list[tuple[str, float]] = field(default_factory=list)

    def to_facts(self) -> list[Fact]:
        facts: list[Fact] = []

        # (1) สเกลาร์: (label, value, unit, period) — ข้ามตัวที่เป็น None (ห้ามปลอม 0.0)
        # period ต้องตรงกับ 'ฐานเวลาจริง' ของค่านั้น: Revenue/FCF Margin/FCF Yield คำนวณจาก
        # info['totalRevenue']/info['freeCashflow'] ซึ่งเป็น TTM (ล่าสุด 12 เดือน) ไม่ใช่สิ้นปีงบ
        # (self.period) — ติดป้าย FY ผิดจะทำให้ LLM เห็นค่า TTM (เช่น FCF ติดลบช่วงแย่ล่าสุด)
        # ข้าง ๆ FCF series แบบ FY (เช่น FY2025 บวก) แล้วงงว่าตัวเลขขัดแย้งกันเอง (ลด confidence)
        scalars = [
            ("Revenue", self.revenue, "USD", "TTM"),
            ("FCF Margin", self.fcf_margin, "%", "TTM"),
            ("ROIC", self.roic, "%", self.period),
            ("ROE", self.roe, "%", self.period),
            ("Revenue CAGR", self.revenue_cagr, "%", self.period),
            ("Net Debt / EBITDA", self.net_debt_to_ebitda, "x", self.period),
            ("Interest Coverage", self.interest_coverage, "x", self.period),
            ("Current Ratio", self.current_ratio, "x", self.period),
            ("P/E", self.pe, "x", self.period),
            ("Forward P/E", self.forward_pe, "x", self.period),
            ("EV/EBITDA", self.ev_ebitda, "x", self.period),
            ("PEG", self.peg, "x", self.period),
            ("P/B", self.price_to_book, "x", self.period),
            ("P/S", self.price_to_sales, "x", self.period),
            ("FCF Yield", self.fcf_yield, "%", "TTM"),
            ("Market Cap", self.market_cap, "USD", self.period),
            ("Avg Daily Volume", self.avg_volume, "shares", self.period),
            ("Goodwill", self.goodwill, "USD", self.period),
            ("Goodwill % Assets", self.goodwill_pct_assets, "%", self.period),
            ("Net Income", self.net_income, "USD", self.period),
            ("CFO", self.cfo, "USD", self.period),
            ("Net Debt", self.net_debt, "USD", self.period),
            ("Capex", self.capex, "USD", self.period),
            ("D&A", self.depreciation_amortization, "USD", self.period),
            ("NWC Change", self.nwc_change, "USD", self.period),
            ("NOPAT", self.nopat, "USD", self.period),
            ("Invested Capital", self.invested_capital, "USD", self.period),
            ("Beta", self.beta, "x", self.period),
        ]
        facts += [
            Fact(label, value, unit, period)
            for label, value, unit, period in scalars
            if value is not None
        ]

        # (2) อนุกรม: แตกเป็น 1 Fact ต่อปี (period = ป้ายงวดของปีนั้น)
        series = [
            ("Gross Margin", self.gross_margin_series, "%"),
            ("Operating Margin", self.operating_margin_series, "%"),
            ("Net Margin", self.net_margin_series, "%"),
            ("Diluted Shares", self.share_count_series, "shares"),
            ("Free Cash Flow", self.fcf_series, "USD"),
            ("DSO", self.dso_series, "days"),
            ("Inventory % Revenue", self.inventory_pct_series, "%"),
            ("ROE", self.roe_series, "%"),
            ("Net Debt / EBITDA", self.net_debt_to_ebitda_series, "x"),
            ("Current Ratio", self.current_ratio_series, "x"),
        ]
        for label, points, unit in series:
            for period_label, value in points:
                facts.append(Fact(label, value, unit, period_label))

        return facts


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — ดึงค่าจาก DataFrame ของ yfinance (คอลัมน์ = งวด, ล่าสุดอยู่ซ้ายสุด)
# ─────────────────────────────────────────────────────────────────────────────
def _period_label(col) -> str:
    """คอลัมน์ (Timestamp) -> 'FY2025'."""
    try:
        return f"FY{col.year}"
    except AttributeError:
        return str(col)


def _find_row(row_names, df):
    """คืน 'ชื่อแถวจริง' ตัวแรกที่มีใน df (รองรับชื่อสำรอง), ไม่เจอคืน None."""
    if df is None or df.empty:
        return None
    for name in row_names:
        if name in df.index:
            return name
    return None


def _first(row_names, df):
    """ค่าล่าสุด (คอลัมน์ซ้ายสุด) ของแถวแรกที่เจอ, ไม่มีคืน None. ใช้ pd.notna กัน NaN."""
    row = _find_row(row_names, df)
    if row is None:
        return None
    value = df.loc[row, df.columns[0]]
    return float(value) if pd.notna(value) else None


def _series(row_names, df) -> list[tuple[str, float]]:
    """คืนทั้งอนุกรม [(FYxxxx, ค่า), ...] เรียงล่าสุดก่อน, ข้ามงวดที่เป็น NaN."""
    row = _find_row(row_names, df)
    if row is None:
        return []
    out = []
    for col in df.columns:
        value = df.loc[row, col]
        if pd.notna(value):
            out.append((_period_label(col), float(value)))
    return out


def _ratio_series(numer_names, denom_names, df, pct=True) -> list[tuple[str, float]]:
    """อัตราส่วนรายปี เช่น margin = numerator/denominator ต่อคอลัมน์เดียวกัน."""
    numer_row = _find_row(numer_names, df)
    denom_row = _find_row(denom_names, df)
    if numer_row is None or denom_row is None:
        return []
    out = []
    for col in df.columns:
        n, d = df.loc[numer_row, col], df.loc[denom_row, col]
        if pd.notna(n) and pd.notna(d) and d != 0:
            # cast เป็น native Python float ก่อนคำนวณ (เหมือน _first/_series) — เผื่อไว้ ไม่งั้น
            # ค่าที่ได้เป็น numpy.float64 ซึ่งดู 'เหมือน' float ปกติ (subclass ของ float จริง จึง
            # JSON serialize ผ่านมาตลอดไม่มีปัญหา) แต่พอเอาไปเทียบ <= จะได้ numpy.bool_ ซึ่ง
            # json.dumps() serialize ไม่ได้ (ไม่ใช่ subclass ของ bool) — เจอตอนทำ eval เทียบ tolerance
            ratio = float(n) / float(d)
            out.append((_period_label(col), round(ratio * 100, 2) if pct else round(ratio, 2)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE — เมตริกที่ต้องคำนวณ (ไม่มีตรง ๆ ใน info)
# ─────────────────────────────────────────────────────────────────────────────
def _compute_free_cash_flow(info: dict, cashflow) -> float | None:
    fcf = info.get("freeCashflow")
    if fcf is not None:
        return float(fcf)
    # สำรอง: FCF = OCF + Capex (capex เก็บเป็นเลขติดลบอยู่แล้ว)
    ocf = _first(["Operating Cash Flow", "Total Cash From Operating Activities"], cashflow)
    capex = _first(["Capital Expenditure", "Capital Expenditures"], cashflow)
    if ocf is not None and capex is not None:
        return ocf + capex
    return None


def _compute_roic(financials, balance_sheet) -> tuple[float | None, float | None, float | None]:
    """คืน (ROIC %, NOPAT ดอลลาร์, Invested Capital ดอลลาร์) — expose NOPAT/invested_capital
    แยกเป็น Fact ของตัวเอง (Phase 18) เพราะ reinvestment_rate ของ reverse-DCF ใหม่ต้องใช้
    NOPAT เป็นตัวหาร (reinvestment_rate = (Capex − D&A + ΔNWC) / NOPAT)."""
    operating_income = _first(["Operating Income", "EBIT"], financials)  # EBIT
    pretax_income = _first(["Pretax Income"], financials)
    tax_provision = _first(["Tax Provision"], financials)

    total_debt = _first(["Total Debt"], balance_sheet)
    total_equity = _first(["Stockholders Equity", "Total Stockholder Equity"], balance_sheet)
    cash = _first(
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
        balance_sheet,
    )
    if operating_income is None or total_debt is None or total_equity is None or cash is None:
        return None, None, None

    # อัตราภาษีจริง (guard หาร 0 / None) แล้วได้ NOPAT = กำไรดำเนินงานหลังภาษี
    tax_rate = tax_provision / pretax_income if pretax_income and tax_provision is not None else 0.0
    nopat = operating_income * (1 - tax_rate)
    invested_capital = total_debt + total_equity - cash  # เงินทั้งหมดที่ใส่ในธุรกิจ (หัก cash กองเฉย ๆ)
    if not invested_capital:
        return None, nopat, invested_capital
    return round((nopat / invested_capital) * 100, 2), nopat, invested_capital


def _compute_roe(financials, balance_sheet) -> float | None:
    net_income = _first(["Net Income", "Net Income Common Stockholders"], financials)
    equity = _first(["Stockholders Equity", "Total Stockholder Equity"], balance_sheet)
    if net_income is None or not equity:
        return None
    return round((net_income / equity) * 100, 2)


def _compute_revenue_cagr(financials) -> float | None:
    """CAGR ตลอดช่วงที่มีข้อมูล (ล่าสุด vs เก่าสุด)."""
    rev = _series(["Total Revenue", "Operating Revenue"], financials)
    if len(rev) < 2:
        return None
    newest, oldest = rev[0][1], rev[-1][1]      # rev เรียงล่าสุดก่อน
    years = len(rev) - 1
    if oldest <= 0 or newest <= 0:
        return None
    cagr = (newest / oldest) ** (1 / years) - 1
    return round(cagr * 100, 2)


def _compute_net_debt(balance_sheet) -> float | None:
    """Net Debt ดอลลาร์ดิบ (ไม่ใช่ ratio) — เดิมคำนวณแล้วทิ้งข้างในเลย (Phase 18: แยก expose
    เป็น Fact ของตัวเองด้วย ใช้ผูก EV = Market Cap + Net Debt ใน reverse-DCF ใหม่)."""
    net_debt = _first(["Net Debt"], balance_sheet)
    if net_debt is not None:
        return net_debt
    total_debt = _first(["Total Debt"], balance_sheet)
    cash = _first(["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], balance_sheet)
    if total_debt is None or cash is None:
        return None
    return total_debt - cash


def _compute_net_debt_to_ebitda(balance_sheet, financials, info) -> float | None:
    net_debt = _compute_net_debt(balance_sheet)
    if net_debt is None:
        return None
    ebitda = _first(["EBITDA", "Normalized EBITDA"], financials) or info.get("ebitda")
    if not ebitda:
        return None
    return round(net_debt / ebitda, 2)


def _net_debt_to_ebitda_series(balance_sheet, financials) -> list[tuple[str, float]]:
    """อนุกรมรายปี — net_debt คำนวณจาก 2 แถวในงบดุลปีเดียวกัน (ไม่ใช่แถวเดียว) จึงคำนวณ
    net_debt ต่อปีก่อน แล้วค่อยจับคู่กับ EBITDA ปีเดียวกันจากงบกำไร (คนละ DataFrame)."""
    debt_row = _find_row(["Total Debt"], balance_sheet)
    cash_row = _find_row(
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], balance_sheet
    )
    if debt_row is None or cash_row is None:
        return []
    net_debt_by_year: dict[int, float] = {}
    for col in balance_sheet.columns:
        year = getattr(col, "year", None)
        debt, cash = balance_sheet.loc[debt_row, col], balance_sheet.loc[cash_row, col]
        if year is not None and pd.notna(debt) and pd.notna(cash):
            net_debt_by_year[year] = float(debt) - float(cash)

    ebitda_row = _find_row(["EBITDA", "Normalized EBITDA"], financials)
    if ebitda_row is None:
        return []
    out = []
    for col in financials.columns:
        year = getattr(col, "year", None)
        ebitda = financials.loc[ebitda_row, col]
        net_debt = net_debt_by_year.get(year)
        if year is not None and pd.notna(ebitda) and ebitda and net_debt is not None:
            out.append((f"FY{year}", round(net_debt / float(ebitda), 2)))
    return out


def _latest_common(numer_names, denom_names, df):
    """คู่ (numer, denom) จากคอลัมน์ล่าสุดที่ 'ทั้งคู่' ไม่เป็น NaN (จับคู่ในปีเดียวกัน).
    เผื่อกรณีปีล่าสุดข้อมูลตัวหนึ่งว่าง (เช่น AAPL ไม่รายงาน Interest Expense แล้ว)."""
    numer_row = _find_row(numer_names, df)
    denom_row = _find_row(denom_names, df)
    if numer_row is None or denom_row is None:
        return None
    for col in df.columns:                       # ล่าสุดก่อน
        n, d = df.loc[numer_row, col], df.loc[denom_row, col]
        if pd.notna(n) and pd.notna(d):
            return float(n), float(d)
    return None


def _compute_interest_coverage(financials) -> float | None:
    pair = _latest_common(["EBIT", "Operating Income"], ["Interest Expense", "Interest Expense Non Operating"], financials)
    if pair is None:
        return None
    ebit, interest = pair
    if not interest:
        return None
    return round(ebit / abs(interest), 2)


def _compute_current_ratio(balance_sheet, info) -> float | None:
    cur_assets = _first(["Current Assets"], balance_sheet)
    cur_liab = _first(["Current Liabilities"], balance_sheet)
    if cur_assets is not None and cur_liab:
        return round(cur_assets / cur_liab, 2)
    cr = info.get("currentRatio")
    return float(cr) if cr is not None else None


def _cross_ratio_series(numer_names, numer_df, denom_names, denom_df, mult) -> list[tuple[str, float]]:
    """อัตราส่วนข้ามงบ จับคู่ 'ปีเดียวกัน' เช่น DSO = Receivables(งบดุล)/Revenue(งบกำไร)*365.
    ตัวหาร (revenue) มาจากคนละ DataFrame จึง index ด้วยปีก่อนแล้วค่อยจับคู่."""
    nrow = _find_row(numer_names, numer_df)
    drow = _find_row(denom_names, denom_df)
    if nrow is None or drow is None:
        return []
    denom_by_year: dict[int, float] = {}
    for col in denom_df.columns:
        year = getattr(col, "year", None)
        val = denom_df.loc[drow, col]
        if year is not None and pd.notna(val) and val != 0:
            denom_by_year[year] = float(val)
    out = []
    for col in numer_df.columns:
        year = getattr(col, "year", None)
        num = numer_df.loc[nrow, col]
        den = denom_by_year.get(year)
        if year is not None and pd.notna(num) and den:
            out.append((f"FY{year}", round(float(num) / den * mult, 2)))
    return out


def _compute_goodwill(balance_sheet) -> tuple[float | None, float | None]:
    """คืน (goodwill, goodwill เป็น % ของสินทรัพย์รวม). ถ้าบริษัทไม่มี goodwill -> (None, None)."""
    goodwill = _first(["Goodwill"], balance_sheet)
    if goodwill is None:
        return None, None
    total_assets = _first(["Total Assets"], balance_sheet)
    pct = round(goodwill / total_assets * 100, 2) if total_assets else None
    return goodwill, pct


def _fcf_yield(fcf, market_cap) -> float | None:
    if fcf is None or not market_cap:
        return None
    return round((fcf / market_cap) * 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER
# ─────────────────────────────────────────────────────────────────────────────
class StockFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str) -> StockFundamentals:
        t = yf.Ticker(ticker)
        info = t.info
        fin, bs, cf = t.financials, t.balance_sheet, t.cashflow

        revenue = info.get("totalRevenue") or _first(["Total Revenue"], fin)
        revenue = float(revenue) if revenue is not None else None
        fcf = _compute_free_cash_flow(info, cf)
        market_cap = info.get("marketCap")
        goodwill, goodwill_pct = _compute_goodwill(bs)
        roic, nopat, invested_capital = _compute_roic(fin, bs)

        return StockFundamentals(
            period=_period_label(fin.columns[0]) if fin is not None and not fin.empty else "N/A",
            revenue=revenue,
            free_cash_flow=fcf,
            fcf_margin=round((fcf / revenue) * 100, 2) if fcf is not None and revenue else None,
            roic=roic,
            roe=_compute_roe(fin, bs),
            revenue_cagr=_compute_revenue_cagr(fin),
            net_debt_to_ebitda=_compute_net_debt_to_ebitda(bs, fin, info),
            interest_coverage=_compute_interest_coverage(fin),
            current_ratio=_compute_current_ratio(bs, info),
            goodwill=goodwill,
            goodwill_pct_assets=goodwill_pct,
            pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            peg=info.get("trailingPegRatio") or info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            fcf_yield=_fcf_yield(fcf, market_cap),
            market_cap=float(market_cap) if market_cap is not None else None,
            avg_volume=float(info["averageVolume"]) if info.get("averageVolume") is not None else None,
            net_income=_first(["Net Income", "Net Income Common Stockholders"], fin),
            cfo=_first(["Operating Cash Flow", "Total Cash From Operating Activities"], cf),
            net_debt=_compute_net_debt(bs),
            capex=_first(["Capital Expenditure", "Capital Expenditures"], cf),
            depreciation_amortization=_first(["Depreciation And Amortization", "Depreciation Amortization Depletion"], cf),
            nwc_change=_first(["Change In Working Capital"], cf),
            nopat=nopat,
            invested_capital=invested_capital,
            beta=float(info["beta"]) if info.get("beta") is not None else None,
            gross_margin_series=_ratio_series(["Gross Profit"], ["Total Revenue"], fin),
            operating_margin_series=_ratio_series(["Operating Income", "EBIT"], ["Total Revenue"], fin),
            net_margin_series=_ratio_series(["Net Income", "Net Income Common Stockholders"], ["Total Revenue"], fin),
            share_count_series=_series(["Diluted Average Shares", "Basic Average Shares"], fin),
            fcf_series=_series(["Free Cash Flow"], cf),
            dso_series=_cross_ratio_series(["Receivables", "Accounts Receivable"], bs, ["Total Revenue", "Operating Revenue"], fin, 365),
            inventory_pct_series=_cross_ratio_series(["Inventory"], bs, ["Total Revenue", "Operating Revenue"], fin, 100),
            roe_series=_cross_ratio_series(["Net Income", "Net Income Common Stockholders"], fin, ["Stockholders Equity", "Total Stockholder Equity"], bs, 100),
            net_debt_to_ebitda_series=_net_debt_to_ebitda_series(bs, fin),
            current_ratio_series=_ratio_series(["Current Assets"], ["Current Liabilities"], bs, pct=False),
        )


if __name__ == "__main__":
    # เครื่องมือ debug: ดูทุก Fact ของ ticker หนึ่งดิบ ๆ (ไม่เรียก LLM, ไม่กิน quota)
    # ใช้ตอนสงสัยว่า "ทำไม confidence ต่ำ / คำอธิบายดูขัดแย้งกัน" — ไล่ดู label+period+value
    # เทียบกันเองได้ทันที ไม่ต้องเปิด python -c หลายรอบแบบตอนไล่บั๊ก TTM/FY ของ SBUX
    #   ใช้:  python -m src.providers.stock.fundamentals SBUX
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    facts = StockFundamentalsProvider().get_fundamentals(ticker).to_facts()
    facts.sort(key=lambda f: (f.label, f.period))
    print(f"=== {ticker}: {len(facts)} facts ===")
    for f in facts:
        print(f"  {f.label:22} = {f.value:>18,.4f}  {f.unit:8} period={f.period}")