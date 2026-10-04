"""OKX v5 REST — **ที่เดียวในแพ็กเกจที่แตะเน็ตและ key** (อ่านอย่างเดียว).

ใช้แค่ GET: ประวัติ position ที่ปิดแล้ว, position ที่เปิดอยู่, คำสั่ง TP/SL ที่ตั้งไว้, ยอดพอร์ต และ
ขนาดสัญญา (public). ไม่มีฟังก์ชันไหนในไฟล์นี้ส่งคำสั่งซื้อขาย และไม่ควรมีวันไหนมี

key อ่านจาก .env: OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE — ผู้ใช้สร้างใน OKX แบบ
Read only แล้วใส่เอง. ไม่มี key = ข้ามเงียบๆ (ส่วนอื่นของโปรเจกต์ทำงานต่อได้)

ตัวแปลงข้อมูล (parse_*) แยกเป็นฟังก์ชันบริสุทธิ์ เทสต์ด้วยตัวอย่างรูปแบบตามเอกสาร OKX ได้โดยไม่ต้อง
มีบัญชีจริง — ส่วนที่เทสต์ออฟไลน์ไม่ได้คือ "OKX ตอบตามเอกสารจริงไหม" ซึ่งต้องรันกับ key จริงครั้งแรก
"""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

INST = "BTC-USDT-SWAP"
DEFAULT_CT_VAL = 0.01          # BTC-USDT-SWAP: 1 สัญญา = 0.01 BTC (ยืนยันด้วย public instruments ตอนรัน)


class OkxError(RuntimeError):
    pass


@dataclass(frozen=True)
class Creds:
    key: str
    secret: str
    passphrase: str


