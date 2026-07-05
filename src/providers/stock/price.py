import yfinance as yf
from datetime import datetime         
from src.domain.interfaces import PriceProvider, PriceSnapshot  

class StockPriceProvider(PriceProvider):
    def get_price(self, ticker: str) -> PriceSnapshot:
        info = yf.Ticker(ticker).fast_info
        return PriceSnapshot(
            ticker=ticker,
            price=info["lastPrice"],
            currency=info["currency"],
            as_of=datetime.now().isoformat(),
        )