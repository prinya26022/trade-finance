import yfinance as yf
import pandas as pd
from dataclasses import dataclass
from src.domain.interfaces import Fundamentals, FundamentalsProvider, Fact

@dataclass
class StockFundamentals(Fundamentals):
    revenue: float | None
    free_cash_flow: float | None
    roic: float | None
    period: str = "FY2024"

    def to_facts(self) -> list[Fact]:
        # missing metric -> no Fact (never fake a 0.0 that reads as a real zero)
        candidates = [
            ("Revenue", self.revenue, "USD"),
            ("Free Cash Flow", self.free_cash_flow, "USD"),
            ("ROIC", self.roic, "%"),
        ]
        return [
            Fact(label, value, unit, self.period)
            for label, value, unit in candidates
            if value is not None
        ]


def _first(row_names, df):
    """Return the first matching row's most recent column value, or None."""
    if df is None or df.empty:
        return None
    latest_col = df.columns[0]
    for name in row_names:
        if name in df.index:
            value = df.loc[name, latest_col]
            if pd.notna(value):
                return float(value)
    return None


def _compute_free_cash_flow(info: dict, cashflow) -> float | None:
    fcf = info.get("freeCashflow")
    if fcf is not None:
        return float(fcf)
    op_cash_flow = _first(["Operating Cash Flow", "Total Cash From Operating Activities"], cashflow)
    capex = _first(["Capital Expenditure", "Capital Expenditures"], cashflow)
    if op_cash_flow is not None and capex is not None:
        return op_cash_flow + capex  # capex is stored as a negative number
    return None


def _latest_period_label(financials) -> str:
    """Derive a fiscal-year label (e.g. 'FY2025') from the most recent financials column."""
    if financials is None or financials.empty:
        return "N/A"
    latest_col = financials.columns[0]
    try:
        return f"FY{latest_col.year}"
    except AttributeError:
        return str(latest_col)


def _compute_roic(financials, balance_sheet) -> float | None:
    operating_income = _first(["Operating Income", "EBIT"], financials) #กำไรจากการดำเนินงาน ก่อนดอกเบี้ยและภาษี
    pretax_income = _first(["Pretax Income"], financials)
    tax_provision = _first(["Tax Provision"], financials)

    total_debt = _first(["Total Debt"], balance_sheet)
    total_equity = _first(["Stockholders Equity", "Total Stockholder Equity"], balance_sheet)
    cash = _first(
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
        balance_sheet,
    )

    if operating_income is None or total_debt is None or total_equity is None or cash is None:
        return None

    tax_rate = tax_provision / pretax_income if pretax_income and tax_provision is not None else 0.0 # อัตราภาษีจริงที่จ่าย
    nopat = operating_income * (1 - tax_rate) #กำไรจากการดำเนินงานหลังหักภาษี
    invested_capital = total_debt + total_equity - cash #หนี้ + ส่วนของเจ้าของ = เงินทั้งหมดที่ใส่เข้าธุรกิจ (ลบ cash ออก เพราะเงินสดที่กองเฉยๆ ไม่ได้ "ลงทุน" ในการดำเนินงาน)

    if not invested_capital:
        return None
    return round((nopat / invested_capital) * 100, 2)


class StockFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str) -> StockFundamentals:
        t = yf.Ticker(ticker)
        info = t.info

        revenue = info.get("totalRevenue")
        free_cash_flow = _compute_free_cash_flow(info, t.cashflow)
        roic = _compute_roic(t.financials, t.balance_sheet)
        period = _latest_period_label(t.financials)

        return StockFundamentals(
            revenue=float(revenue) if revenue is not None else None,
            free_cash_flow=free_cash_flow,   # already None when missing
            roic=roic,                       # already None when missing
            period=period,
        )