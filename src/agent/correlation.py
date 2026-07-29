"""ถือเดิมพันเดียวกันกี่ชั้น (Phase 30) — วัดว่าของใน watchlist/พอร์ตวิ่งไปด้วยกันแค่ไหน.

ที่มา: บทวิเคราะห์ที่คนเชียร์กันมักเป็น "สายเดียวกัน" โดยไม่รู้ตัว — เช่น ASML (เครื่อง EUV)
-> TSMC (ผลิตชิป) -> NVDA (ขาย GPU) -> AMZN/AWS (ซื้อไปตั้ง data center) ทั้งสายคือเดิมพัน
เดียวกันบน AI capex. ถือ 4 ตัวนี้ = ไม่ได้กระจายความเสี่ยง แต่คือ 'ซื้อ trade เดียวกัน 4 ชั้น'
ซึ่งเป็นความเสี่ยงที่ *ไม่มีหน้าจอไหนในระบบนี้เตือนเลย* ทั้งที่พอร์ตกระจุกอยู่แล้ว.

วิธีวัด — จงใจใช้ตัวเลขล้วน ไม่ใช่ความเห็น: correlation ของ **ผลตอบแทนรายวัน** (ไม่ใช่ราคา —
ราคาสองตัวที่เทรนด์ขึ้นเหมือนกันจะได้ correlation สูงหลอกๆ ทั้งที่วันต่อวันไม่เกี่ยวกัน) คำนวณ
เองด้วย Pearson จาก closes ที่ align วันตรงกันแล้ว. ไม่เรียก LLM, ไม่ทำนายทิศทาง, ไม่ใช่สัญญาณ
ซื้อขาย — ตอบคำถามเดียวคือ 'ถ้าเรื่องเล่านั้นผิด ฉันเจ็บกี่ตัวพร้อมกัน'.

ข้อจำกัดที่ต้องพูดตรงๆ (แสดงบน UI ด้วย): correlation เป็นของอดีตและไม่เสถียร — ช่วงตลาดปกติ
มันต่ำได้ แล้วพุ่งเข้าหา 1 พร้อมกันตอนตลาดพัง ซึ่งคือตอนที่การกระจายความเสี่ยงสำคัญที่สุดพอดี
ตัวเลขนี้จึงเป็น 'พื้นล่างของความเสี่ยงกระจุก' (อย่างน้อยเท่านี้) ไม่ใช่เพดาน.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

CACHE_PATH = Path(__file__).parents[2] / "data" / "price_cache.json"   # gitignored เหมือน cache อื่น
CACHE_TTL_SEC = 12 * 3600          # ราคาปิดรายวัน — วันละครั้งพอ (กันยิง yfinance ทุก request)
HIGH_CORR = 0.7                    # เกณฑ์ 'วิ่งด้วยกัน' — ดู _pair_note() สำหรับที่มา
MIN_OVERLAP_DAYS = 30              # น้อยกว่านี้ correlation ไม่มีความหมายพอจะรายงาน
WINDOWS = {"90d": 90, "1y": 252}   # วันทำการโดยประมาณ


# ─────────────────────────────────────────────────────────────────────────────
# ราคา (yfinance + cache ดิสก์)
# ─────────────────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - raw.get("fetched_at", 0) < CACHE_TTL_SEC:
            return raw.get("closes", {})
    except Exception:
        pass
    return {}


def _save_cache(closes: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"fetched_at": time.time(), "closes": closes},
                                          ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass   # cache เขียนไม่ได้ = ช้าลง ไม่ใช่พัง


def fetch_closes(tickers: list[str], period: str = "1y") -> dict[str, dict[str, float]]:
    """{ticker: {"YYYY-MM-DD": close}} — ดึงทีละตัว (ล้มตัวไหนข้ามตัวนั้น ไม่ล้มทั้งชุด)."""
    import yfinance as yf

    cached = _load_cache()
    out: dict[str, dict[str, float]] = {}
    missing = []
    for t in tickers:
        if t in cached:
            out[t] = cached[t]
        else:
            missing.append(t)

    for t in missing:
        try:
            hist = yf.Ticker(t).history(period=period, auto_adjust=True)
            closes = hist["Close"].dropna()
            out[t] = {d.strftime("%Y-%m-%d"): float(v) for d, v in closes.items()}
        except Exception as e:
            print(f"[correlation] {t}: ดึงราคาไม่ได้ - {e}")
            out[t] = {}
    if missing:
        _save_cache(out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# คณิตศาสตร์ (pure — เทสต์ออฟไลน์ได้ทั้งหมด)
# ─────────────────────────────────────────────────────────────────────────────
def daily_returns(closes: dict[str, float]) -> dict[str, float]:
    """{date: close} -> {date: ผลตอบแทนวันนั้น} (ใช้ผลตอบแทน ไม่ใช่ราคา — ดู docstring บนสุด)."""
    days = sorted(closes)
    out = {}
    for prev, cur in zip(days, days[1:]):
        p = closes[prev]
        if p:
            out[cur] = closes[cur] / p - 1.0
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None          # ตัวใดตัวหนึ่งนิ่งสนิท -> correlation ไม่นิยาม (ไม่ใช่ 0)
    return cov / (vx * vy) ** 0.5


def correlate(ret_a: dict[str, float], ret_b: dict[str, float], window: int) -> tuple[float | None, int]:
    """correlation ของวันที่ 'ทั้งคู่มีข้อมูลตรงกัน' N วันหลังสุด -> (corr, จำนวนวันที่ใช้จริง)."""
    shared = sorted(set(ret_a) & set(ret_b))[-window:]
    if len(shared) < MIN_OVERLAP_DAYS:
        return None, len(shared)
    return pearson([ret_a[d] for d in shared], [ret_b[d] for d in shared]), len(shared)


def _pair_note(corr: float) -> str:
    if corr >= 0.85:
        return "แทบเป็นตัวเดียวกัน — ถือทั้งคู่ ≈ ถือตัวเดียวหนักขึ้นเท่าตัว"
    if corr >= HIGH_CORR:
        return "วิ่งไปด้วยกันเป็นส่วนใหญ่ — กระจายความเสี่ยงได้น้อยกว่าที่คิด"
    if corr >= 0.4:
        return "ไปด้วยกันบ้าง"
    if corr <= -0.3:
        return "สวนทางกัน — ช่วยถ่วงกันได้จริง"
    return "ค่อนข้างอิสระต่อกัน"


# ─────────────────────────────────────────────────────────────────────────────
# ประกอบผลลัพธ์
# ─────────────────────────────────────────────────────────────────────────────
def analyze(closes_by_ticker: dict[str, dict[str, float]],
            weights: dict[str, float] | None = None) -> dict:
    """closes_by_ticker = {ticker: {date: close}} (ฉีดได้ -> เทสต์ไม่ต้องแตะ network).
    weights = สัดส่วนในพอร์ตของตัวที่ 'ถืออยู่จริง' (%) ไว้บอกว่าคู่ที่วิ่งด้วยกันกินพอร์ตรวมเท่าไหร่.
    """
    weights = weights or {}
    rets = {t: daily_returns(c) for t, c in closes_by_ticker.items() if len(c) >= 2}
    tickers = sorted(rets)

    pairs = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            row = {"a": a, "b": b, "corr": {}, "days": {}}
            for name, win in WINDOWS.items():
                corr, days = correlate(rets[a], rets[b], win)
                row["corr"][name] = None if corr is None else round(corr, 2)
                row["days"][name] = days
            primary = row["corr"]["90d"] if row["corr"]["90d"] is not None else row["corr"]["1y"]
            if primary is None:
                continue
            row["primary"] = primary
            row["note"] = _pair_note(primary)
            row["high"] = primary >= HIGH_CORR
            # เตือนแรงเป็นพิเศษเมื่อ 'ทั้งคู่ถืออยู่จริง' — ไม่ใช่แค่จับตา
            row["both_held"] = a in weights and b in weights
            row["combined_weight"] = round(weights.get(a, 0.0) + weights.get(b, 0.0), 1) if row["both_held"] else None
            pairs.append(row)

    pairs.sort(key=lambda r: r["primary"], reverse=True)
    high = [p for p in pairs if p["high"]]
    held_high = [p for p in high if p["both_held"]]
    return {
        "tickers": tickers,
        "pairs": pairs,
        "high_pairs": high,
        "summary": {
            "n_tickers": len(tickers),
            "n_pairs": len(pairs),
            "n_high": len(high),
            "n_high_held": len(held_high),
            "threshold": HIGH_CORR,
            # พอร์ตจริงที่ตกอยู่ในคู่ที่วิ่งด้วยกัน (นับน้ำหนักไม่ซ้ำตัว)
            "held_weight_in_high": round(
                sum(weights.get(t, 0.0) for t in {x for p in held_high for x in (p["a"], p["b"])}), 1),
        },
        "caveat": ("correlation เป็นของอดีตและไม่เสถียร — ตอนตลาดพังมันมักพุ่งเข้าหา 1 พร้อมกัน "
                   "ซึ่งคือตอนที่การกระจายความเสี่ยงสำคัญที่สุด ตัวเลขนี้จึงเป็นพื้นล่างของความเสี่ยง "
                   "กระจุก ไม่ใช่เพดาน"),
    }


def portfolio_correlation(extra: list[str] | None = None) -> dict:
    """ประกอบจากของจริง: watchlist (ไม่รวมที่แช่แข็ง) + น้ำหนักพอร์ตของตัวที่ถืออยู่.
    extra = ticker นอก watchlist ที่อยากลองใส่เปรียบเทียบ (เช่น TSM/ASML ที่ยังไม่ได้เพิ่ม)."""
    from src.watchlist.store import list_all
    from src.agent.performance import portfolio_edge

    rows = [r for r in list_all() if r["status"] != "frozen"]
    tickers = [r["ticker"] for r in rows if r["asset_type"] == "stock"]
    for t in (extra or []):
        if t.upper() not in tickers:
            tickers.append(t.upper())

    weights = {}
    try:
        for pos in portfolio_edge().get("positions", []):
            if pos.get("weight") is not None:
                weights[pos["ticker"]] = pos["weight"]
    except Exception as e:
        print(f"[correlation] อ่านน้ำหนักพอร์ตไม่ได้ - {e}")

    result = analyze(fetch_closes(tickers), weights)
    result["weights"] = weights
    return result


if __name__ == "__main__":
    # python -m src.agent.correlation [TICKER ...]   (ticker เพิ่มเติมนอก watchlist)
    import sys

    data = portfolio_correlation(sys.argv[1:])
    s = data["summary"]
    print(f"=== ถือเดิมพันเดียวกันกี่ชั้น: {s['n_tickers']} ตัว, {s['n_high']}/{s['n_pairs']} คู่ที่ corr >= {s['threshold']} ===\n")
    for p in data["pairs"][:15]:
        flag = "⚠ " if p["high"] else "  "
        print(f"{flag}{p['a']:6} ~ {p['b']:6} 90d={p['corr']['90d']}  1y={p['corr']['1y']}  {p['note']}")
    print(f"\n{data['caveat']}")
