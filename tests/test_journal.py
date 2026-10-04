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
    assert names == {"closed_positions", "open_positions", "stops", "equity", "entry_orders", "algo_history"}
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

    def entry_orders(self, pages=1):
        return getattr(self, "_entries", [])

    def algo_history(self):
        return getattr(self, "_algos", [])


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


def test_only_recent_trades_are_news():
    """ซิงก์ครั้งแรกเคยแจ้งทุกไม้ย้อนหลัง 101 ไม้ — ประวัติไม่ใช่ข่าว"""
    now = datetime(2026, 10, 4, 12, 0)
    fresh = {"status": "open", "opened_at": "2026-10-04T09:00:00"}
    old_closed = {"status": "closed", "opened_at": "2025-03-01T00:00:00", "closed_at": "2025-03-02T00:00:00"}
    just_closed = {"status": "closed", "opened_at": "2026-09-20T00:00:00", "closed_at": "2026-10-04T08:00:00"}
    assert sync.is_news(fresh, now) and sync.is_news(just_closed, now)
    assert not sync.is_news(old_closed, now)
    assert not sync.is_news({"status": "closed", "closed_at": None}, now)


def test_discord_retries_after_rate_limit(monkeypatch):
    import io
    import urllib.error
    from src.notify import discord
    calls = []

    class _Ok:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("u", 429, "rate", {}, io.BytesIO(b'{"retry_after": 0.01}'))
        return _Ok()

    monkeypatch.setattr(discord.urllib.request, "urlopen", fake)
    monkeypatch.setattr(discord.time, "sleep", lambda s: None)
    assert discord.post("x", "https://discord.test/x") is True and len(calls) == 2


# ---------- เติม stop ตัวแรก (ข้อ 3) ----------

def _ms(dt: datetime) -> str:
    return str(int((dt - datetime(1970, 1, 1)).total_seconds() * 1000))


def test_parse_entry_orders_reads_attached_stop_and_skips_closing_orders():
    t = datetime(2026, 9, 30, 7, 23)
    rows = [{"state": "filled", "reduceOnly": "false", "side": "buy", "posSide": "net", "uTime": _ms(t),
             "attachAlgoOrds": [{"slTriggerPx": "82200", "tpTriggerPx": "90000"}]},
            {"state": "filled", "reduceOnly": "true", "side": "sell", "posSide": "net", "uTime": _ms(t),
             "attachAlgoOrds": [{"slTriggerPx": "1"}]},
            {"state": "canceled", "reduceOnly": "false", "side": "buy", "attachAlgoOrds": [{"slTriggerPx": "2"}]}]
    (o,) = okx.parse_entry_orders(rows)
    assert o == {"ts": t, "side": "long", "sl": 82200.0, "tp": 90000.0}


def test_parse_algo_history_maps_closing_side():
    (a,) = okx.parse_algo_history([{"side": "buy", "posSide": "net", "slTriggerPx": "65550",
                                    "tpTriggerPx": "59300", "cTime": _ms(datetime(2026, 7, 30))}])
    assert a["side"] == "short" and a["sl"] == 65550 and a["tp"] == 59300


def test_match_prefers_the_stop_attached_at_entry_over_later_ones():
    from src.journal import stops
    opened = datetime(2026, 9, 30, 7, 23)
    trade = {"opened_at": opened.isoformat(), "closed_at": None, "side": "long"}
    entries = [{"ts": opened + timedelta(minutes=2), "side": "long", "sl": 82200.0, "tp": 90000.0}]
    algos = [{"ts": opened + timedelta(hours=5), "side": "long", "sl": 82900.0, "tp": None}]
    assert stops.match(trade, entries, algos) == {"sl": 82200.0, "tp": 90000.0, "source": "entry"}
    assert stops.match(trade, [], algos)["source"] == "algo"
    assert stops.match(trade, [{**entries[0], "side": "short"}], []) is None          # คนละทิศ
    far = [{**entries[0], "ts": opened - timedelta(hours=3)}]
    assert stops.match(trade, far, []) is None                                         # คนละไม้


