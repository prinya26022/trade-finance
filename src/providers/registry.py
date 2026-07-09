from dataclasses import dataclass
from src.domain.interfaces import PriceProvider, NewsProvider, FundamentalsProvider
from src.providers.stock.price import StockPriceProvider
from src.providers.stock.news import MaterialNewsProvider
from src.providers.stock.fundamentals import StockFundamentalsProvider

@dataclass
class ProviderBundle:
    price: PriceProvider
    news: NewsProvider
    fundamentals: FundamentalsProvider

def get_providers(asset_type: str) -> ProviderBundle:
    if asset_type == "stock":
        return ProviderBundle(
            price=StockPriceProvider(),
            news=MaterialNewsProvider(),
            fundamentals=StockFundamentalsProvider(),
        )
    raise ValueError(f"unknown asset_type: {asset_type}")