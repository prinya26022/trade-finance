"""ดึงข้อมูลดิบ — **ที่เดียวในแพ็กเกจนี้ที่แตะเน็ต** เพื่อให้ signals.py เป็นฟังก์ชันบริสุทธิ์
ที่เทสต์ได้ออฟไลน์ทั้งหมด (บทเรียนเดียวกับ src/macro/fred.py แยกจาก baserate.py)

คืน None เมื่อดึงไม่ได้ — **ไม่เดาค่า ไม่ใช้ค่าเก่าแทนแล้วเงียบ** (บทเรียน Phase 45 เรื่อง FX:
ตัวเลขที่ผิดแบบดูน่าเชื่อ แย่กว่าไม่มีตัวเลข) ปลายทางจะรายงานว่า 'ดึงไม่ได้' ตรงๆ
"""
import json
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path(__file__).parents[2] / "data" / "aicapex_cache.json"
CACHE_TTL_SECONDS = 6 * 3600   # ราคาระหว่างวันไม่ใช่ประเด็นของเรดาร์นี้ — 6 ชม. พอ และประหยัดโควตา


@dataclass
class TickerData:
    """ข้อมูลดิบต่อ ticker. ทุก field เป็น None ได้หมด — ข้อมูลขาดคือสภาพปกติของ yfinance
    ไม่ใช่กรณียกเว้น และ signals ต้องรับมือได้โดยไม่ระเบิด"""
    ticker: str
    price: float | None = None
    # (วันที่ ISO, ราคาปิด) เรียงเก่า -> ใหม่
    closes: list[tuple[str, float]] = field(default_factory=list)
    # งบกระแสเงินสดรายไตรมาส เรียงใหม่ -> เก่า (ล่าสุดอยู่ index 0)
    fcf_q: list[float | None] = field(default_factory=list)
    capex_q: list[float | None] = field(default_factory=list)
    ocf_q: list[float | None] = field(default_factory=list)
    da_q: list[float | None] = field(default_factory=list)
    quarter_ends: list[str] = field(default_factory=list)
    # งบดุลรายไตรมาส เรียงใหม่ -> เก่า
    total_debt_q: list[float | None] = field(default_factory=list)
    equity_q: list[float | None] = field(default_factory=list)


def _clean(v) -> float | None:
    """NaN/NaT/None ของ pandas -> None. ค่าที่ไม่ใช่ตัวเลขห้ามหลุดเข้าไปถึง signals."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f      # f != f จริงเมื่อ f เป็น NaN


def _row(df, names: tuple[str, ...], n: int) -> list[float | None]:
    """แถวแรกที่ชื่อตรงกับ names (yfinance เปลี่ยนชื่อแถวเองบ่อย จึงต้องลองหลายชื่อ)."""
    if df is None or getattr(df, "empty", True):
        return []
    for name in names:
        if name in df.index:
            return [_clean(df.loc[name, c]) for c in list(df.columns)[:n]]
    return []


def fetch_ticker(ticker: str, quarters: int = 5, history_days: int = 400) -> TickerData:
    """ดึงข้อมูลของ ticker เดียว — ล้มเหลวบางส่วนไม่ทำให้ทั้งตัวพัง (คืน field ที่ได้เท่าที่ได้)."""
    import yfinance as yf

    out = TickerData(ticker=ticker)
    tk = yf.Ticker(ticker)

    try:
        hist = tk.history(period=f"{history_days}d", auto_adjust=True)
        if hist is not None and not hist.empty:
            out.closes = [(str(idx)[:10], float(v)) for idx, v in hist["Close"].items()
                          if _clean(v) is not None]
            if out.closes:
                out.price = out.closes[-1][1]
    except Exception as e:
        print(f"[aicapex] {ticker}: history ล้มเหลว — {type(e).__name__}")

    try:
        cf = tk.quarterly_cashflow
        if cf is not None and not cf.empty:
            out.quarter_ends = [str(c)[:10] for c in list(cf.columns)[:quarters]]
            out.fcf_q = _row(cf, ("Free Cash Flow",), quarters)
            out.capex_q = _row(cf, ("Capital Expenditure", "Capital Expenditures"), quarters)
            out.ocf_q = _row(cf, ("Operating Cash Flow",), quarters)
            out.da_q = _row(cf, ("Depreciation Amortization Depletion",
                                 "Depreciation And Amortization", "Depreciation"), quarters)
    except Exception as e:
        print(f"[aicapex] {ticker}: cashflow ล้มเหลว — {type(e).__name__}")

    try:
        bs = tk.quarterly_balance_sheet
        if bs is not None and not bs.empty:
            out.total_debt_q = _row(bs, ("Total Debt",), quarters)
            out.equity_q = _row(bs, ("Stockholders Equity", "Total Stockholder Equity"), quarters)
    except Exception as e:
        print(f"[aicapex] {ticker}: balance sheet ล้มเหลว — {type(e).__name__}")

    return out


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch_all(tickers: list[str], use_cache: bool = True) -> dict[str, TickerData]:
    """ดึงทุกตัว พร้อม cache ดิสก์ (เหมือน providers/stock/fx.py) — workflow รันวันละครั้ง
    แต่รันมือทดสอบซ้ำๆ ได้โดยไม่โดน rate-limit"""
    warnings.filterwarnings("ignore")
    cache = _load_cache() if use_cache else {}
    fresh_enough = (
        use_cache
        and cache.get("fetched_at_epoch")
        and (time.time() - cache["fetched_at_epoch"]) < CACHE_TTL_SECONDS
        and set(cache.get("data", {})) >= set(tickers)
    )
    if fresh_enough:
        return {t: TickerData(**cache["data"][t]) for t in tickers}

    out: dict[str, TickerData] = {}
    for t in tickers:
        out[t] = fetch_ticker(t)

    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetched_at_epoch": time.time(),
            "data": {t: asdict(d) for t, d in out.items()},
        }, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"[aicapex] เขียน cache ไม่ได้ — {type(e).__name__} (ไม่กระทบผลลัพธ์)")
    return out
