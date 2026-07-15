"""Sensitivity / robustness analysis ของ threshold ทั้งหมดใน health score (Phase 19.5, เวอร์ชัน
ที่ทำได้จริงบนข้อมูลปัจจุบัน).

ตอบคำถาม: threshold ตัวไหน 'load-bearing' (ขยับเล็กน้อยแล้ว tier/ranking ของ watchlist เปลี่ยน)
vs 'inert' (ขยับยังไงในช่วงที่สมเหตุสมผลก็ไม่กระเทือน เพราะทุกตัวห่างจากเกณฑ์นั้นมาก). ผลลัพธ์คือ
'แผนที่ความเปราะ' — ชี้ว่าควรกังวลกับการตั้งค่าตัวไหนเป็นพิเศษ และตัวไหนตั้งยังไงก็ได้ไม่ต้องเสีย
เวลา debate.

สิ่งที่นี่ 'ไม่ใช่': predictive calibration (พิสูจน์ว่า threshold ทำนายผลตอบแทนได้จริง) — อันนั้น
ต้อง point-in-time backtest บน universe กว้างหลายร้อยตัวที่ไม่มี survivorship bias (watchlist
ปัจจุบัน 7 ตัวเป็นหุ้นที่เลือกมาว่าดีแล้ว + รอดหมด — calibrate ไม่ได้ ดู 19.5 ใน AGENT_PROJECT.md).
sensitivity ตอบได้แค่ 'ค่าที่ตั้งไว้ตอนนี้ เปราะแค่ไหนต่อ watchlist ชุดนี้' ไม่ใช่ 'ค่าที่ถูกคืออะไร'.

ใช้:  python -m src.agent.sensitivity
"""
import sys
from contextlib import contextmanager
from types import SimpleNamespace

from src.agent import health as H
from src.agent import valuation as V
from src.history.store import latest_per_ticker
from src.providers.stock.market import get_risk_free_rate_pct

STEPS = 61   # จำนวนจุดต่อ 1 threshold ที่ sweep (ละเอียดพอจะหา 'ขอบที่พลิก' ได้)

# (module, attr, label, sweep_lo, sweep_hi) — ช่วง sweep ตั้งจากพิสัยที่ 'สมเหตุสมผลจะ debate จริง'
# ไม่ใช่ ±X% แบบสุ่ม (คนละ scale กันคนละตัว). ค่าปัจจุบันอ่านสดจาก module ตอนรัน (ไม่ hardcode ซ้ำ)
PARAMS = [
    # --- Fundamental /8 : threshold ของแต่ละเกณฑ์ ---
    (H, "NET_MARGIN_MIN_PCT",         "#2 Net Margin ขั้นต่ำ (%)",        0.0,  25.0),
    (H, "REVENUE_CAGR_THRESHOLD_PCT", "#4 Revenue CAGR ขั้นต่ำ (%)",      0.0,  15.0),
    (H, "LEVERAGE_MAX_X",             "#5 Net Debt/EBITDA เพดาน (x)",     1.0,   6.0),
    (H, "INTEREST_COVERAGE_MIN_X",    "#6 Interest Coverage ขั้นต่ำ (x)", 1.0,   8.0),
    (H, "ACCRUALS_TOLERANCE",         "#3 CFO/NI tolerance",              0.5,   1.2),
    # --- Fundamental /8 : ความชันของ graded band (19.3) ---
    (H, "BAND_PCT",                   "band % ทั่วไป (ROIC/margin/rev)",  1.0,   8.0),
    (H, "BAND_ACCRUALS_RATIO",        "band CFO/NI",                      0.02,  0.2),
    (H, "BAND_LEVERAGE_X",            "band leverage (x)",                0.5,   3.0),
    (H, "BAND_COVERAGE_X",            "band coverage (x)",                0.5,   4.0),
    (H, "BAND_MARGIN_TREND_PP",       "#7 band margin trend (pp)",        0.5,   4.0),
    (H, "BAND_DILUTION_PCT",          "#8 band dilution (%)",             0.5,   4.0),
    # --- Valuation /3 ---
    (V, "GAP_PP_GOOD",                "valuation gap band 2/3 (pp)",      1.0,  10.0),
    (V, "GAP_PP_FAIR",                "valuation gap band 1/3 (pp)",      5.0,  20.0),
    (V, "MIN_NOPAT_MARGIN",           "NOPAT margin ต่ำสุด (route guard)",0.0,  0.10),
    (V, "DIVERGENCE_TRIGGER_PP",      "sustainable divergence (pp)",      5.0,  30.0),
    (V, "RULE40_WEAK",                "Rule-of-40 เพดาน (growth lens)",  10.0,  40.0),
    (V, "CAP_INITIAL_GROWTH",         "growth lens เพดานปีแรก",           0.20,  0.60),
    (V, "SUSTAINABLE_GROWTH_CAP",     "value lens เพดาน sustainable",     0.10,  0.40),
    (V, "BETA_FLOOR",                 "beta floor (WACC clamp)",          0.5,   1.0),
    (V, "BETA_CAP",                   "beta cap (WACC clamp)",            1.2,   2.0),
]


