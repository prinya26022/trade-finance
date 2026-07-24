"""Base-rate ย้อนหลัง — "ครั้งก่อนๆ ที่ตัวเลขออกมาแบบนี้ ตลาดขยับยังไง".

หัวใจของ honesty: เราไม่ 'ทำนาย' ว่าราคาจะขึ้น/ลง. เราแค่บอก *การกระจายตัว* ของสิ่งที่
เคยเกิด — ค่าเฉลี่ย + ช่วง (min..max) + จำนวนครั้ง (n) + สัดส่วนที่ขึ้น — เพื่อให้เห็นว่า
'ความสัมพันธ์นี้มั่วแค่ไหน' ด้วยตาตัวเอง. ถ้าเหวี่ยง -5% ถึง +3% นั่นแหละคือคำตอบ: เดาไม่ได้.

ช่องว่างที่ต้องซื่อสัตย์:
- FRED CSV (ไม่มีคีย์) ให้ 'เดือนอ้างอิง' ไม่ใช่ 'วันประกาศจริง' -> เราประมาณวันประกาศด้วย
  approx_lag_days ต่อ series แล้ว *ติดธง approx=True* ให้ผู้ใช้รู้ว่าเป็นค่าประมาณ.
- ถ้ามี FRED_API_KEY -> ใช้ 'วันประกาศจริง' (approx=False) แม่นยำระดับที่คนเทรด 4h ใช้ได้.
"""
import functools
from dataclasses import dataclass
from datetime import date, timedelta

from src.macro import fred

# สินทรัพย์ที่คนเทรดสั้นสนใจปฏิกิริยา (ticker ฝั่ง yfinance)
ASSETS: dict[str, str] = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "ทองคำ": "GC=F",
    "หุ้นสหรัฐ (S&P500)": "^GSPC",
}


@dataclass(frozen=True)
class ReactionStats:
    asset: str          # ชื่อไทยของสินทรัพย์
    direction: str      # ทิศของ 'สัญญาณ' macro ที่กรอง: 'up' | 'down'
    signal_desc: str    # อธิบายว่า 'up'/'down' แปลว่าอะไรของ series นี้
    n: int              # จำนวนครั้งในอดีตที่นับได้
    mean_pct: float     # % เปลี่ยนแปลงเฉลี่ยหลังประกาศ (horizon)
    min_pct: float
    max_pct: float
    share_up: float     # สัดส่วนครั้งที่สินทรัพย์ขึ้น (0..1)
    horizon_days: int
    approx: bool        # True = ใช้วันประกาศประมาณ (ไม่มีคีย์ FRED)

    def as_text(self) -> str:
        note = " (วันประกาศ *ประมาณ* — ใส่ FRED_API_KEY เพื่อความแม่น)" if self.approx else ""
        return (
            f"{self.asset}: {self.n} ครั้งที่{self.signal_desc} "
            f"→ {self.horizon_days} วันถัดมาขยับเฉลี่ย {self.mean_pct:+.1f}% "
            f"(ช่วง {self.min_pct:+.1f}%..{self.max_pct:+.1f}%, ขึ้น {self.share_up*100:.0f}% ของครั้ง){note}"
        )


def _signal_values(key: str, obs: list) -> list[float | None]:
    """แปลง observation ดิบ -> 'สัญญาณที่เทรดเดอร์ดูจริง' ต่อ series (ยาวเท่า obs; ช่องคำนวณไม่ได้=None):
      CPI/PPI -> อัตราเงินเฟ้อ YoY (%)  |  NFP -> จำนวนงานเพิ่มสุทธิ/เดือน  |  UNRATE -> ระดับ %.
    ทิศทางจะคิดจาก 'สัญญาณเทียบครั้งก่อน' (เร่งตัว/ชะลอ) ไม่ใช่ค่าดิบเทียบเดือนก่อน (ซึ่งแทบขึ้นตลอด)."""
    vals = [o.value for o in obs]
    n = len(vals)
    sig: list[float | None] = [None] * n
    if key in ("CPI", "PPI"):
        for i in range(12, n):                       # YoY = เทียบ 12 เดือนก่อน
            if vals[i - 12]:
                sig[i] = (vals[i] - vals[i - 12]) / vals[i - 12] * 100.0
    elif key == "NFP":
        for i in range(1, n):                        # งานเพิ่มสุทธิเดือนนั้น
            sig[i] = vals[i] - vals[i - 1]
    else:                                            # UNRATE ฯลฯ: เป็นอัตราอยู่แล้ว ใช้ระดับตรงๆ
        for i in range(n):
            sig[i] = vals[i]
    return sig


