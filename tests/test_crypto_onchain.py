"""ชั้น on-chain ของ BTC (Phase 33.5). Offline ล้วน — ไม่แตะ blockchain.info จริง.

CRYPTO_FRAMEWORK สั่งให้ประเมิน 'การใช้งานจริง/adoption' และ 'ความปลอดภัยของเครือข่าย' มาตั้งแต่
Phase 9 แต่ DATA ที่ส่งไปมีแค่ tokenomics — สั่งให้ตอบคำถามที่ไม่มีข้อมูลให้ตอบ คือสูตรของการเดา
ที่ฟังดูน่าเชื่อ (บทเรียนเดียวกับ Phase 33.1: อะไรคำนวณได้ให้คำนวณแล้ววางเป็นบรรทัดใน DATA)
"""
from src.providers.crypto import onchain
from src.providers.crypto.fundamentals import CryptoFundamentals


def _series(values: list[float]) -> list[dict]:
    return [{"x": 1_700_000_000 + i * 86400, "y": v} for i, v in enumerate(values)]


def test_unsupported_chain_returns_nothing_rather_than_guessing(monkeypatch):
    """blockchain.info เป็น API ของเชน BTC เท่านั้น — เหรียญอื่นต้องไม่ได้ตัวเลขที่นิยามคนละแบบ
    มาสวมป้ายเดียวกัน (active addresses ของเชน account-based นับคนละอย่างกับ BTC)."""
    monkeypatch.setattr(onchain, "_fetch_chart", lambda chart: _series([1.0] * 365))
    assert onchain.get_onchain_metrics("ETH") == {}
    assert onchain.get_onchain_metrics("SOL") == {}


def test_level_is_a_30day_average_and_trend_compares_year_start(monkeypatch):
    """ค่า on-chain แกว่งรายวันแรงมาก — ค่าวันเดียวคือ noise ไม่ใช่ระดับของเครือข่าย."""
    monkeypatch.setattr(onchain, "_fetch_chart", lambda chart: _series([100.0] * 30 + [0.0] * 305 + [200.0] * 30))

    metrics = onchain.get_onchain_metrics("BTC")

    assert metrics["Active Addresses"] == (200.0, "addresses")   # เฉลี่ย 30 วันท้าย
    assert metrics["Active Addresses YoY"] == (100.0, "%")       # เทียบ 30 วันแรก (100 -> 200)


def test_series_too_short_to_show_a_trend_is_skipped(monkeypatch):
    """ข้อมูลสั้นเกินไป = ไม่มีทิศทางให้ดู ต้องไม่ใส่ตัวเลขที่คำนวณจากฐานที่ไม่พอ."""
    monkeypatch.setattr(onchain, "_fetch_chart", lambda chart: _series([100.0] * 40))
    assert onchain.get_onchain_metrics("BTC") == {}


def test_api_failure_degrades_to_empty_not_an_exception(monkeypatch):
    """on-chain ล่มต้องไม่ล้มรอบวิเคราะห์ทั้งรอบ (หลักเดียวกับข่าว/EDGAR ใน loop.py)."""
    monkeypatch.setattr(onchain, "_fetch_chart", lambda chart: [])
    assert onchain.get_onchain_metrics("BTC") == {}


def test_zero_baseline_gives_a_level_without_a_fabricated_trend(monkeypatch):
    """ฐานเป็นศูนย์ -> คำนวณ % เทียบไม่ได้ ต้องมีแต่ระดับ ไม่ใช่หารศูนย์หรือใส่ 0 มั่วๆ."""
    monkeypatch.setattr(onchain, "_fetch_chart", lambda chart: _series([0.0] * 30 + [1.0] * 335))

    metrics = onchain.get_onchain_metrics("BTC")
    assert "Active Addresses" in metrics
    assert "Active Addresses YoY" not in metrics


def test_onchain_metrics_reach_the_data_block_as_facts():
    f = CryptoFundamentals(
        market_cap=1.28e12, volume_24h=2.5e10,
        circulating_supply=20_065_256.0, max_supply=21_000_000.0, price=63_000.0,
        onchain={"Active Addresses": (469_414.77, "addresses"),
                 "Hash Rate YoY": (-5.59, "%")},
    )
    by_label = {x.label: x for x in f.to_facts()}

    assert by_label["Active Addresses"].value == 469_414.77
    assert by_label["Active Addresses"].unit == "addresses"
    assert by_label["Hash Rate YoY"].value == -5.59
    assert "Supply Issued" in by_label          # ของเดิมต้องยังอยู่ครบ


def test_crypto_without_onchain_data_keeps_working():
    """เชนที่ยังไม่รองรับต้องได้ facts ชุดเดิมเป๊ะ — งานนี้คือการเพิ่ม ไม่ใช่เปลี่ยนของเดิม."""
    f = CryptoFundamentals(market_cap=1.0e11, volume_24h=1.0e9, circulating_supply=1.2e8)
    labels = {x.label for x in f.to_facts()}
    assert labels == {"Market Cap", "24h Volume", "Volume / Market Cap", "Circulating Supply"}
