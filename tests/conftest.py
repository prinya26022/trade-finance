"""Fixtures ร่วมของ test suite.

หัวใจคือ `tmp_db`: ชี้ DB_PATH ของ *ทุก* store ไปที่ไฟล์ชั่วคราว เพื่อให้ test
เขียน/อ่าน SQLite ได้จริง โดยไม่แตะ data/watchlist.db ของจริง และแต่ละ test เริ่มจาก
DB เปล่า (store จะ self-init สร้างตารางเองตอนเรียกครั้งแรก).
"""
import importlib
import json

import pytest

# ทุก store ที่ผูกกับไฟล์ DB เดียวกัน (data/watchlist.db) — ต้อง redirect ให้ครบ
_STORE_MODULES = [
    "src.watchlist.store",
    "src.history.store",
    "src.thesis.store",
    "src.settings.store",
]


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """ชี้ DB_PATH ของทุก store ไปไฟล์ temp -> test แยกกันสะอาด ไม่แตะ DB จริง."""
    db = tmp_path / "test.db"
    for mod_name in _STORE_MODULES:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, "DB_PATH", db, raising=False)
    return db


class FakeSummary:
    """แทน Pydantic Summary แบบเบาๆ สำหรับ save_analysis (ต้องมี attribute + model_dump_json)."""

    def __init__(self, ticker="AAPL", strength="strong", valuation="fair",
                 sentiment="neutral", price=100.0, confidence=0.8, **extra):
        self.ticker = ticker
        self.fundamental_strength = strength
        self.valuation_view = valuation
        self.sentiment = sentiment
        self.price = price
        self.confidence = confidence
        self._extra = extra

    def model_dump_json(self):
        return json.dumps({
            "ticker": self.ticker,
            "fundamental_strength": self.fundamental_strength,
            "valuation_view": self.valuation_view,
            "sentiment": self.sentiment,
            "price": self.price,
            "confidence": self.confidence,
            "thesis_relevant_news": self._extra.get("thesis_relevant_news", []),
        })


@pytest.fixture
def fake_summary():
    return FakeSummary


def save_row(ticker="AAPL", facts=None, **kw):
    """helper: บันทึกผลวิเคราะห์ 1 แถวลง history store (tmp_db ต้อง active อยู่ก่อน)."""
    from src.history.store import save_analysis
    summary = FakeSummary(ticker=ticker, **kw)
    grounding = {"price_ok": True, "news_grounded_ratio": 1.0,
                 "facts": {"facts_grounded_ratio": 1.0}}
    return save_analysis(summary, grounding, facts or [])
