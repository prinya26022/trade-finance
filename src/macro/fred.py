"""FRED (Federal Reserve Economic Data) — ข้อมูล macro ฟรี.

โหมดพื้นฐาน (ไม่ต้องมีคีย์): ดึงผ่าน CSV endpoint สาธารณะ (fredgraph.csv) — ไม่ต้องสมัคร
ไม่เพิ่ม dependency (urllib + csv จาก stdlib). ได้ค่ารายเดือน โดย observation_date คือ
'เดือนอ้างอิง' ไม่ใช่ 'วันประกาศจริง' — CPI เดือน มิ.ย. ประกาศจริงกลาง ก.ค.
(baserate.py รับมือช่องว่างนี้ด้วยการประมาณ lag แล้ว 'ระบุชัดว่าเป็นค่าประมาณ').

โหมดแม่นยำ (ถ้ามี FRED_API_KEY ใน .env — ฟรี สมัคร 1 นาที):
release_dates() จะดึง 'วันประกาศจริง' มาให้ ทำให้ base-rate วัดผลตอบสนอง ณ วันที่ตลาด
เห็นตัวเลขจริงๆ (แม่นกว่ามาก สำหรับคนเทรด 4h). ไม่มีคีย์ก็ทำงานต่อได้ แค่เป็นค่าประมาณ.
"""
import csv
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

_UA = {"User-Agent": "trade-finance-agent/1.0 (+local research tool)"}
_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_API_URL = "https://api.stlouisfed.org/fred"

_CACHE_TTL_SEC = 600                                   # ตัวเลข macro เป็นรายเดือน 10 นาทีถือว่าสด
_CACHE: dict[str, tuple[float, list["Observation"]]] = {}


def clear_cache() -> None:
    """ล้าง cache — ใช้ในเทสต์ ไม่ให้ผลของเคสก่อนหน้าไหลข้ามมา."""
    _CACHE.clear()


@dataclass(frozen=True)
class Series:
    """metadata ของแต่ละ series ที่เราติดตาม."""
    key: str            # ชื่อสั้นที่เราใช้ภายใน ('CPI')
    fred_id: str        # id ฝั่ง FRED ('CPIAUCSL')
    label_th: str       # ชื่อไทยไว้แสดง
    unit: str           # หน่วย (%, ดัชนี, พันตำแหน่ง)
    up_means: str       # 'ค่าขึ้น' แปลว่าอะไร (ไว้อธิบายทิศทาง ไม่ใช่ฟันธงตลาด)
    approx_lag_days: int  # ประมาณกี่วันหลังเดือนอ้างอิงถึงประกาศจริง (ใช้เมื่อไม่มีคีย์)


# series ที่เทรดเดอร์จับตาบ่อยสุด (ทั้งหมดฟรีบน FRED).
# up_means / down_means อธิบาย 'สัญญาณ' ที่ baserate.py คำนวณ (ไม่ใช่ค่าดิบ):
#   CPI/PPI = อัตราเงินเฟ้อ YoY เร่งตัว/ชะลอ,  NFP = จ้างงานเพิ่มเร็วขึ้น/ช้าลง,
#   UNRATE = อัตราว่างงานสูงขึ้น/ลดลง.
SERIES: dict[str, Series] = {
    "CPI": Series("CPI", "CPIAUCSL", "เงินเฟ้อ CPI (YoY)", "%",
                  "เงินเฟ้อเร่งตัวขึ้น (ร้อนกว่าเดิม)", 43),
    "PPI": Series("PPI", "PPIACO", "เงินเฟ้อผู้ผลิต PPI (YoY)", "%",
                  "เงินเฟ้อผู้ผลิตเร่งตัวขึ้น", 45),
    "UNRATE": Series("UNRATE", "UNRATE", "อัตราว่างงาน", "%",
                     "อัตราว่างงานสูงขึ้น (เศรษฐกิจอ่อน)", 35),
    "NFP": Series("NFP", "PAYEMS", "การจ้างงานนอกภาคเกษตร (NFP)", "พันตำแหน่ง/เดือน",
                  "จ้างงานเพิ่มเร็วกว่าเดือนก่อน", 35),
}


@dataclass(frozen=True)
class Observation:
    ref_date: date      # เดือนอ้างอิง (จาก FRED CSV)
    value: float


def fetch_series(key_or_id: str) -> list[Observation]:
    """ดึงค่ารายเดือนทั้งหมดของ series (เรียงเก่า -> ใหม่). ล้มเหลว -> [] (ไม่ทำ flow อื่นพัง).

    รับได้ทั้ง key ภายใน ('CPI') และ fred_id ตรงๆ ('CPIAUCSL').

    สอง path: มี FRED_API_KEY -> ใช้ official API ก่อน (เชื่อถือได้กว่าใน CI, ดู docstring
    _fetch_series_api) ไม่มีคีย์ หรือ API พังเฉยๆ -> fallback ไปหน้า CSV สาธารณะ (ไม่ต้องมีคีย์
    แต่เจอจริงว่า timeout ทุก series พร้อมกันเวลารันจาก GitHub Actions — สงสัยว่า FRED (อยู่หลัง
    Cloudflare) throttle/บล็อก IP ของ cloud runner แบบเงียบๆ แทนที่จะ reject ตรงๆ).

    cache ในโปรเซส TTL สั้น: หน้า radar/รอบสแกนเรียกซ้ำ series เดิมหลายทาง (dashboard + status
    + baserate) — ข้อมูลเป็นรายเดือน การยิงซ้ำในไม่กี่นาทีจึงได้คำตอบเดิมเสมอ. cache เฉพาะผลที่
    ได้ข้อมูลจริง: ถ้าดึงพลาดต้องลองใหม่รอบหน้า ไม่ใช่จำความล้มเหลวไว้ทั้ง TTL
    """
    sid = SERIES[key_or_id].fred_id if key_or_id in SERIES else key_or_id
    hit = _CACHE.get(sid)
    if hit and time.time() - hit[0] < _CACHE_TTL_SEC:
        return hit[1]

    obs: list[Observation] = []
    if _api_key():
        obs = _fetch_series_api(sid)
    if not obs:
        obs = _fetch_series_csv(sid)
    if obs:
        _CACHE[sid] = (time.time(), obs)
    return obs


