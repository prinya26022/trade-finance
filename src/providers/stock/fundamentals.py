from dataclasses import dataclass
from src.domain.interfaces import Fundamentals, FundamentalsProvider, Fact

@dataclass
class StockFundamentals(Fundamentals):
    revenue: float
    free_cash_flow: float
    roic: float
    
    def to_facts(self) -> list[Fact]:
        return [
            Fact("Revenue",     self.revenue,       "USD",  "FY2024"),
            Fact("Free Cash Flow",     self.free_cash_flow,       "USD",  "FY2024"),
            Fact("ROIC",     self.roic,       "%",  "FY2024"),
        ]
    
class StockFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str) -> StockFundamentals:
        return StockFundamentals(
            revenue=383e9,
            free_cash_flow=99e9,
            roic=56.0,
        )