"""Crypto provider (thin slice) — tokenomics logic + wiring, offline."""
import pytest

from src.providers.crypto.fundamentals import CryptoFundamentals
from src.providers.crypto.price import yf_symbol


def test_yf_symbol_maps_short_ticker():
    assert yf_symbol("btc") == "BTC-USD"
    assert yf_symbol("ETH") == "ETH-USD"
    assert yf_symbol("BTC-USD") == "BTC-USD"   # กันใส่ซ้ำ


def test_capped_coin_tokenomics():
    f = CryptoFundamentals(
        name="Bitcoin", price=60_000, market_cap=1_200_000_000_000,
        volume_24h=30_000_000_000, circulating_supply=20_000_000,
        max_supply=21_000_000, total_supply=20_000_000,
    )
    facts = {x.label: x for x in f.to_facts()}

    assert facts["Supply Issued"].value == pytest.approx(20 / 21 * 100, rel=1e-3)
    assert facts["Dilution Ahead"].value == pytest.approx(1_000_000 / 20_000_000 * 100, rel=1e-3)
    assert facts["Volume / Market Cap"].value == pytest.approx(30 / 1200 * 100, rel=1e-3)
    assert "Fully Diluted Valuation" in facts
    assert all(x.period == "spot" for x in f.to_facts())   # point-in-time (ไม่ใช่ FY)


def test_uncapped_coin_skips_dilution_metrics():
    # ETH ไม่มี hard cap -> คำนวณ Supply Issued/Dilution/FDV ไม่ได้ ต้องข้ามเงียบๆ
    f = CryptoFundamentals(
        name="Ethereum", price=3_000, market_cap=360_000_000_000,
        volume_24h=15_000_000_000, circulating_supply=120_000_000,
        max_supply=None, total_supply=120_000_000,
    )
    labels = {x.label for x in f.to_facts()}
    assert "Supply Issued" not in labels
    assert "Dilution Ahead" not in labels
    assert "Fully Diluted Valuation" not in labels
    assert {"Market Cap", "24h Volume", "Circulating Supply"} <= labels


def test_no_none_facts_when_data_sparse():
    # ข้อมูลไม่ครบ (มีแค่ market cap) -> ต้องไม่มี Fact ที่ value เป็น None (ห้ามปลอม 0)
    f = CryptoFundamentals(name="X", market_cap=1_000_000)
    facts = f.to_facts()
    assert [x.label for x in facts] == ["Market Cap"]
    assert all(x.value is not None for x in facts)


def test_registry_returns_crypto_bundle():
    from src.providers.registry import get_providers
    from src.providers.crypto.price import CryptoPriceProvider
    from src.providers.crypto.news import CryptoNewsProvider
    from src.providers.crypto.fundamentals import CryptoFundamentalsProvider

    b = get_providers("crypto")
    assert isinstance(b.price, CryptoPriceProvider)
    assert isinstance(b.news, CryptoNewsProvider)
    assert isinstance(b.fundamentals, CryptoFundamentalsProvider)
