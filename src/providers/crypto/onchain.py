"""ข้อมูล on-chain ของ Bitcoin จาก blockchain.info (ฟรี ไม่ต้องมี API key) — Phase 33.5.

ทำไมถึงจำเป็น: CRYPTO_FRAMEWORK ใน summarize.py สั่งให้ประเมิน 'การใช้งานจริง/adoption' และ
'ความเสี่ยงด้านความปลอดภัย' มาตั้งแต่ Phase 9 — แต่ DATA ที่ส่งไปให้มีแค่ tokenomics จาก
yfinance (supply/เพดาน/สภาพคล่อง) ไม่มีตัวเลขการใช้งานเลยสักตัว. โมเดลจึงถูกสั่งให้ตอบคำถามที่
ไม่มีข้อมูลให้ตอบ ซึ่งเป็นสูตรของการเดาที่ฟังดูดี — บทเรียนเดียวกับ Phase 33.1 (อะไรคำนวณได้
ให้คำนวณแล้ววางเป็นบรรทัดใน DATA แทนที่จะหวังให้ LLM รู้เอง)

**รองรับ Bitcoin อย่างเดียวโดยตั้งใจ** — blockchain.info เป็น API ของเชน BTC เท่านั้น. เหรียญอื่น
คืน {} แล้วปล่อยให้ไม่มี fact กลุ่มนี้ ดีกว่าไปหา endpoint ของแต่ละเชนมาต่อแบบหลวมๆ แล้วได้
ตัวเลขที่นิยามไม่ตรงกันมากองรวมกันภายใต้ป้ายเดียว (เช่น 'active addresses' ของ BTC กับของเชน
account-based นับคนละอย่าง)
"""
import json
import time
import urllib.request
from pathlib import Path

_CHARTS = "https://api.blockchain.info/charts/{chart}?timespan={span}&format=json"
_CACHE_DIR = Path(__file__).parents[3] / "data" / "onchain_cache"
_CACHE_TTL = 24 * 3600          # ตัวเลข on-chain ขยับรายวัน — cache 1 วันพอ
_TIMEOUT = 15
_SPAN = "1year"                 # ต้องยาวพอจะดูแนวโน้ม ไม่ใช่ค่าวันเดียว

SUPPORTED = {"BTC"}

# chart ที่ดึง: (ชื่อ chart ของ blockchain.info, ป้ายที่ใช้ในระบบ, หน่วย)
_CHARTS_WANTED = [
    ("n-unique-addresses", "Active Addresses", "addresses"),
    ("n-transactions", "Transactions / Day", "tx"),
    ("transaction-fees", "Transaction Fees", "BTC"),
    ("hash-rate", "Hash Rate", "TH/s"),
]


def _cache_path(chart: str) -> Path:
    return _CACHE_DIR / f"{chart}.json"


def _fetch_chart(chart: str) -> list[dict]:
    """คืน [{'x': epoch, 'y': value}, ...] — [] ถ้าดึงไม่ได้ (ไม่ raise: on-chain ล่มต้องไม่ล้ม
    รอบวิเคราะห์ทั้งรอบ หลักเดียวกับข่าว/EDGAR ที่ห่อ try ไว้ใน loop.py)."""
    path = _cache_path(chart)
    if path.exists() and (time.time() - path.stat().st_mtime) < _CACHE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("values", [])
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            _CHARTS.format(chart=chart, span=_SPAN),
            headers={"User-Agent": "investment-research-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data.get("values", [])


def _average(values: list[dict], count: int) -> float | None:
    """ค่าเฉลี่ย N จุดล่าสุด — ตัวเลข on-chain แกว่งรายวันแรงมาก (วันหยุด/ค่าธรรมเนียมพุ่ง)
    ค่าวันเดียวจึงเป็น noise ล้วน ไม่ใช่ระดับของเครือข่าย."""
    tail = [v["y"] for v in values[-count:] if v.get("y") is not None]
    return sum(tail) / len(tail) if tail else None


def get_onchain_metrics(ticker: str) -> dict[str, tuple[float, str]]:
    """{ป้าย: (ค่า, หน่วย)} — {} ถ้าไม่ใช่ BTC หรือดึงไม่ได้.

    ทุกตัวเป็น **ค่าเฉลี่ย 30 วันล่าสุด** คู่กับ **% เทียบ 30 วันแรกของช่วง 1 ปี** เพื่อให้เห็น
    'ระดับ' และ 'ทิศทาง' พร้อมกัน — ทิศทางคือสิ่งที่บอกว่าเครือข่ายถูกใช้มากขึ้นหรือน้อยลงจริง
    ส่วนระดับเปล่าๆ ไม่มีเกณฑ์กลางให้เทียบว่าเท่าไหร่ถึงเรียกว่าดี
    """
    if ticker.upper() not in SUPPORTED:
        return {}

    out: dict[str, tuple[float, str]] = {}
    for chart, label, unit in _CHARTS_WANTED:
        values = _fetch_chart(chart)
        if len(values) < 60:            # สั้นเกินกว่าจะเทียบต้นช่วงกับท้ายช่วงได้
            continue
        recent = _average(values, 30)
        baseline = _average(values[:30], 30)
        if recent is None:
            continue
        out[label] = (round(recent, 2), unit)
        if baseline:
            out[f"{label} YoY"] = (round((recent / baseline - 1) * 100, 2), "%")
    return out
