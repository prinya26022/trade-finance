from dataclasses import dataclass
from src.domain.interfaces import PriceProvider, NewsProvider, FundamentalsProvider
from src.providers.stock.price import StockPriceProvider
from src.providers.stock.news import MaterialNewsProvider
from src.providers.stock.fundamentals import StockFundamentalsProvider
from src.providers.crypto.price import CryptoPriceProvider
from src.providers.crypto.news import CryptoNewsProvider
from src.providers.crypto.fundamentals import CryptoFundamentalsProvider

@dataclass
class ProviderBundle:
    price: PriceProvider
    news: NewsProvider
    fundamentals: FundamentalsProvider

def get_providers(asset_type: str) -> ProviderBundle:
    # asset-agnostic: watchlist/loop/eval/dashboard เหมือนกันหมด ต่างแค่ 3 provider นี้
    if asset_type == "stock":
        return ProviderBundle(
            price=StockPriceProvider(),
            news=MaterialNewsProvider(),
            fundamentals=StockFundamentalsProvider(),
        )
    if asset_type == "crypto":
        return ProviderBundle(
            price=CryptoPriceProvider(),
            news=CryptoNewsProvider(),
            fundamentals=CryptoFundamentalsProvider(),
        )
    raise ValueError(f"unknown asset_type: {asset_type}")