def test_match_takes_the_first_algo_stop_inside_the_trade_window():
    from src.journal import stops
    o, c = datetime(2026, 8, 1), datetime(2026, 8, 5)
    trade = {"opened_at": o.isoformat(), "closed_at": c.isoformat(), "side": "short"}
    algos = [{"ts": o - timedelta(days=2), "side": "short", "sl": 1.0, "tp": None},       # ไม้ก่อนหน้า
             {"ts": o + timedelta(hours=1), "side": "short", "sl": 66000.0, "tp": None},
             {"ts": o + timedelta(hours=9), "side": "short", "sl": 65000.0, "tp": 60000.0},
             {"ts": c + timedelta(hours=1), "side": "short", "sl": 2.0, "tp": None}]       # ไม้ถัดไป
    assert stops.match(trade, [], algos) == {"sl": 66000.0, "tp": 60000.0, "source": "algo"}


def test_backfill_replaces_a_moved_stop_with_the_one_set_at_entry(db):
    """ไม้จริง: ตอนกดเข้า stop 82,200 แต่ระบบเห็นครั้งแรกที่ 82,900 เพราะเลื่อนไปแล้ว"""
    h = _hourly(2400, start=datetime(2026, 7, 1))
    opened = h[-100].ts
    row = {**OPEN, "posSide": "net", "pos": "1.7", "avgPx": "83278.4", "cTime": _ms(opened)}

    class Moved(FakeClient):
        def stops(self):
            return {"long": {"sl": 82900.0, "tp": 90000.0}}

    client = Moved(opens=[row])
    client._entries = [{"ts": opened + timedelta(minutes=1), "side": "long", "sl": 82200.0, "tp": 90000.0}]
    sync.sync(client, candles=(h, _daily_from(h)), ct_val=0.01)
    (t,) = store.all_trades()
    assert t["sl"] == 82200.0 and t["sl_source"] == "entry"
    assert t["context"]["stop_pct"] == round((83278.4 - 82200) / 83278.4 * 100, 2)
    assert C.risk(t)["risk_usd"] == round((83278.4 - 82200) * 1.7 * 0.01, 2)


