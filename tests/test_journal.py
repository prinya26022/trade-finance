"""Phase 55 — สมุดเทรด. Offline ล้วน: ไม่แตะ OKX / Google / yfinance.

สิ่งที่คุ้มครอง:
- ลายเซ็น OKX ตรงตามสูตรในเอกสาร และตัวแปลงอ่านรูปแบบข้อมูลตามเอกสารได้ (ทั้งโหมด long/short และ net)
- ซิงก์รอบใหม่ห้ามทับเหตุผลที่ผู้ใช้แตะ และค่า ณ ตอนเข้า (SL/TP/ยอดพอร์ต) ห้ามเปลี่ยนตามทีหลัง
- บริบทกราฟ ณ เวลาเข้าไม้ใช้แท่งที่ปิดก่อนเวลานั้นเท่านั้น
- ความเสี่ยงจริงคิดจากระยะ stop × ขนาดเหรียญ ไม่ใช่มาร์จิน
"""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta

import pytest

from src.journal import context as C
from src.journal import okx, sheet, stats, store, sync, tags
from src.wave.candles import Candle


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "journal.db"
    monkeypatch.setattr(store, "DB_PATH", path)
    return path


# ---------- OKX ----------

def test_signature_matches_the_documented_formula():
    ts, path = "2026-10-04T08:00:00.123Z", "/api/v5/account/positions?instType=SWAP"
    want = base64.b64encode(hmac.new(b"sec", f"{ts}GET{path}".encode(), hashlib.sha256).digest()).decode()
    assert okx.sign("sec", ts, "get", path) == want


def test_timestamp_format_has_milliseconds_and_z():
    assert okx._timestamp(datetime(2026, 10, 4, 8, 0, 0, 123456)) == "2026-10-04T08:00:00.123Z"


CLOSED = {"instId": "BTC-USDT-SWAP", "posId": "777", "direction": "short", "cTime": "1790000000000",
          "uTime": "1790003600000", "openAvgPx": "84000", "closeAvgPx": "83000", "closeTotalPos": "10",
          "openMaxPos": "10", "lever": "20", "realizedPnl": "9.5", "pnl": "10", "fee": "-0.5", "type": "2"}
OPEN = {"instId": "BTC-USDT-SWAP", "posId": "778", "posSide": "net", "pos": "-5", "avgPx": "84500",
        "lever": "20", "cTime": "1790007200000", "margin": "21.1"}


def test_parse_closed_uses_realized_pnl_and_open_time_in_the_key():
    t = okx.parse_closed(CLOSED)
    assert t["side"] == "short" and t["status"] == "closed" and t["pnl"] == 9.5
    assert t["key"] == "okx:777:1790000000000" and t["entry"] == 84000 and t["exit"] == 83000
    assert t["opened_at"] < t["closed_at"] and not t["liquidated"]
    assert okx.parse_closed({**CLOSED, "type": "3"})["liquidated"]


def test_parse_open_reads_net_mode_sign_as_direction():
    t = okx.parse_open(OPEN)
    assert t["side"] == "short" and t["contracts"] == 5 and t["status"] == "open"


def test_parse_algos_maps_closing_side_to_position_side():
    rows = [{"posSide": "net", "side": "buy", "slTriggerPx": "86000", "tpTriggerPx": ""},
            {"posSide": "net", "side": "buy", "slTriggerPx": "", "tpTriggerPx": "80000"},
            {"posSide": "long", "side": "sell", "slTriggerPx": "82000", "tpTriggerPx": "90000"}]
    a = okx.parse_algos(rows)
    assert a["short"] == {"sl": 86000.0, "tp": 80000.0}
    assert a["long"] == {"sl": 82000.0, "tp": 90000.0}


def test_no_credentials_means_none(monkeypatch):
    for k in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"):
        monkeypatch.delenv(k, raising=False)
    assert okx.credentials() is None


def test_okx_client_has_no_method_that_can_trade():
    """อ่านอย่างเดียวโดยโครงสร้าง — ถ้าวันหนึ่งมีคนเพิ่มเมธอดส่งคำสั่ง เทสต์นี้ต้องแดง"""
    names = {n for n in dir(okx.Client) if not n.startswith("_")}
    assert names == {"closed_positions", "open_positions", "stops", "equity"}
    assert "POST" not in open(okx.__file__, encoding="utf-8").read().replace('"POST" not in', "")


