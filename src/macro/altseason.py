"""Alt vs BTC — ETH/BTC ratio momentum (คำนวณเอง ไม่พึ่งเว็บนอกที่พังง่าย).

'alt season' แบบที่คนพูดถึง = ETH/อัลต์แรงกว่า BTC. เราไม่ 'ทำนาย' ว่า season กำลังมา —
เราวัด**สิ่งที่เกิดจริงตอนนี้**: ratio ETH/BTC ขยับขึ้น (ETH นำ) หรือลง (BTC นำ) ในช่วง 30/90 วัน.
โปร่งใส: คำนวณจากราคา yfinance ตรงๆ อธิบายได้ทุกเลข. ล้มเหลว -> None (หน้าเว็บก็แค่ไม่โชว์บล็อกนี้).
"""
from dataclasses import dataclass
from datetime import timedelta

from src.macro.baserate import _price_history

_THRESHOLD = 5.0   # % ขยับของ ratio ที่ถือว่า 'มีทิศชัด' (ต่ำกว่านี้ = พอๆกัน)


@dataclass(frozen=True)
class AltSeason:
    eth_btc_ratio: float     # ค่า ratio ล่าสุด
    change_30d: float        # % เปลี่ยนของ ratio ใน 30 วัน (+ = ETH นำ)
    change_90d: float
    eth_30d: float           # ผลตอบแทน ETH 30 วัน (context)
    btc_30d: float           # ผลตอบแทน BTC 30 วัน
    state: str               # 'alt' | 'btc' | 'neutral'
    label: str               # อธิบายไทย (บรรยาย ไม่ฟันธงอนาคต)

    def as_dict(self) -> dict:
        return {
            "eth_btc_ratio": round(self.eth_btc_ratio, 5),
            "change_30d": round(self.change_30d, 1),
            "change_90d": round(self.change_90d, 1),
            "eth_30d": round(self.eth_30d, 1),
            "btc_30d": round(self.btc_30d, 1),
            "state": self.state,
            "label": self.label,
        }


def _pct_change_over(prices: dict, days: int) -> float | None:
    """% เปลี่ยนของ series (date->value) จาก ~`days` วันก่อน ถึงล่าสุด. ข้อมูลไม่พอ -> None."""
    if not prices:
        return None
    dates = sorted(prices)
    last = dates[-1]
    target = last - timedelta(days=days)
    past = None
    for d in dates:                      # ค่าล่าสุดที่ <= target
        if d <= target:
            past = prices[d]
        else:
            break
    if past is None or past == 0:
        return None
    return (prices[last] - past) / past * 100.0


def eth_btc_momentum() -> AltSeason | None:
    """โมเมนตัม ETH/BTC ล่าสุด. ดึงราคาไม่ได้/ข้อมูลไม่พอ -> None."""
    btc = _price_history("BTC-USD")
    eth = _price_history("ETH-USD")
    if not btc or not eth:
        return None

    common = sorted(set(btc) & set(eth))
    if len(common) < 30:
        return None
    ratio = {d: eth[d] / btc[d] for d in common if btc[d]}

    ch30 = _pct_change_over(ratio, 30)
    ch90 = _pct_change_over(ratio, 90)
    eth30 = _pct_change_over(eth, 30)
    btc30 = _pct_change_over(btc, 30)
    if ch30 is None:
        return None

    if ch30 >= _THRESHOLD:
        state, label = "alt", f"ETH กำลังนำ BTC (ratio +{ch30:.0f}% ใน 30 วัน)"
    elif ch30 <= -_THRESHOLD:
        state, label = "btc", f"BTC กำลังนำ ETH (ratio {ch30:.0f}% ใน 30 วัน)"
    else:
        state, label = "neutral", f"ETH กับ BTC ไปพอๆกัน (ratio {ch30:+.0f}% ใน 30 วัน)"

    return AltSeason(
        eth_btc_ratio=ratio[common[-1]],
        change_30d=ch30,
        change_90d=ch90 if ch90 is not None else 0.0,
        eth_30d=eth30 if eth30 is not None else 0.0,
        btc_30d=btc30 if btc30 is not None else 0.0,
        state=state,
        label=label,
    )


if __name__ == "__main__":  # เดโม (แตะเน็ต): python -m src.macro.altseason
    a = eth_btc_momentum()
    print(a.label if a else "ไม่มีข้อมูลพอ")