@contextmanager
def _patched(module, attr, value):
    old = getattr(module, attr)
    setattr(module, attr, value)
    try:
        yield
    finally:
        setattr(module, attr, old)


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    if n < 2:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


def _load_scored_universe(risk_free_pct: float):
    """คืน list ของ (ticker, summary_ns, facts) เฉพาะตัวที่ 'มีคะแนน' จริง (ไม่ excluded) ตอน
    baseline — crypto/ข้อมูลไม่พอถูกคัดออก เพราะ sensitivity ของ threshold ไม่มีความหมายกับตัว
    ที่ไม่ได้เข้าสูตรอยู่แล้ว."""
    universe = []
    for row in latest_per_ticker():
        summary = SimpleNamespace(**row["summary"])
        facts = row.get("facts") or []
        h = H.compute_health(summary, [], facts, risk_free_pct)
        if h["score"] is not None:
            universe.append((row["ticker"], summary, facts, h["score"]))
    return universe


def _score_vector(universe, risk_free_pct) -> dict:
    """{ticker: score} ณ ค่า threshold ปัจจุบันของ module (ใครเรียกต้อง patch ไว้ก่อนถ้าจะเปลี่ยน)."""
    out = {}
    for ticker, summary, facts, _ in universe:
        h = H.compute_health(summary, [], facts, risk_free_pct)
        out[ticker] = h["score"]
    return out


def _tiers(scores: dict) -> dict:
    """map score -> tier ด้วย cutoff ปัจจุบัน (70%/45% ของ TOTAL_MAX)."""
    return {
        t: ("strong" if s is not None and s >= H.TOTAL_MAX * 0.7
            else "ok" if s is not None and s >= H.TOTAL_MAX * 0.45 else "weak")
        for t, s in scores.items()
    }


def _ranking(scores: dict) -> list[str]:
    """ลำดับ ticker เรียงคะแนนมาก->น้อย (tie-break ด้วยชื่อ ให้ deterministic)."""
    return [t for t, _ in sorted(scores.items(), key=lambda kv: (-(kv[1] or 0), kv[0]))]


def analyze_param(module, attr, label, lo, hi, universe, risk_free_pct,
                  base_tiers, base_rank) -> dict:
    """sweep 1 threshold แล้ววัดว่า tier/ranking ของ watchlist เปลี่ยนที่ค่าไหนบ้าง.
    คืน dict สรุป: มี tier flip ไหม + ที่ค่าเท่าไหร่, ranking เปลี่ยนไหม, ช่วงคะแนนที่ขยับ."""
    current = getattr(module, attr)
    values = sorted(set(_linspace(lo, hi, STEPS) + [current]))

    tier_flip_values = []   # ค่าที่ tier ต่างจาก baseline (อย่างน้อย 1 ticker)
    rank_change_values = []
    max_score_shift = 0.0

    for v in values:
        with _patched(module, attr, v):
            scores = _score_vector(universe, risk_free_pct)
        if _tiers(scores) != base_tiers:
            tier_flip_values.append(v)
        if _ranking(scores) != base_rank:
            rank_change_values.append(v)
        base_scores = {t: s for t, _, _, s in universe}
        shift = max(abs((scores[t] or 0) - base_scores[t]) for t in scores)
        max_score_shift = max(max_score_shift, shift)

    def _nearest_edge(vals):
        """ค่าที่ใกล้ current ที่สุดที่ทำให้เกิดการเปลี่ยน (ไว้บอก 'margin' ก่อนพลิก)."""
        return min(vals, key=lambda v: abs(v - current)) if vals else None

    tier_edge = _nearest_edge(tier_flip_values)
    return {
        "label": label, "attr": attr, "module": module.__name__.split(".")[-1],
        "current": current, "lo": lo, "hi": hi,
        "tier_flips": bool(tier_flip_values),
        "tier_edge": tier_edge,
        "tier_margin": abs(tier_edge - current) if tier_edge is not None else None,
        "rank_changes": bool(rank_change_values),
        "rank_edge": _nearest_edge(rank_change_values),
        "max_score_shift": round(max_score_shift, 2),
    }


