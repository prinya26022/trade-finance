"""Crypto news — yfinance aggregator บนสัญลักษณ์ '<COIN>-USD'.

ไม่มี 8-K/EDGAR สำหรับ crypto (ไม่มี SEC filing) จึงใช้ข่าว aggregator ล้วน. material
ปล่อยเป็น False ทั้งหมด (ยังไม่มีแหล่ง 'เหตุการณ์ทางการ' แบบ 8-K สำหรับ crypto ในสไลซ์นี้).
ล้มเงียบ -> [] เพื่อไม่ให้ทั้ง analyze พังเพราะข่าว.
"""
import yfinance as yf

from src.domain.interfaces import NewsProvider, NewsItem
from src.providers.crypto.price import yf_symbol


class CryptoNewsProvider(NewsProvider):
    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        try:
            raw = yf.Ticker(yf_symbol(ticker)).news or []
        except Exception:
            return []
        out: list[NewsItem] = []
        for item in raw[:limit]:
            content = item.get("content", {})
            title = content.get("title")
            if not title:
                continue
            out.append(
                NewsItem(
                    title=title,
                    url=content.get("canonicalUrl", {}).get("url", ""),
                    published_at=content.get("pubDate", ""),
                    source=content.get("provider", {}).get("displayName", "yfinance"),
                )
            )
        return out