# ---------- store ----------

def test_resync_never_overwrites_user_tags_or_first_seen_values(db):
    tid, s = store.upsert({**okx.parse_open(OPEN), "sl": 86000, "equity": 2000})
    assert s == "new"
    store.set_tags(tid, {"time": ["มีเวลาดู"]}, "ทดสอบ")
    _, s2 = store.upsert({**okx.parse_open(OPEN), "sl": 99999, "equity": 1})       # ย้าย stop ทีหลัง
    t = store.get(tid)
    assert s2 == "same" and t["sl"] == 86000 and t["equity"] == 2000
    assert t["tags"] == {"time": ["มีเวลาดู"]} and t["note"] == "ทดสอบ"


def test_open_then_closed_is_reported_once_as_closed(db):
    row_open = {**OPEN, "posId": "777", "cTime": CLOSED["cTime"], "pos": "-10", "avgPx": "84000"}
    tid, _ = store.upsert(okx.parse_open(row_open))
    t2, state = store.upsert(okx.parse_closed(CLOSED))
    assert t2 == tid and state == "closed"
    assert store.upsert(okx.parse_closed(CLOSED))[1] == "same"


# ---------- บริบท / ความเสี่ยง ----------

def _hourly(n: int, start=datetime(2026, 5, 1)) -> list[Candle]:
    out, p = [], 80000.0
    for i in range(n):
        q = p * (1 + (0.004 if i % 7 else -0.01))
        out.append(Candle(start + timedelta(hours=i), p, max(p, q) * 1.002, min(p, q) * 0.998, q))
        p = q
    return out


def _daily_from(hourly: list[Candle]) -> list[Candle]:
    days: dict = {}
    for c in hourly:
        days.setdefault(c.ts.date(), []).append(c)
    return [Candle(datetime.combine(d, datetime.min.time()), cs[0].open, max(x.high for x in cs),
                   min(x.low for x in cs), cs[-1].close) for d, cs in sorted(days.items())]


def test_context_ignores_candles_after_the_entry_time():
    h = _hourly(2400)
    at = h[2000].ts + timedelta(minutes=30)
    a = C.build(h[:2001], _daily_from(h[:2001]), at, "long", 90000, 89000, 93000)
    crazy = h[:2001] + [Candle(x.ts, 1, 2, 0.5, 1) for x in h[2001:]]
    b = C.build(crazy, _daily_from(crazy), at, "long", 90000, 89000, 93000)
    assert a == b


def test_context_flags_a_stop_inside_normal_4h_swing():
    h = _hourly(2400)
    at = h[-1].ts
    ctx = C.build(h, _daily_from(h), at, "long", 90000, 89900, 93000)          # stop 0.11%
    assert ctx["stop_inside_noise"] is True and ctx["rr"] == 30.0
    assert ctx["stop_wrong_side"] is False
    assert C.build(h, _daily_from(h), at, "long", 90000, 91000, 93000)["stop_wrong_side"] is True


def test_risk_is_stop_distance_times_coins_not_margin():
    """ผู้ใช้วางมาร์จิน ~160$ (10% ของ 2,000$) แต่เงินที่เสียจริงตอนโดน stop คือระยะ × ขนาด"""
    r = C.risk({"entry": 84000, "sl": 83160, "contracts": 2, "ct_val": 0.01, "equity": 2000})
    assert r == {"risk_usd": 16.8, "risk_pct": 0.84}
    assert C.risk({"entry": 84000, "sl": None}) == {}


# ---------- ชีต / ปุ่ม / สถิติ ----------

