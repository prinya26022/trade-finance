"""News providers for stocks.

- StockNewsProvider   : ข่าว aggregator จาก yfinance (context กว้าง แต่ noise สูง)
- MaterialNewsProvider: รวม 8-K จาก SEC (material, มาก่อน) + yfinance (เติม context)
  พร้อม dedup และ fallback — ถ้าฝั่งใดฝั่งหนึ่งล่ม อีกฝั่งยังทำงานต่อได้
registry ใช้ MaterialNewsProvider เป็นตัวหลัก.
"""
import yfinance as yf

from src.domain.interfaces import NewsProvider, NewsItem
from src.providers.stock.edgar import recent_8k


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


def _norm(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())[:60]


class MaterialNewsProvider(NewsProvider):
    """เอา material events (8-K) ขึ้นก่อนเสมอ แล้วเติมด้วยข่าว aggregator จนครบ limit.
    material มาก่อนเพราะ signal สูงกว่า (สิ่งที่บริษัทถูกบังคับให้เปิดเผย ไม่ใช่ข่าวมือสอง)."""

    def __init__(self) -> None:
        self._agg = StockNewsProvider()

    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        # 1) material 8-K (ล้มเงียบ -> [] ให้ยังมี aggregator เหลือ)
        material = recent_8k(ticker, limit=limit, high_only=True)

        # 2) aggregator (ล้มเงียบเช่นกัน — เช่น yfinance เปลี่ยน schema)
        try:
            agg = self._agg.get_news(ticker, limit=limit)
        except Exception:
            agg = []

        # 3) merge: material ก่อน แล้วเติม aggregator ที่ยังไม่ซ้ำ (dedup ด้วย title ที่ normalize)
        seen = {_norm(n.title) for n in material}
        out = list(material)
        for a in agg:
            key = _norm(a.title)
            if key in seen:
                continue
            seen.add(key)
            out.append(a)
        return out[:limit]