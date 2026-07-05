import yfinance as yf
from datetime import datetime        
from src.domain.interfaces import NewsProvider, NewsItem

class StockNewsProvider(NewsProvider):
    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        raw = yf.Ticker(ticker).news
        return [
            NewsItem(
                title=item["content"]["title"], 
                url=item["content"]["canonicalUrl"]["url"],
                published_at=item["content"]["pubDate"], 
                source=item["content"]["provider"]["displayName"],
            )
            for item in raw[:limit]
        ]