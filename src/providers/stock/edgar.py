"""SEC EDGAR 8-K client — 'material events' ที่บริษัทถูกกฎหมายบังคับให้เปิดเผย.

ทำไมใช้ 8-K ไม่ใช่ข่าว aggregator: 8-K = เหตุการณ์สำคัญจริง (เปลี่ยน CEO, M&A,
งบผิดต้องแก้, เสี่ยง delisting ฯลฯ) ที่ต้องยื่นภายใน ~4 วันทำการ — signal สูง, noise ต่ำ,
ฟรี, ตรงกับปรัชญา 'daily news = noise' ของโปรเจกต์ (เราสนแค่สิ่งที่กระทบ thesis).

EDGAR บังคับส่ง User-Agent ที่มีช่องทางติดต่อ (email) ไม่งั้น 403 — ตั้งผ่าน env
SEC_USER_AGENT ได้ ไม่งั้นใช้ค่า default. ไม่ต้องมี API key.
"""
import json
import os
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from src.domain.interfaces import NewsItem

_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_CACHE = Path(__file__).parents[3] / "data" / "sec_cik_map.json"
_CACHE_TTL = 30 * 24 * 3600  # รายชื่อ CIK เปลี่ยนช้ามาก — cache 30 วันพอ

# 8-K item code -> หมวดเหตุการณ์ (ไทย). ชุด HIGH = signal สูงพอจะกระทบ thesis จริง
# (ตัด 9.01 'เอกสารแนบ' / 7.01 'Reg FD' ที่มักเป็น noise ออกจาก high)
ITEM_MAP = {
    "1.01": "เข้าทำสัญญาสำคัญ",
    "1.02": "ยกเลิกสัญญาสำคัญ",
    "1.03": "ล้มละลาย / พิทักษ์ทรัพย์",
    "2.01": "ซื้อ/ขายสินทรัพย์ (M&A)",
    "2.02": "ผลประกอบการ (earnings)",
    "2.03": "ก่อหนี้ก้อนใหญ่",
    "2.04": "ถูกเร่งชำระหนี้",
    "2.05": "แผนปรับโครงสร้าง (เลิกจ้าง/ปิดสายงาน)",
    "2.06": "ด้อยค่าสินทรัพย์ (write-off)",
    "3.01": "เสี่ยงถูกเพิกถอนจากตลาด (delisting)",
    "4.01": "เปลี่ยนผู้สอบบัญชี",
    "4.02": "งบเก่าเชื่อถือไม่ได้ ต้องแก้ (restatement)",
    "5.01": "เปลี่ยนการควบคุมบริษัท",
    "5.02": "เปลี่ยนกรรมการ/ผู้บริหาร (CEO/CFO)",
    "5.03": "แก้ข้อบังคับบริษัท",
    "7.01": "Regulation FD disclosure",
    "8.01": "เหตุการณ์อื่น",
    "9.01": "งบการเงิน/เอกสารแนบ",
}
HIGH_SIGNAL = {"1.01", "1.02", "1.03", "2.01", "2.02", "2.05", "2.06",
               "3.01", "4.01", "4.02", "5.01", "5.02"}


def _headers() -> dict:
    # ไม่ขอ gzip: urllib ไม่ decompress ให้เอง จะทำให้ json.loads พัง (เจอบั๊กนี้มาแล้ว)
    ua = os.getenv("SEC_USER_AGENT") or "trade-finance-agent/1.0 research prinya44497@gmail.com"
    return {"User-Agent": ua}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_cik_map() -> dict[str, str]:
    """ticker (upper) -> CIK 10 หลัก. cache ลงดิสก์ (รายชื่อ ~1MB, เปลี่ยนช้า)."""
    if _CACHE.exists() and (time.time() - _CACHE.stat().st_mtime) < _CACHE_TTL:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    raw = _get_json(_CIK_URL)  # {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    mapping = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in raw.values()}
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(mapping), encoding="utf-8")
    return mapping


def ticker_to_cik(ticker: str) -> str | None:
    try:
        return _load_cik_map().get(ticker.upper())
    except Exception:
        return None


def _filing_url(cik: str, accession: str, doc: str) -> str:
    accn = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{doc}"


def _category(items_field: str) -> tuple[str, bool]:
    """'2.02,9.01' -> ('ผลประกอบการ (earnings) · งบการเงิน/เอกสารแนบ', is_high)."""
    codes = [c.strip() for c in items_field.replace(" ", ",").split(",") if c.strip()]
    labels = [ITEM_MAP.get(c, f"Item {c}") for c in codes]
    is_high = any(c in HIGH_SIGNAL for c in codes)
    return " · ".join(labels) if labels else "8-K", is_high


def recent_8k(ticker: str, limit: int = 5, high_only: bool = True, days: int = 120) -> list[NewsItem]:
    """8-K ล่าสุดของ ticker เป็น NewsItem (material=True, category=หมวดเหตุการณ์).
    high_only=True: เอาเฉพาะ item ที่ signal สูงพอ (ตัด 8-K ที่มีแต่เอกสารแนบ).
    days: เอาเฉพาะที่ยื่นภายใน N วัน — 8-K เก่าไม่ใช่ 'ข่าว' แล้ว (กัน earnings หลายไตรมาสซ้ำ).
    คืน [] เงียบๆ ถ้า EDGAR ล่ม/ไม่พบ CIK — ให้ provider หลัก fallback ได้."""
    cik = ticker_to_cik(ticker)
    if cik is None:
        return []
    try:
        data = _get_json(_SUBMISSIONS.format(cik=cik))
    except Exception:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    items = recent.get("items", [])
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    out: list[NewsItem] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        filed = dates[i] if i < len(dates) else ""
        if filed < cutoff:  # ISO date เทียบสตริงได้ตรงๆ; filings เรียงใหม่ก่อน -> เจอเก่าก็หยุดได้
            break
        items_field = items[i] if i < len(items) else ""
        category, is_high = _category(items_field)
        if high_only and not is_high:
            continue
        out.append(
            NewsItem(
                title=f"8-K ({filed}): {category}",
                url=_filing_url(cik, accns[i], docs[i]) if i < len(docs) else "",
                published_at=filed,
                source="SEC EDGAR",
                category=category,
                material=True,
            )
        )
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    # python -m src.providers.stock.edgar AAPL   -> 8-K material ล่าสุด
    import sys

    t = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    cik = ticker_to_cik(t)
    print(f"{t}  CIK={cik}\n")
    for n in recent_8k(t, limit=8):
        print(f"  {n.published_at}  {n.category}")
        print(f"     {n.url}")