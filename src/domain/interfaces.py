from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PriceSnapshot:
    ticker: str
    price: float
    currency: str
    as_of: str

@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str
    source: str

@dataclass
class Fact:
    label: str
    value: float
    unit: str = ""
    period: str = ""

class PriceProvider(ABC):
    @abstractmethod
    def get_price(self, ticker: str) -> PriceSnapshot: ...

class NewsProvider(ABC):
    @abstractmethod
    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]: ...

class Fundamentals(ABC):
    @abstractmethod
    def to_facts(self) -> list[Fact]: ...

class FundamentalsProvider(ABC):
    @abstractmethod
    def get_fundamentals(self, ticker: str) -> Fundamentals: ...