def test_old_database_gets_the_new_column(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, "
                "source TEXT NOT NULL, inst TEXT, side TEXT, status TEXT, opened_at TEXT, closed_at TEXT, "
                "entry REAL, exit REAL, contracts REAL, ct_val REAL, lever REAL, margin REAL, pnl REAL, fee REAL, "
                "liquidated INTEGER, sl REAL, tp REAL, equity REAL, context TEXT, tags TEXT, note TEXT, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(store, "DB_PATH", path)
    tid, _ = store.upsert({"key": "k", "source": "okx", "status": "closed"})
    store.set_stops(tid, 1.0, None, "algo")
    assert store.get(tid)["sl_source"] == "algo"


# ---------- เช็กลิสต์ก่อนเข้า (ข้อ 1) ----------

def _wave_snap(kill_a=83131.0, kill_b=87237.0):
    return {"report": {"scenarios": [
        {"key": "A", "title": "i ของ 5", "alive": True, "kill_level": kill_a, "kill_text": "หลุด 83,131", "bias": "up"},
        {"key": "B", "title": "5 จบแล้ว", "alive": True, "kill_level": kill_b, "kill_text": "ทะลุ 87,237", "bias": "down"},
        {"key": "C", "title": "ตายแล้ว", "alive": False, "kill_level": 1.0, "kill_text": "-", "bias": "up"}]}}


def test_check_reports_history_of_similar_trades_not_fixed_thresholds():
    from src.journal.check import evaluate
    h = _hourly(2400, start=datetime(2026, 7, 1))
    past = [{"status": "closed", "side": "long", "entry": 100.0, "sl": 99.0, "tp": 110.0, "pnl": 50.0},
            {"status": "closed", "side": "long", "entry": 100.0, "sl": 99.0, "tp": 108.0, "pnl": -10.0}]
    r = evaluate("long", sl=h[-1].close * 0.99, tp=h[-1].close * 1.10, hourly=h, daily=_daily_from(h),
                 trades=past, has_time=False, equity=2000.0, margin=160.0, lever=10.0)
    rr = next(x for x in r["history"] if x["group"] == "R:R ที่วางไว้")
    assert rr["bucket"] == "R:R เกิน 5" and rr["n"] == 2 and rr["wins"] == 1
    t = next(x for x in r["history"] if x["group"] == "มีเวลาดูไม้นี้ไหม")
    assert t["bucket"] == "ไม่มีเวลาดู" and t["n"] == 0
    assert r["risk_usd"] == round(r["entry"] * 0.01 * 160 * 10 / r["entry"], 2)
    one = next(s for s in r["sizing"] if s["risk_pct"] == 1.0)
    assert abs(one["coins"] * (r["entry"] - r["sl"]) - 20.0) < 0.05         # 1% ของ 2,000$
    assert one["contracts"] == round(one["coins"] / 0.01, 2)
    assert one["margin"] == round(one["notional"] / 10, 2)


def test_check_says_whether_the_stop_sits_beyond_the_scenarios_kill_level():
    from src.journal.check import evaluate
    h = _hourly(2400, start=datetime(2026, 7, 1))
    inside = evaluate("long", sl=83500.0, tp=None, hourly=h, daily=_daily_from(h), trades=[], wave=_wave_snap())
    a = next(w for w in inside["wave"] if w["key"] == "A")
    assert a["with_trade"] and a["stop_beyond_kill"] is False and "ทั้งที่ฉากยังไม่ผิด" in a["stop_vs_kill"]
    beyond = evaluate("long", sl=82900.0, tp=None, hourly=h, daily=_daily_from(h), trades=[], wave=_wave_snap())
    assert next(w for w in beyond["wave"] if w["key"] == "A")["stop_beyond_kill"] is True
    assert {w["key"] for w in beyond["wave"]} == {"A", "B"}                   # ฉากที่ตายแล้วไม่โชว์
    assert not next(w for w in beyond["wave"] if w["key"] == "B")["with_trade"]


def test_link_checks_pairs_by_side_time_and_price():
    from src.journal.check import link_checks
    checks = [{"id": 1, "created_at": "2026-10-05T10:00:00", "side": "long", "entry": 84000.0, "trade_id": None}]
    trades = [{"id": 7, "side": "long", "opened_at": "2026-10-05T11:30:00", "entry": 84300.0},   # ตรง
              {"id": 8, "side": "short", "opened_at": "2026-10-05T10:30:00", "entry": 84000.0},  # คนละทิศ
              {"id": 9, "side": "long", "opened_at": "2026-10-05T09:00:00", "entry": 84000.0},   # ก่อนเช็ก
              {"id": 10, "side": "long", "opened_at": "2026-10-05T10:10:00", "entry": 86000.0}]  # ราคาห่างเกิน 1%
    assert link_checks(trades, checks) == [(1, 7)]


def test_check_bucket_only_counts_trades_after_checks_began():
    trades = [{"status": "closed", "pnl": 5.0, "opened_at": "2026-01-01T00:00:00"},
              {"status": "closed", "pnl": -5.0, "opened_at": "2026-10-06T00:00:00", "check_id": 3},
              {"status": "closed", "pnl": -5.0, "opened_at": "2026-10-07T00:00:00"}]
    g = stats.compute(trades, checks_since="2026-10-05T00:00:00")["groups"]["เช็กลิสต์ก่อนเข้า"]
    assert g["เช็กก่อนเข้า"]["n"] == 1 and g["กดเข้าโดยไม่ได้เช็ก"]["n"] == 1
    assert "เช็กลิสต์ก่อนเข้า" not in stats.compute(trades)["groups"]


def test_check_api_saves_every_check_and_uses_synced_equity(db, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import main
    h = _hourly(2400, start=datetime(2026, 7, 1))
    monkeypatch.setattr(main, "_candles_for_check", lambda: (h, _daily_from(h)))
    monkeypatch.setattr(main.wave_snapshot, "read", lambda stem: None)
    store.set_meta("equity", 2000.0)
    client = TestClient(main.app)
    r = client.post("/api/check", json={"side": "long", "sl": h[-1].close * 0.98, "margin": 160, "lever": 10})
    assert r.status_code == 200 and r.json()["risk_pct"] is not None and r.json()["equity"] == 2000.0
    assert store.all_checks()[0]["id"] == r.json()["id"]
    assert client.post("/api/check", json={"side": "up", "sl": 1}).status_code == 400