def credentials() -> Creds | None:
    k, s, p = (os.environ.get(n, "").strip() for n in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"))
    return Creds(k, s, p) if k and s and p else None


def base_url() -> str:
    return os.environ.get("OKX_API_BASE", "https://www.okx.com").rstrip("/")


def sign(secret: str, ts: str, method: str, path: str, body: str = "") -> str:
    """ลายเซ็นตามเอกสาร OKX: base64(HMAC-SHA256(secret, timestamp + METHOD + path?query + body))"""
    mac = hmac.new(secret.encode(), f"{ts}{method.upper()}{path}{body}".encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def _timestamp(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _get(path: str, params: dict | None = None, creds: Creds | None = None) -> list[dict]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    full = path + query
    headers = {"User-Agent": "trade-finance-journal/1.0", "Content-Type": "application/json"}
    if creds is not None:
        ts = _timestamp()
        headers.update({"OK-ACCESS-KEY": creds.key, "OK-ACCESS-SIGN": sign(creds.secret, ts, "GET", full),
                        "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": creds.passphrase})
    req = urllib.request.Request(base_url() + full, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise OkxError(f"HTTP {e.code} {path}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise OkxError(f"ต่อ OKX ไม่ได้ ({path}): {e.reason}") from e
    if str(body.get("code")) != "0":
        # ข้อความจาก OKX บอกตรงๆ ว่าผิดที่ key/สิทธิ์/IP — ส่งต่อให้ผู้ใช้เห็น ไม่กลืน
        raise OkxError(f"OKX ตอบ code {body.get('code')}: {body.get('msg')} ({path})")
    return body.get("data") or []


# ---------- ตัวแปลง (บริสุทธิ์) ----------

def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _ms(x) -> datetime | None:
    v = _f(x)
    return datetime.fromtimestamp(v / 1000, timezone.utc).replace(tzinfo=None) if v else None


def _direction(row: dict) -> str:
    """long/short — โหมด long/short ใช้ posSide, โหมด net ใช้เครื่องหมายของ pos"""
    if row.get("direction") in ("long", "short"):
        return row["direction"]
    if row.get("posSide") in ("long", "short"):
        return row["posSide"]
    return "long" if (_f(row.get("pos")) or 0) >= 0 else "short"


def trade_key(row: dict) -> str:
    """posId อย่างเดียวไม่พอ: OKX ใช้ posId เดิมซ้ำเมื่อเปิดใหม่ทางเดิม — เวลาเปิด (cTime) คือ
    สิ่งที่แยก 'ไม้นี้' ออกจาก 'ไม้ก่อน' และเหมือนกันทั้งตอนเปิดอยู่และตอนปิดแล้ว"""
    return f"okx:{row.get('posId')}:{row.get('cTime')}"


def parse_open(row: dict) -> dict:
    return {"key": trade_key(row), "source": "okx", "inst": row.get("instId"), "side": _direction(row),
            "status": "open", "opened_at": _ms(row.get("cTime")), "entry": _f(row.get("avgPx")),
            "contracts": abs(_f(row.get("pos")) or 0), "lever": _f(row.get("lever")),
            "margin": _f(row.get("margin")) or _f(row.get("imr"))}


def parse_closed(row: dict) -> dict:
    return {"key": trade_key(row), "source": "okx", "inst": row.get("instId"), "side": _direction(row),
            "status": "closed", "opened_at": _ms(row.get("cTime")), "closed_at": _ms(row.get("uTime")),
            "entry": _f(row.get("openAvgPx")), "exit": _f(row.get("closeAvgPx")),
            "contracts": _f(row.get("closeTotalPos")) or _f(row.get("openMaxPos")),
            "lever": _f(row.get("lever")),
            # realizedPnl = pnl + ค่าธรรมเนียม + funding — เงินที่เข้า/ออกพอร์ตจริง
            "pnl": _f(row.get("realizedPnl")) if row.get("realizedPnl") not in (None, "") else _f(row.get("pnl")),
            "fee": _f(row.get("fee")), "liquidated": str(row.get("type")) in ("3", "4")}


def parse_algos(rows: list[dict]) -> dict[str, dict]:
    """คำสั่ง TP/SL ที่ค้างอยู่ -> {"long"/"short": {"sl":..., "tp":...}}.
    คำสั่งปิด long คือฝั่ง sell — โหมด net ไม่มี posSide จึงต้องดูจาก side"""
    out: dict[str, dict] = {}
    for r in rows:
        side = r.get("posSide") if r.get("posSide") in ("long", "short") else (
            "long" if r.get("side") == "sell" else "short")
        cur = out.setdefault(side, {"sl": None, "tp": None})
        cur["sl"] = cur["sl"] or _f(r.get("slTriggerPx"))
        cur["tp"] = cur["tp"] or _f(r.get("tpTriggerPx"))
    return out


def _closes_side(order_side: str) -> str:
    """คำสั่งฝั่ง sell ปิด long / buy ปิด short (โหมด net ไม่มี posSide)"""
    return "long" if order_side == "sell" else "short"


def parse_entry_orders(rows: list[dict]) -> list[dict]:
    """คำสั่งเปิดไม้ที่แนบ stop/TP มาด้วย = stop ตัวแรกจริง ณ ตอนกดเข้า.
    เวลาใช้ uTime (ตอนจับคู่สำเร็จ) ไม่ใช่ cTime — limit order วางไว้ก่อนแล้วค่อยจับคู่ทีหลังได้"""
    out = []
    for r in rows:
        if str(r.get("reduceOnly")).lower() == "true" or r.get("state") not in ("filled", "partially_filled"):
            continue
        att = r.get("attachAlgoOrds") or []
        sl = next((_f(a.get("slTriggerPx")) for a in att if _f(a.get("slTriggerPx"))), None) or _f(r.get("slTriggerPx"))
        tp = next((_f(a.get("tpTriggerPx")) for a in att if _f(a.get("tpTriggerPx"))), None) or _f(r.get("tpTriggerPx"))
        if sl or tp:
            side = r["posSide"] if r.get("posSide") in ("long", "short") else (
                "long" if r.get("side") == "buy" else "short")
            out.append({"ts": _ms(r.get("uTime")) or _ms(r.get("cTime")), "side": side, "sl": sl, "tp": tp})
    return out


def parse_algo_history(rows: list[dict]) -> list[dict]:
    """คำสั่ง stop/TP ที่ตั้งแยกหลังเข้าไม้ (ทั้งที่ทำงานแล้วและที่ยกเลิก)"""
    out = []
    for r in rows:
        side = r["posSide"] if r.get("posSide") in ("long", "short") else _closes_side(r.get("side"))
        sl, tp = _f(r.get("slTriggerPx")), _f(r.get("tpTriggerPx"))
        if sl or tp:
            out.append({"ts": _ms(r.get("cTime")), "side": side, "sl": sl, "tp": tp})
    return out


# ---------- เรียกจริง ----------

class Client:
    def __init__(self, creds: Creds):
        self.creds = creds

    def closed_positions(self, inst: str = INST) -> list[dict]:
        rows = _get("/api/v5/account/positions-history", {"instType": "SWAP", "instId": inst, "limit": "100"},
                    self.creds)
        return [parse_closed(r) for r in rows]

    def open_positions(self, inst: str = INST) -> list[dict]:
        rows = _get("/api/v5/account/positions", {"instType": "SWAP", "instId": inst}, self.creds)
        return [parse_open(r) for r in rows if (_f(r.get("pos")) or 0) != 0]

    def stops(self, inst: str = INST) -> dict[str, dict]:
        rows = []
        for kind in ("conditional", "oco"):
            rows += _get("/api/v5/trade/orders-algo-pending", {"ordType": kind, "instType": "SWAP", "instId": inst},
                         self.creds)
        return parse_algos(rows)

    def entry_orders(self, inst: str = INST, pages: int = 30) -> list[dict]:
        """ประวัติคำสั่ง (OKX เก็บ ~3 เดือนขึ้นไป) ไล่ทีละหน้าย้อนหลังด้วย after=ordId"""
        rows, after = [], None
        for _ in range(pages):
            params = {"instType": "SWAP", "instId": inst, "limit": "100", **({"after": after} if after else {})}
            page = _get("/api/v5/trade/orders-history-archive", params, self.creds)
            rows += page
            if len(page) < 100:
                break
            after = page[-1].get("ordId")
        return parse_entry_orders(rows)

    def algo_history(self, inst: str = INST) -> list[dict]:
        rows = []
        for kind in ("conditional", "oco"):
            for state in ("effective", "canceled"):
                rows += _get("/api/v5/trade/orders-algo-history",
                             {"ordType": kind, "state": state, "instType": "SWAP", "instId": inst, "limit": "100"},
                             self.creds)
        return parse_algo_history(rows)

    def equity(self) -> float | None:
        data = _get("/api/v5/account/balance", None, self.creds)
        return _f(data[0].get("totalEq")) if data else None


def contract_value(inst: str = INST) -> float:
    """ขนาดสัญญา (public, ไม่ต้องใช้ key) — ดึงไม่ได้ใช้ค่าเริ่มต้นที่รู้แน่ของ BTC-USDT-SWAP"""
    try:
        data = _get("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst})
        return _f(data[0].get("ctVal")) or DEFAULT_CT_VAL
    except (OkxError, IndexError):
        return DEFAULT_CT_VAL
