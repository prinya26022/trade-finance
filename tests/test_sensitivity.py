"""Sensitivity harness — pure helpers, offline (ตัว run() เต็มแตะ DB/network จึงไม่เทสต์ที่นี่
เทสต์เฉพาะ logic ที่ deterministic: linspace, tier bucketing, ranking, patch/restore)."""
from src.agent import health as H
from src.agent import sensitivity as S


def test_linspace_inclusive_endpoints():
    xs = S._linspace(0.0, 10.0, 11)
    assert xs[0] == 0.0 and xs[-1] == 10.0 and len(xs) == 11
    assert xs[5] == 5.0


def test_linspace_degenerate_single_point():
    assert S._linspace(3.0, 9.0, 1) == [3.0]


def test_tiers_bucket_on_total_max():
    # cutoff 70%/45% ของ TOTAL_MAX
    strong = H.TOTAL_MAX * 0.7
    ok = H.TOTAL_MAX * 0.45
    scores = {"A": strong + 0.1, "B": ok + 0.1, "C": ok - 0.1, "D": None}
    tiers = S._tiers(scores)
    assert tiers == {"A": "strong", "B": "ok", "C": "weak", "D": "weak"}


def test_ranking_orders_desc_with_name_tiebreak():
    scores = {"NVDA": 5.9, "SBUX": 5.9, "DUOL": 9.9, "AAPL": 7.0}
    # 5.9 เท่ากัน -> tie-break ด้วยชื่อ (NVDA ก่อน SBUX), คะแนนมากขึ้นก่อน
    assert S._ranking(scores) == ["DUOL", "AAPL", "NVDA", "SBUX"]


def test_patched_restores_value_even_on_exception():
    original = H.NET_MARGIN_MIN_PCT
    try:
        with S._patched(H, "NET_MARGIN_MIN_PCT", 999.0):
            assert H.NET_MARGIN_MIN_PCT == 999.0
            raise ValueError("boom")
    except ValueError:
        pass
    assert H.NET_MARGIN_MIN_PCT == original   # ต้องคืนค่าเดิมเสมอ ไม่รั่วไป test อื่น


def test_tier_cutoff_proximity_computes_distance_to_lines():
    # score 7.7 บน /11 = 70.0% พอดี (ขอบเส้น strong)
    universe = [("X", None, None, H.TOTAL_MAX * 0.7)]
    rows = S.tier_cutoff_proximity(universe)
    assert rows[0]["ticker"] == "X"
    assert rows[0]["to_strong_line"] == 0.0
    assert rows[0]["to_ok_line"] == 25.0   # 70% - 45%
