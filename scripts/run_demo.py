"""
Smoke-test runner for the provider layer (src/providers).

Usage:
    python scripts/run_demo.py AAPL
    python scripts/run_demo.py AAPL --mock   # no network / no yfinance needed
"""
import sys
import argparse
from pathlib import Path

# allow running as `python scripts/run_demo.py` from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.domain.interfaces import PriceProvider, NewsProvider, FundamentalsProvider, PriceSnapshot, NewsItem, Fact
from src.providers.registry import get_providers, ProviderBundle


class MockPriceProvider(PriceProvider):
    def get_price(self, ticker: str) -> PriceSnapshot:
        return PriceSnapshot(ticker=ticker, price=123.45, currency="USD", as_of="2026-07-05T00:00:00")


class MockNewsProvider(NewsProvider):
    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        return [
            NewsItem(
                title=f"Mock headline #{i} about {ticker}",
                url="https://example.com/mock",
                published_at="2026-07-05T00:00:00Z",
                source="MockWire",
            )
            for i in range(1, limit + 1)
        ]


class MockFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str):
        from src.providers.stock.fundamentals import StockFundamentals
        return StockFundamentals(revenue=1e9, free_cash_flow=2e8, roic=25.0)


def get_mock_providers() -> ProviderBundle:
    return ProviderBundle(
        price=MockPriceProvider(),
        news=MockNewsProvider(),
        fundamentals=MockFundamentalsProvider(),
    )


def main():
    parser = argparse.ArgumentParser(description="Run the stock provider bundle for a ticker.")
    parser.add_argument("ticker", nargs="?", default="AAPL")
    parser.add_argument("--mock", action="store_true", help="use in-memory mock providers instead of yfinance")
    parser.add_argument("--limit", type=int, default=3, help="max news items")
    args = parser.parse_args()

    providers = get_mock_providers() if args.mock else get_providers("stock")

    print(f"--- {args.ticker} ({'mock' if args.mock else 'live'}) ---")

    price = providers.price.get_price(args.ticker)
    print(f"\nPrice: {price.price} {price.currency}  (as of {price.as_of})")

    print(f"\nNews (top {args.limit}):")
    for item in providers.news.get_news(args.ticker, limit=args.limit):
        print(f"  - [{item.source}] {item.title}\n    {item.url}")

    print("\nFundamentals:")
    for fact in providers.fundamentals.get_fundamentals(args.ticker).to_facts():
        print(f"  - {fact.label}: {fact.value} {fact.unit} ({fact.period})")


if __name__ == "__main__":
    main()