@functools.lru_cache(maxsize=16)
def _price_history(yf_ticker: str):
    """ราคาปิดรายวันย้อนหลังไกลๆ (dict: date -> close). ล้มเหลว -> {}.

    cache ต่อ ticker: 1 หน้า radar เรียกซ้ำ 4 series × สินทรัพย์เดิม -> ยิง yfinance ครั้งเดียวพอ
    (แถวสุดท้ายอาจ 'ค้าง' ราคาวันนี้เล็กน้อย แต่ base-rate ใช้ประวัติศาสตร์ ไม่กระทบสถิติ)."""
    try:
        import yfinance as yf
        hist = yf.Ticker(yf_ticker).history(period="max", auto_adjust=True)
    except Exception:
        return {}
    out = {}
    for ts, row in hist["Close"].items():
        try:
            out[ts.date()] = float(row)
        except (ValueError, TypeError):
            continue
    return out


def _close_on_or_after(prices: dict, d: date, max_skip: int = 6) -> tuple[date, float] | None:
    """หาราคาปิดวันแรกที่ >= d (ข้ามเสาร์-อาทิตย์/วันหยุดได้สูงสุด max_skip วัน)."""
    for i in range(max_skip + 1):
        day = d + timedelta(days=i)
        if day in prices:
            return day, prices[day]
    return None


def _release_events(key: str) -> tuple[list[tuple[date, str]], bool]:
    """คืน ([(วันประกาศ, ทิศทาง 'up'|'down'), ...], used_real_dates).

    ทิศทาง = 'สัญญาณ' (ดู _signal_values) เร่งตัวขึ้น = 'up' / ชะลอลง = 'down'.
    วันประกาศ: ใช้ของจริงถ้ามีคีย์ FRED และ align ได้, ไม่งั้นประมาณ = เดือนอ้างอิง + approx_lag_days.
    used_real_dates บอกว่าใช้วันจริงหรือไม่ — เพื่อ 'ติดธง approx' ให้ตรงความจริง.
    """
    obs = fred.fetch_series(key)
    if len(obs) < 2:
        return [], False
    sig = _signal_values(key, obs)
    real_dates = fred.release_dates(key)  # None ถ้าไม่มีคีย์
    # จับคู่วันประกาศจริงกับ obs แบบ index-ต่อ-index — ใช้ได้ต่อเมื่อความยาวสอดคล้องกันจริง
    # (offset ระหว่าง release history กับ observation history ยังไม่ได้ verify กับคีย์จริง).
    # ถ้าไม่สอดคล้อง -> ถอยไปใช้ค่าประมาณที่ 'ติดธงชัด' ดีกว่าอ้างความแม่นที่ยังไม่พิสูจน์.
    if real_dates is not None and abs(len(real_dates) - len(obs)) > 3:
        real_dates = None
    lag = fred.SERIES[key].approx_lag_days

    events: list[tuple[date, str]] = []
    for i in range(1, len(obs)):
        if sig[i] is None or sig[i - 1] is None or sig[i] == sig[i - 1]:
            continue  # คำนวณสัญญาณไม่ได้ หรือนิ่งสนิท (ไม่มีทิศ)
        direction = "up" if sig[i] > sig[i - 1] else "down"
        if real_dates is not None and i < len(real_dates):
            rel = real_dates[i]
        else:
            rel = obs[i].ref_date + timedelta(days=lag)
        events.append((rel, direction))
    return events, real_dates is not None


# คำอธิบายทิศทาง 'ชะลอ/ตรงข้าม' (คู่กับ SERIES[key].up_means ที่เป็นฝั่ง 'เร่งตัว')
_DOWN_MEANS: dict[str, str] = {
    "CPI": "เงินเฟ้อชะลอลง (เย็นลง)",
    "PPI": "เงินเฟ้อผู้ผลิตชะลอลง",
    "UNRATE": "อัตราว่างงานลดลง (เศรษฐกิจแข็ง)",
    "NFP": "จ้างงานเพิ่มช้าลงกว่าเดือนก่อน",
}


