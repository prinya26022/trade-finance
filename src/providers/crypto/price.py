"""Crypto price provider — reuse yfinance (รองรับ 'BTC-USD', 'ETH-USD' ฯลฯ).

watchlist เก็บ ticker แบบสั้น ('BTC') — เราต่อ '-USD' ให้ yfinance เอง เพื่อให้ผู้ใช้
พิมพ์เหมือนหุ้น ไม่ต้องรู้ format ของ yfinance.
"""
from datetime import datetime

import yfinance as yf

from src.domain.interfaces import PriceProvider, PriceSnapshot


def yf_symbol(ticker: str) -> str:
    """'BTC' -> 'BTC-USD'; 'BTC-USD' -> 'BTC-USD' (กันเผลอใส่ซ้ำ)."""
    t = ticker.upper()
    return t if t.endswith("-USD") else f"{t}-USD"


class CryptoPriceProvider(PriceProvider):
    def get_price(self, ticker: str) -> PriceSnapshot:
        info = yf.Ticker(yf_symbol(ticker)).fast_info
        return PriceSnapshot(
            ticker=ticker.upper(),          # คงชื่อสั้นตามที่อยู่ใน watchlist
            price=info["lastPrice"],
            currency=info["currency"],
            as_of=datetime.now().isoformat(),
        )