def _fetch_series_api(sid: str) -> list[Observation]:
    """ดึง observations ผ่าน FRED official API (ต้องมี FRED_API_KEY) — endpoint สำหรับ
    machine/programmatic access โดยเฉพาะ ต่างจาก fredgraph.csv ที่เป็นหน้าเว็บสาธารณะที่
    Cloudflare อาจ throttle traffic จาก cloud/datacenter IP (เช่น GitHub Actions runner)."""
    params = urllib.parse.urlencode({
        "series_id": sid, "api_key": _api_key(), "file_type": "json", "sort_order": "asc",
    })
    try:
        req = urllib.request.Request(f"{_API_URL}/series/observations?{params}", headers=_UA)
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    except Exception as e:
        print(f"[fred] API ดึง {sid} ล้มเหลว: {type(e).__name__}: {e} -> fallback ไป CSV")
        return []

    out: list[Observation] = []
    for o in data.get("observations", []):
        v = o.get("value")
        if v in (".", "", None):   # FRED ใช้ '.' แทนค่าที่ขาด
            continue
        try:
            out.append(Observation(datetime.strptime(o["date"], "%Y-%m-%d").date(), float(v)))
        except (ValueError, KeyError):
            continue
    return out


def _fetch_series_csv(sid: str) -> list[Observation]:
    """หน้า CSV สาธารณะ (ไม่ต้องมีคีย์) — path เดิมของโปรเจกต์, ยังเป็น fallback หลัก."""
    try:
        req = urllib.request.Request(_CSV_URL.format(sid=sid), headers=_UA)
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # เดิม swallow เงียบสนิท -> ตอน CI ดึงล้มเหลวทุก series ไม่มีทางรู้เหตุผลจาก log เลย
        # (เจอจริง: data/macro.db ไม่เคยถูกสร้างใน CI แต่ไม่มีร่องรอยว่าทำไม จนกระทั่ง print นี้
        # เผยว่าเป็น TimeoutError ทุก series พร้อมกัน) print ไว้ให้เห็นใน Action log แต่ยัง
        # return [] เหมือนเดิม (ไม่ทำ flow อื่นพัง ตามเจตนาเดิม)
        print(f"[fred] CSV ดึง {sid} ล้มเหลว: {type(e).__name__}: {e}")
        return []

    out: list[Observation] = []
    reader = csv.reader(io.StringIO(raw))
    next(reader, None)  # ข้าม header
    for row in reader:
        if len(row) < 2:
            continue
        d_str, v_str = row[0], row[1]
        if v_str in (".", ""):   # FRED ใช้ '.' แทนค่าที่ขาด
            continue
        try:
            out.append(Observation(datetime.strptime(d_str, "%Y-%m-%d").date(), float(v_str)))
        except ValueError:
            continue
    return out


def latest_two(key_or_id: str) -> tuple[Observation, Observation] | None:
    """คืน (ก่อนหน้า, ล่าสุด) ไว้เทียบทิศทาง; ถ้าข้อมูลไม่พอ -> None."""
    obs = fetch_series(key_or_id)
    if len(obs) < 2:
        return None
    return obs[-2], obs[-1]


def _api_key() -> str | None:
    return os.environ.get("FRED_API_KEY") or None


def has_api_key() -> bool:
    return _api_key() is not None


def release_dates(key: str) -> list[date] | None:
    """วันประกาศจริงย้อนหลังของ series (ต้องมี FRED_API_KEY). ไม่มีคีย์/ล้มเหลว -> None.

    ใช้ 2 ขั้น: หา release_id ของ series แล้วดึง release/dates ทั้งหมด.
    baserate.py จับคู่ 'วันประกาศจริง' นี้กับราคาสินทรัพย์เพื่อวัดผลตอบสนองที่แม่นยำ.
    """
    key_str = _api_key()
    if not key_str or key not in SERIES:
        return None
    sid = SERIES[key].fred_id

    def _get(path: str, **params) -> dict | None:
        params.update(api_key=key_str, file_type="json")
        qs = urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(f"{_API_URL}/{path}?{qs}", headers=_UA)
            return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
        except Exception:
            return None

    meta = _get("series/release", series_id=sid)
    if not meta or not meta.get("releases"):
        return None
    release_id = meta["releases"][0]["id"]
    dates = _get("release/dates", release_id=release_id, limit=10000,
                 sort_order="asc", include_release_dates_with_no_data="false")
    if not dates:
        return None
    out: list[date] = []
    for d in dates.get("release_dates", []):
        try:
            out.append(datetime.strptime(d["date"], "%Y-%m-%d").date())
        except (ValueError, KeyError):
            continue
    return out or None
