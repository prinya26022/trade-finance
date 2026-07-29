"""ถือเดิมพันเดียวกันกี่ชั้น (Phase 30) — คณิตศาสตร์ล้วน ฉีดราคาเข้าไปเอง ไม่แตะ yfinance."""
import math

import pytest

from src.agent import correlation as corr


def _series(values: list[float], start_day: int = 1) -> dict[str, float]:
    """{YYYY-MM-DD: close} จาก list ราคา (วันติดกัน)."""
    return {f"2026-01-{start_day + i:02d}": v for i, v in enumerate(values)}


def _walk(steps: list[float], base: float = 100.0) -> dict[str, float]:
    """สร้างราคาจากผลตอบแทนรายวันที่กำหนด (ควบคุม correlation ได้แม่นๆ)."""
    closes, price = [base], base
    for s in steps:
        price *= (1 + s)
        closes.append(price)
    return _series(closes)


def test_daily_returns_uses_returns_not_prices():
    r = corr.daily_returns(_series([100.0, 110.0, 99.0]))
    assert list(r.values()) == pytest.approx([0.1, -0.1])


def test_pearson_perfect_and_inverse():
    assert corr.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0
    assert corr.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == -1.0
    assert corr.pearson([1, 1, 1], [1, 2, 3]) is None    # นิ่งสนิท -> ไม่นิยาม ไม่ใช่ 0


def test_needs_minimum_overlap_before_reporting():
    """ข้อมูลทับกันน้อยเกินไป = ไม่รายงานตัวเลข ดีกว่ารายงานเลขที่ไม่มีความหมาย."""
    steps = [0.01, -0.01] * 5      # 10 วัน < MIN_OVERLAP_DAYS
    a, b = corr.daily_returns(_walk(steps)), corr.daily_returns(_walk(steps))
    value, days = corr.correlate(a, b, window=90)
    assert value is None
    assert days < corr.MIN_OVERLAP_DAYS


def test_identical_movers_flagged_as_same_bet():
    steps = [0.01, -0.02, 0.015, -0.005] * 15    # 60 วัน
    closes = {"NVDA": _walk(steps), "TSM": _walk(steps, base=50.0)}
    out = corr.analyze(closes)

    pair = out["pairs"][0]
    assert pair["corr"]["90d"] == 1.0
    assert pair["high"] is True
    assert out["summary"]["n_high"] == 1
    assert "ตัวเดียวกัน" in pair["note"]


def test_opposite_movers_not_flagged():
    steps = [0.01, -0.02, 0.015, -0.005] * 15
    closes = {"AAA": _walk(steps), "BBB": _walk([-s for s in steps])}
    out = corr.analyze(closes)

    assert out["pairs"][0]["corr"]["90d"] == -1.0
    assert out["summary"]["n_high"] == 0
    assert "สวนทาง" in out["pairs"][0]["note"]


def test_both_held_pairs_report_combined_weight():
    """คู่ที่วิ่งด้วยกัน 'และถืออยู่จริงทั้งคู่' คือเคสที่ต้องเตือน — ต้องบอกว่ากินพอร์ตรวมเท่าไหร่."""
    steps = [0.01, -0.02, 0.015, -0.005] * 15
    closes = {"NVDA": _walk(steps), "TSM": _walk(steps, base=50.0), "MA": _walk([-s for s in steps])}
    out = corr.analyze(closes, weights={"NVDA": 30.0, "TSM": 25.0})

    high = out["high_pairs"][0]
    assert high["both_held"] is True
    assert high["combined_weight"] == 55.0
    assert out["summary"]["n_high_held"] == 1
    assert out["summary"]["held_weight_in_high"] == 55.0


def test_watching_only_pair_is_flagged_but_not_counted_as_held():
    steps = [0.01, -0.02, 0.015, -0.005] * 15
    closes = {"AAA": _walk(steps), "BBB": _walk(steps, base=20.0)}
    out = corr.analyze(closes, weights={"AAA": 40.0})   # ถือแค่ตัวเดียวในคู่

    assert out["high_pairs"][0]["both_held"] is False
    assert out["high_pairs"][0]["combined_weight"] is None
    assert out["summary"]["n_high_held"] == 0


def test_ticker_without_prices_is_skipped_not_crashing():
    steps = [0.01, -0.02, 0.015, -0.005] * 15
    out = corr.analyze({"AAA": _walk(steps), "DEAD": {}})
    assert out["tickers"] == ["AAA"]
    assert out["pairs"] == []


def test_caveat_is_always_present():
    """ตัวเลขนี้ห้ามถูกอ่านว่าเป็นเพดานความเสี่ยง — คำเตือนต้องติดไปกับผลลัพธ์เสมอ."""
    out = corr.analyze({})
    assert "ไม่เสถียร" in out["caveat"]


def test_pairs_sorted_most_correlated_first():
    steps = [0.01, -0.02, 0.015, -0.005] * 15
    noise = [((-1) ** i) * 0.004 + s * 0.1 for i, s in enumerate(steps)]
    closes = {"AAA": _walk(steps), "BBB": _walk(steps, base=30.0), "CCC": _walk(noise)}
    out = corr.analyze(closes)

    primaries = [p["primary"] for p in out["pairs"]]
    assert primaries == sorted(primaries, reverse=True)
    assert not math.isnan(primaries[0])
