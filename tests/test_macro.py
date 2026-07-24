"""Phase 26 Macro Event Radar — ทดสอบ *ออฟไลน์ล้วน* (ห้ามแตะ FRED/yfinance/เน็ต).

หัวใจที่ต้องพิสูจน์:
- fred: parse CSV ถูก, ข้ามค่าที่ขาด ('.'), เรียงเก่า->ใหม่.
- baserate: 'สัญญาณ' คิดถูกต่อ series (CPI=YoY, NFP=งานเพิ่ม, UNRATE=ระดับ),
  ทิศทางเร่ง/ชะลอถูก, สถิติ n/mean/ช่วง/ทิศ กรองถูก, ติดธง approx ตรงความจริง.
- store: mark/get roundtrip (temp DB).
- radar: bootstrap ไม่แจ้ง, ตัวเลขใหม่ค่อยแจ้ง; format มีคำเตือน 'ไม่ใช่คำแนะนำซื้อขาย'.
"""
from datetime import date

import pytest

from src.macro import altseason, baserate, fred, geonews, radar, store
from src.macro.fred import Observation


# ---------- fred: parse CSV ----------

class _FakeResp:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body


def test_fetch_series_parses_and_skips_missing(monkeypatch):
    csv_text = (
        "observation_date,CPIAUCSL\n"
        "2020-01-01,100.0\n"
        "2020-02-01,.\n"          # ค่าที่ขาด -> ต้องข้าม
        "2020-03-01,101.5\n"
    )
    monkeypatch.setattr(fred.urllib.request, "urlopen", lambda *a, **k: _FakeResp(csv_text))
    obs = fred.fetch_series("CPI")
    assert [o.value for o in obs] == [100.0, 101.5]           # แถว '.' หายไป
    assert obs[0].ref_date == date(2020, 1, 1)
    assert obs[-1].ref_date == date(2020, 3, 1)               # เรียงเก่า->ใหม่