def tier_cutoff_proximity(universe) -> list[dict]:
    """แยกวิเคราะห์ tier cutoff (70%/45%) ต่างหาก — cutoff ไม่กระทบ 'คะแนน' แค่ 'การจัดกลุ่ม'
    จึงดูตรงๆ ได้ว่าแต่ละ ticker อยู่ห่างเส้น strong(70%)/ok(45%) แค่ไหน (%ของ max) = margin
    ก่อนหลุด tier ถ้าขยับ cutoff."""
    out = []
    for ticker, _, _, score in universe:
        pct = score / H.TOTAL_MAX * 100
        out.append({
            "ticker": ticker, "score": score, "pct_of_max": round(pct, 1),
            "to_strong_line": round(pct - 70.0, 1),   # บวก=เหนือเส้น strong, ลบ=ต่ำกว่า
            "to_ok_line": round(pct - 45.0, 1),
        })
    return sorted(out, key=lambda r: -r["pct_of_max"])


def run() -> None:
    rf = get_risk_free_rate_pct()
    universe = _load_scored_universe(rf)
    if not universe:
        print("ไม่มี ticker ที่มีคะแนนใน watchlist — รัน analyze ก่อน")
        return

    base_scores = {t: s for t, _, _, s in universe}
    base_tiers = _tiers(base_scores)
    base_rank = _ranking(base_scores)

    print(f"=== Sensitivity analysis (Rf={rf:.2f}%, {len(universe)} หุ้นที่มีคะแนน) ===")
    print("baseline ranking:", " > ".join(f"{t}({base_scores[t]:.1f})" for t in base_rank))
    print()

    results = [analyze_param(m, a, lbl, lo, hi, universe, rf, base_tiers, base_rank)
               for (m, a, lbl, lo, hi) in PARAMS]

    # load-bearing ก่อน (มี tier flip -> เรียงตาม margin น้อยสุด = เปราะสุด), แล้วค่อย rank-only, แล้ว inert
    def _sort_key(r):
        if r["tier_flips"]:
            return (0, r["tier_margin"])
        if r["rank_changes"]:
            return (1, 0)
        return (2, 0)
    results.sort(key=_sort_key)

    print(f"{'threshold':38} {'ปัจจุบัน':>9} {'สถานะ':<12} {'margin ก่อน tier พลิก':>22} {'Δscore สูงสุด':>13}")
    print("-" * 100)
    for r in results:
        if r["tier_flips"]:
            status = "LOAD-BEARING"
            margin = f"{r['tier_margin']:.2f} (ที่ {r['tier_edge']:.2f})"
        elif r["rank_changes"]:
            status = "rank-only"
            margin = f"rank เปลี่ยนที่ {r['rank_edge']:.2f}"
        else:
            status = "inert"
            margin = "— (ไม่พลิกทั้งช่วง)"
        cur = f"{r['current']:.3f}".rstrip("0").rstrip(".")
        print(f"{r['label']:38} {cur:>9} {status:<12} {margin:>22} {r['max_score_shift']:>13.2f}")

    print()
    print("=== Tier cutoff proximity (เส้น strong=70%, ok=45% ของ /{:.0f}) ===".format(H.TOTAL_MAX))
    print(f"{'ticker':8} {'score':>6} {'%ของmax':>8} {'ห่างเส้น strong':>16} {'ห่างเส้น ok':>14}")
    print("-" * 60)
    for r in tier_cutoff_proximity(universe):
        print(f"{r['ticker']:8} {r['score']:>6.1f} {r['pct_of_max']:>7.1f}% "
              f"{r['to_strong_line']:>+15.1f} {r['to_ok_line']:>+13.1f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run()