SHEET = ("Timestamp,คู่เทรด ,ทิศ,Trend,  Elliott นับเป็นคลื่น  ,MACD,RSI,มีเวลาดูไม้นี้จริงไหม  ,"
         "  เข้าครบเช็คลิสต์ไหม  ,ราคาเข้า  ,Stoploss  ,TP,เสี่ยงกี่ % ของพอร์ตไม้นี้  ,เหตุผลที่เข้า,ผล,PnL\n"
         "6/17/2026 13:29:02,BTC,Short,ตามเทรนด์,5,divergence,ปกติ,ไม่มี,ตามแผน,62700,64536,54000,10%,เหตุผล ก,ขาดทุน,35$\n"
         "6/17/2026 13:41:30,BTC,Long,สวนเทรนด์,C,ไม่ชัด,divergence,มี,ตามแผน,66135,64800,71000,10,เหตุผล ข,กำไร,195$\n")


def test_sheet_import_maps_columns_and_signs_pnl():
    a, b = sheet.parse(SHEET)
    assert a["pnl"] == -35 and b["pnl"] == 195 and a["side"] == "short" and b["side"] == "long"
    assert a["tags"]["time"] == ["ไม่มีเวลาดู"] and b["tags"]["wave"] == ["C"] and "divergence" in a["tags"]["why"]
    assert a.get("opened_at") is None                                      # ไม่ใส่เวลากรอกฟอร์มแทนเวลาเข้า
    assert sheet.csv_url("https://docs.google.com/spreadsheets/d/ABC123/edit?usp=sharing").endswith(
        "/d/ABC123/export?format=csv")


def test_tag_cleaning_drops_unknown_values_and_enforces_single_choice():
    out = tags.clean({"time": ["มีเวลาดู", "ไม่มีเวลาดู"], "why": ["divergence", "hack"], "evil": ["x"]})
    assert out == {"time": ["มีเวลาดู"], "why": ["divergence"]}


def test_stats_flag_thin_groups_and_bucket_by_rr_and_stop():
    trades = [{**t, "status": "closed"} for t in sheet.parse(SHEET)]
    s = stats.compute(trades)
    assert s["overall"]["n"] == 2 and s["overall"]["net"] == 160
    assert s["groups"]["R:R ที่วางไว้"]["R:R 3–5"]["n"] == 2          # 4.7 และ 3.6
    assert all(v["thin"] for g in s["groups"].values() for v in g.values())
    assert "น้อยเกิน" in stats.format_report(s)


# ---------- ซิงก์ + API ----------

class FakeClient:
    def __init__(self, opens=(), closed=()):
        self._o, self._c = list(opens), list(closed)

    def equity(self):
        return 2000.0

    def stops(self):
        return {"short": {"sl": 86000.0, "tp": 80000.0}}

    def open_positions(self):
        return [okx.parse_open(r) for r in self._o]

    def closed_positions(self):
        return [okx.parse_closed(r) for r in self._c]


def test_sync_reports_new_and_closed_once_and_attaches_risk(db):
    h = _hourly(2400, start=datetime(2026, 7, 1))
    ts = int((h[-100].ts - datetime(1970, 1, 1)).total_seconds() * 1000)
    row = {**OPEN, "cTime": str(ts)}
    rep = sync.sync(FakeClient(opens=[row]), candles=(h, _daily_from(h)), ct_val=0.01)
    (t,) = rep.opened
    assert t["sl"] == 86000 and t["equity"] == 2000 and t["context"]["trend"]
    assert "แตะเหตุผล" in sync.describe(t) and "เสี่ยงจริง" in sync.describe(t)
    again = sync.sync(FakeClient(opens=[row]), candles=(h, _daily_from(h)), ct_val=0.01)
    assert again.opened == [] and again.closed == []


def test_journal_api_roundtrip(db):
    from fastapi.testclient import TestClient
    from src.api.main import app
    tid, _ = store.upsert(sheet.parse(SHEET)[0])
    client = TestClient(app)
    body = client.get("/api/journal").json()
    assert body["trades"][0]["id"] == tid and body["tag_groups"][0]["key"] == "time"
    r = client.put(f"/api/journal/{tid}/tags", json={"tags": {"plan": ["ด้นสด"], "x": ["y"]}, "note": " โน้ต "})
    assert r.status_code == 200 and r.json()["tags"] == {"plan": ["ด้นสด"]} and r.json()["note"] == "โน้ต"
    assert client.put("/api/journal/999/tags", json={"tags": {}}).status_code == 404
