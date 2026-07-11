"""Market-wide data (ไม่ผูกกับ ticker ใดตัวหนึ่ง) สำหรับ CAPM WACC ใน reverse-DCF (Phase 18).

Risk-free rate (Rf) = อัตราผลตอบแทนพันธบัตรรัฐบาลสหรัฐ 10 ปี จาก ^TNX บน yfinance — ค่าเดียว
ใช้ร่วมกันทุก ticker ในรอบวันเดียวกัน (ไม่ใช่เมตริกเฉพาะบริษัท) จึง cache แยกจาก per-ticker
cache (sec_facts_cache/) เป็นไฟล์เดียว TTL 1 วัน กันยิงซ้ำทุกครั้งที่วิเคราะห์แต่ละ ticker.

หมายเหตุสเกล: ตรวจสอบสดแล้วว่า yfinance คืนค่า ^TNX.history()['Close'] เป็น 'ตัวเลข %
ตรงๆ' (เช่น 4.57 = 4.57%) ไม่ใช่สเกล x10 แบบที่บางแหล่งอ้างถึงการแสดงผลบนกราฟ — เทียบกับตัวเลข
yield จริงที่ Yahoo Finance รายงาน ณ เวลาตรวจสอบตรงกันเป๊ะ จึงไม่ต้องหาร 10.
"""
import json
import time
from pathlib import Path

import yfinance as yf

_CACHE_PATH = Path(__file__).parents[3] / "data" / "risk_free_rate_cache.json"
_CACHE_TTL = 24 * 3600

# ใช้ตอนดึง ^TNX ไม่ได้เลย (เครือข่ายล่ม ฯลฯ) — ประมาณการเฉลี่ยระยะยาวคร่าวๆ กัน WACC
# คำนวณไม่ได้เลย ดีกว่าทำ pipeline พังทั้งกระบวน
_FALLBACK_RF_PCT = 4.0


def get_risk_free_rate_pct() -> float:
    """คืนอัตราผลตอบแทนพันธบัตรรัฐบาล 10 ปีล่าสุด (%) — cache ดิสก์ 1 วัน. ไม่โยน exception
    เลย (fallback ค่าคงที่ถ้าดึงไม่ได้) เพราะ WACC/reverse-DCF ต้องคำนวณต่อได้เสมอ."""
    if _CACHE_PATH.exists() and (time.time() - _CACHE_PATH.stat().st_mtime) < _CACHE_TTL:
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))["rf_pct"]
        except Exception:
            pass   # cache เสีย -> ดึงใหม่

    try:
        hist = yf.Ticker("^TNX").history(period="5d")
        rf_pct = float(hist["Close"].iloc[-1])
    except Exception:
        return _FALLBACK_RF_PCT

    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps({"rf_pct": rf_pct, "fetched_at": time.time()}), encoding="utf-8")
    return rf_pct


if __name__ == "__main__":
    # python -m src.providers.stock.market
    print(f"Risk-free rate (10yr treasury): {get_risk_free_rate_pct():.3f}%")