def test_fetch_series_network_fail_returns_empty(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no net")
    monkeypatch.setattr(fred.urllib.request, "urlopen", _boom)
    assert fred.fetch_series("CPI") == []                     # ล้มเงียบ ไม่ raise


# ---------- baserate: signal ----------

def _obs(values, start_year=2000):
    """สร้าง Observation รายเดือนต่อเนื่องจากลิสต์ค่า."""
    out = []
    y, m = start_year, 1
    for v in values:
        out.append(Observation(date(y, m, 1), float(v)))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def test_signal_cpi_is_yoy():
    # 13 เดือน: YoY เดือนที่ 13 = (110-100)/100 = 10%
    obs = _obs([100] * 12 + [110])
    sig = baserate._signal_values("CPI", obs)
    assert sig[:12] == [None] * 12          # 12 เดือนแรกคิด YoY ไม่ได้
    assert sig[12] == pytest.approx(10.0)


def test_signal_nfp_is_monthly_delta():
    obs = _obs([1000, 1150, 1120])
    sig = baserate._signal_values("NFP", obs)
    assert sig[0] is None
    assert sig[1] == pytest.approx(150.0)   # จ้างเพิ่ม 150
    assert sig[2] == pytest.approx(-30.0)   # จ้างลดลง 30


def test_signal_unrate_is_level():
    obs = _obs([4.0, 4.1, 3.9])
    assert baserate._signal_values("UNRATE", obs) == [4.0, 4.1, 3.9]


def test_latest_signal_direction(monkeypatch):
    # UNRATE ระดับ 4.0 -> 4.2 = ว่างงานสูงขึ้น ('up')
    monkeypatch.setattr(fred, "fetch_series", lambda k: _obs([4.0, 4.2]))
    ls = baserate.latest_signal("UNRATE")
    assert ls.direction == "up"
    assert ls.signal == pytest.approx(4.2)
    assert ls.prev_signal == pytest.approx(4.0)


# ---------- baserate: reaction stats ----------

def test_reaction_stats_filters_direction_and_computes(monkeypatch):
    # UNRATE: signals 4.0,4.1,4.0,4.1 -> events: up,down,up  (ทิศจากระดับเทียบก่อนหน้า)
    monkeypatch.setattr(fred, "fetch_series", lambda k: _obs([4.0, 4.1, 4.0, 4.1]))
    monkeypatch.setattr(fred, "release_dates", lambda k: None)      # ไม่มีคีย์
    monkeypatch.setattr(fred, "has_api_key", lambda: False)
    # ราคาปลอม: ขึ้น 10% ทุกวันถัดจากวันประกาศ ไม่ว่าอะไร -> mean เท่ากันทุก event
    def _fake_prices(_ticker):
        prices = {}
        # ครอบคลุมช่วงวันประกาศประมาณ (ref+lag) ของ 2000..2001
        from datetime import timedelta
        d = date(2000, 1, 1)
        val = 100.0
        while d <= date(2002, 12, 31):
            prices[d] = val
            val *= 1.10          # +10% ต่อวัน (สุดโต่ง แต่ทดสอบ mean/ทิศได้)
            d += timedelta(days=1)
        return prices
    monkeypatch.setattr(baserate, "_price_history", _fake_prices)
    monkeypatch.setattr(baserate, "ASSETS", {"X": "X-USD"})         # สินทรัพย์เดียวพอ

    up = baserate.reaction_stats("UNRATE", "up", horizon_days=1)
    assert len(up) == 1
    r = up[0]
    assert r.n == 2                     # up เกิด 2 ครั้ง (i=1, i=3)
    assert r.approx is True             # ไม่มีคีย์ -> ติดธง approx
    assert r.mean_pct == pytest.approx(10.0, abs=0.01)
    assert r.share_up == 1.0            # ราคาขึ้นทุกครั้ง

    down = baserate.reaction_stats("UNRATE", "down", horizon_days=1)
    assert down[0].n == 1              # down เกิดครั้งเดียว (i=2)


def test_reaction_stats_no_macro_data(monkeypatch):
    monkeypatch.setattr(fred, "fetch_series", lambda k: [])
    assert baserate.reaction_stats("CPI", "up") == []


# ---------- store ----------

def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    assert store.get_seen("CPI") is None            # ยังไม่เคย
    store.mark_seen("CPI", "2026-06-01", 3.7)
    assert store.get_seen("CPI") == "2026-06-01"
    store.mark_seen("CPI", "2026-07-01", 3.8)       # upsert
    assert store.get_seen("CPI") == "2026-07-01"


# ---------- radar ----------

def _stub_release_view(key):
    return radar.ReleaseView(
        key=key, label="x", ref_date="2026-06-01", value=1.0, unit="%",
        direction="up", desc="เร่งตัว", signal=2.0, prev_signal=1.0, stats=[],
    )


def test_scan_bootstrap_then_alerts_on_new(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(fred, "SERIES", {"CPI": fred.SERIES["CPI"]})   # ตัวเดียวพอ
    monkeypatch.setattr(fred, "latest_two",
                        lambda k: (Observation(date(2026, 5, 1), 1.0),
                                   Observation(date(2026, 6, 1), 2.0)))
    monkeypatch.setattr(radar, "latest_release_view", _stub_release_view)

    assert radar.scan_for_alerts() == []            # bootstrap: จำ ไม่แจ้ง
    assert store.get_seen("CPI") == "2026-06-01"
    assert radar.scan_for_alerts() == []            # ไม่มีอะไรใหม่

    # ตัวเลขเดือนใหม่โผล่ -> ต้องแจ้ง 1 ครั้ง
    monkeypatch.setattr(fred, "latest_two",
                        lambda k: (Observation(date(2026, 6, 1), 2.0),
                                   Observation(date(2026, 7, 1), 3.0)))
    alerts = radar.scan_for_alerts()
    assert [v.key for v in alerts] == ["CPI"]
    assert store.get_seen("CPI") == "2026-07-01"


def test_format_alert_has_caveat_and_no_crash():
    view = _stub_release_view("CPI")
    view.stats = []
    text = radar.format_alert(view)
    assert "ไม่ใช่คำแนะนำซื้อ" in text
    assert "CPI" in text or "x" in text


# ---------- geonews ----------

_RSS_XML = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Missile strike hits port - Reuters</title>
        <link>http://ex.com/1</link>
        <pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate></item>
  <item><title>Missile strike hits port - AP</title>
        <link>http://ex.com/2</link>
        <pubDate>Wed, 22 Jul 2026 11:00:00 GMT</pubDate></item>
  <item><title>New sanctions announced - BBC</title>
        <link>http://ex.com/3</link>
        <pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_geonews_parses_dedupes_splits_source(monkeypatch):
    monkeypatch.setattr(geonews.urllib.request, "urlopen", lambda *a, **k: _FakeResp(_RSS_XML))
    items = geonews.fetch_geopolitical(max_items=8)
    assert len(items) == 2                     # ข่าวซ้ำหัวเดียวกันถูก dedupe เหลือ 1
    assert items[0].title == "Missile strike hits port"
    assert items[0].source == "Reuters"        # แยก ' - Source' ออกถูก
    assert items[0].published.startswith("2026-07-22")   # pubDate -> ISO
    assert items[1].title == "New sanctions announced"


def test_geonews_network_fail_returns_empty(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no net")
    monkeypatch.setattr(geonews.urllib.request, "urlopen", _boom)
    assert geonews.fetch_geopolitical() == []


def test_geonews_format_warn():
    assert geonews.format_warn([]) == ""       # ไม่มีข่าว -> ว่าง (ไม่ส่ง noise)
    item = geonews.GeoNewsItem("Airstrike reported", "Reuters", "2026-07-22T10:00:00", "http://x")
    text = geonews.format_warn([item])
    assert "จับตา" in text and "ไม่ใช่สัญญาณซื้อขาย" in text
    assert "Airstrike reported" in text


# ---------- altseason (ETH/BTC momentum) ----------

def _daily_prices(start, days, daily_growth):
    """ราคาปิดรายวันต่อเนื่อง (date->value) โตแบบ compounding ต่อวัน."""
    from datetime import date, timedelta
    out = {}
    d, v = date(*start), 100.0
    for _ in range(days):
        out[d] = v
        v *= daily_growth
        d += timedelta(days=1)
    return out


def test_alt_momentum_eth_leading(monkeypatch):
    # ETH โตเร็วกว่า BTC -> ratio ETH/BTC เพิ่ม -> state 'alt'
    def _fake(ticker):
        return _daily_prices((2026, 1, 1), 120, 1.010 if ticker == "ETH-USD" else 1.002)
    monkeypatch.setattr(altseason, "_price_history", _fake)
    a = altseason.eth_btc_momentum()
    assert a is not None
    assert a.state == "alt"
    assert a.change_30d > 0            # ratio ขึ้น
    assert a.eth_30d > a.btc_30d       # ETH นำจริง


def test_alt_momentum_btc_leading(monkeypatch):
    def _fake(ticker):
        return _daily_prices((2026, 1, 1), 120, 1.001 if ticker == "ETH-USD" else 1.010)
    monkeypatch.setattr(altseason, "_price_history", _fake)
    a = altseason.eth_btc_momentum()
    assert a.state == "btc"
    assert a.change_30d < 0


def test_alt_momentum_insufficient_data(monkeypatch):
    monkeypatch.setattr(altseason, "_price_history", lambda t: {})
    assert altseason.eth_btc_momentum() is None