def signal_desc(key: str, direction: str) -> str:
    """ข้อความอธิบายว่า 'up'/'down' ของ series นี้แปลว่าอะไร (ไว้แสดง/อธิบาย ไม่ฟันธงตลาด)."""
    return fred.SERIES[key].up_means if direction == "up" else _DOWN_MEANS.get(key, "สัญญาณชะลอลง")


@dataclass(frozen=True)
class LatestSignal:
    key: str
    ref_date: date          # เดือนอ้างอิงล่าสุด
    value: float            # ค่าดิบล่าสุด (เช่นดัชนี CPI / จำนวน NFP / % ว่างงาน)
    signal: float           # 'สัญญาณ' ล่าสุด (YoY% / งานเพิ่ม / ระดับ)
    prev_signal: float      # สัญญาณครั้งก่อน (ไว้เทียบเร่ง/ชะลอ)
    direction: str          # 'up' | 'down' | 'flat'
    desc: str               # อธิบายทิศ (เช่น 'เงินเฟ้อเร่งตัวขึ้น')


def latest_signal(key: str) -> LatestSignal | None:
    """สัญญาณล่าสุดของ series (ตัวเลขที่เพิ่งออก เร่งตัว/ชะลอเทียบครั้งก่อน). ข้อมูลไม่พอ -> None."""
    if key not in fred.SERIES:
        return None
    obs = fred.fetch_series(key)
    sig = _signal_values(key, obs)
    # หา index ล่าสุดที่มีทั้ง sig[i] และ sig[i-1]
    for i in range(len(obs) - 1, 0, -1):
        if sig[i] is not None and sig[i - 1] is not None:
            if sig[i] > sig[i - 1]:
                d = "up"
            elif sig[i] < sig[i - 1]:
                d = "down"
            else:
                d = "flat"
            return LatestSignal(
                key=key, ref_date=obs[i].ref_date, value=obs[i].value,
                signal=sig[i], prev_signal=sig[i - 1], direction=d,
                desc=signal_desc(key, d) if d != "flat" else "ทรงตัวเท่าเดือนก่อน",
            )
    return None


def reaction_stats(key: str, direction: str, horizon_days: int = 1) -> list[ReactionStats]:
    """สถิติผลตอบสนองของทุกสินทรัพย์ เมื่อ 'สัญญาณ' ของ series `key` เร่งตัว/ชะลอ.

    direction: 'up' (สัญญาณเร่งตัว) หรือ 'down' (ชะลอ). คืน [] ถ้าดึงข้อมูล macro ไม่ได้.
    """
    if key not in fred.SERIES:
        return []
    desc = signal_desc(key, direction)
    all_events, used_real = _release_events(key)
    events = [(d, dir_) for (d, dir_) in all_events if dir_ == direction]
    if not events:
        return []
    approx = not used_real

    out: list[ReactionStats] = []
    for asset_th, yf_ticker in ASSETS.items():
        prices = _price_history(yf_ticker)
        if not prices:
            continue
        changes: list[float] = []
        for rel_date, _ in events:
            before = _close_on_or_after(prices, rel_date)
            if not before:
                continue
            after = _close_on_or_after(prices, before[0] + timedelta(days=horizon_days))
            if not after or after[0] == before[0] or before[1] == 0:
                continue
            changes.append((after[1] - before[1]) / before[1] * 100.0)
        if not changes:
            continue
        out.append(ReactionStats(
            asset=asset_th,
            direction=direction,
            signal_desc=desc,
            n=len(changes),
            mean_pct=sum(changes) / len(changes),
            min_pct=min(changes),
            max_pct=max(changes),
            share_up=sum(1 for c in changes if c > 0) / len(changes),
            horizon_days=horizon_days,
            approx=approx,
        ))
    return out


if __name__ == "__main__":  # เดโมจริง (แตะเน็ต): python -m src.macro.baserate CPI up
    import sys
    k = sys.argv[1] if len(sys.argv) > 1 else "CPI"
    d = sys.argv[2] if len(sys.argv) > 2 else "up"
    s = fred.SERIES[k]
    print(f"# {s.label_th}: ครั้งที่ '{signal_desc(k, d)}' "
          f"(คีย์={'มี' if fred.has_api_key() else 'ไม่มี — ค่าประมาณ'})\n")
    for r in reaction_stats(k, d, horizon_days=1):
        print("  " + r.as_text())
