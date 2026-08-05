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

from src.macro import altseason, baserate, fred, geonews, notify, radar, store
from src.macro.fred import Observation


@pytest.fixture(autouse=True)
def _isolate_fred(monkeypatch):
    """กันสองอย่างที่ทำให้เทสต์ 'ผ่านเพราะไปดึงของจริง' แทนที่จะทดสอบโค้ด.

    1) cache ในโปรเซส: ไม่ล้าง = ผลของเคสก่อนไหลข้ามมาตอบแทน stub
    2) FRED_API_KEY: notify.py เรียก load_dotenv() ตอน import ทำให้คีย์จริงใน .env หลุดเข้า
       os.environ ทั้ง session -> fetch_series จะวิ่ง path official API ยิงเน็ตจริง
       (เทสต์เดิมรอดเพราะ patch urlopen ไว้ ซึ่งครอบทั้งสอง path พอดี)
    """
    fred.clear_cache()
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    yield
    fred.clear_cache()


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


# ---------- notify (Discord alert wiring) ----------

def _capture_posts(monkeypatch):
    posted = []
    monkeypatch.setattr(notify, "post", lambda text, url=None: posted.append(text) or True)
    return posted


def test_send_macro_alert_posts_new_release(monkeypatch):
    posted = _capture_posts(monkeypatch)
    monkeypatch.setattr(radar, "scan_for_alerts", lambda mark=True: [_stub_release_view("CPI")])
    monkeypatch.setattr(geonews, "fetch_geopolitical", lambda max_items=5: [])
    n = notify.send_macro_alert(webhook_url="http://x")
    assert n == 1
    assert len(posted) == 1
    assert "ไม่ใช่คำแนะนำซื้อ" in posted[0]      # สรุปมีคำเตือน


def test_send_macro_alert_silent_when_nothing_new(monkeypatch):
    posted = _capture_posts(monkeypatch)
    monkeypatch.setattr(radar, "scan_for_alerts", lambda mark=True: [])
    n = notify.send_macro_alert(webhook_url="http://x")
    assert n == 0 and posted == []               # ไม่มีใหม่ = เงียบสนิท ไม่ยิงอะไร


def test_send_macro_alert_appends_geo_only_on_event(monkeypatch):
    posted = _capture_posts(monkeypatch)
    monkeypatch.setattr(radar, "scan_for_alerts", lambda mark=True: [_stub_release_view("CPI")])
    item = geonews.GeoNewsItem("Strike", "Reuters", "2026-07-22T10:00:00", "http://x")
    monkeypatch.setattr(geonews, "fetch_geopolitical", lambda max_items=5: [item])
    notify.send_macro_alert(webhook_url="http://x")
    assert len(posted) == 2                       # สรุป + ธงข่าวภูมิรัฐศาสตร์
    assert "จับตา" in posted[1]


# ---------- สถานะของเรดาร์เอง (Phase 26.1) ----------
# เหตุผลที่ต้องมีชุดนี้: ผลลัพธ์ปกติของ radar คือ "เงียบ" และผลลัพธ์ตอนพังก็ "เงียบ" เหมือนกันเป๊ะ
# เคยเกิดจริงตอน FRED บล็อก IP ของ runner — ระบบดูเหมือนทำงานอยู่ทุกวัน ทั้งที่ไม่ได้ตรวจอะไรเลย

def _seed_seen(tmp_path, monkeypatch, **seen):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "macro.db")
    for k, v in seen.items():
        store.mark_seen(k, v)


def _fred_at(month: str):
    """ทำให้ทุก series ของ FRED ล่าสุดอยู่ที่เดือนนั้น."""
    def fake(key):
        ref = date.fromisoformat(month)
        prev = date(ref.year - (ref.month == 1), (ref.month - 2) % 12 + 1, 1)
        return Observation(prev, 1.0), Observation(ref, 2.0)
    return fake


def test_status_says_ok_when_the_next_release_simply_has_not_come_yet(tmp_path, monkeypatch):
    """สถานการณ์จริงของ 2026-08-05: ตัวเลข ก.ค. ยังไม่ออก — เงียบแบบนี้คือถูกต้อง."""
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01", PPI="2026-06-01",
               UNRATE="2026-06-01", NFP="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-06-01"))

    rows = {r.key: r for r in radar.status(today=date(2026, 8, 5))}
    assert all(r.state == "ok" for r in rows.values())
    assert rows["NFP"].due_on == "2026-08-05"        # 1 ก.ค. + 35 วัน
    assert rows["CPI"].due_on == "2026-08-13"        # CPI ออกช้ากว่า -> ยังไม่ถึงคิว


def test_status_flags_a_series_that_is_overdue(tmp_path, monkeypatch):
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01", PPI="2026-06-01",
               UNRATE="2026-06-01", NFP="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-06-01"))

    rows = {r.key: r for r in radar.status(today=date(2026, 9, 1))}
    assert rows["NFP"].state == "overdue"
    assert rows["NFP"].overdue_days == 20            # เลย 2026-08-05 มา 27 วัน หักผ่อนผัน 7


def test_status_does_not_cry_wolf_during_the_grace_window(tmp_path, monkeypatch):
    """วันประกาศเป็นค่าประมาณ เลื่อน 2-3 วันเป็นเรื่องปกติ — เตือนทุกเดือนแล้วจะไม่มีใครเชื่อ."""
    _seed_seen(tmp_path, monkeypatch, NFP="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-06-01"))

    rows = {r.key: r for r in radar.status(today=date(2026, 8, 11))}   # เลยมา 6 วัน
    assert rows["NFP"].state == "ok"


def test_status_reports_a_fetch_failure_instead_of_looking_calm(tmp_path, monkeypatch):
    """หัวใจของทั้งชุด: ดึงข้อมูลไม่ได้ ต้องไม่หน้าตาเหมือน 'ไม่มีข่าว'."""
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", lambda key: None)

    rows = radar.status(today=date(2026, 8, 5))
    assert all(r.state == "fetch_failed" for r in rows)
    assert all(r.latest_ref is None for r in rows)


def test_status_shows_new_data_that_has_not_been_announced_yet(tmp_path, monkeypatch):
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01", PPI="2026-06-01",
               UNRATE="2026-06-01", NFP="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-07-01"))

    rows = {r.key: r for r in radar.status(today=date(2026, 8, 20))}
    assert rows["CPI"].state == "unreported"


def test_status_never_marks_anything_as_seen(tmp_path, monkeypatch):
    """ต้องอ่านอย่างเดียว — ถ้า status() เผลอ mark หน้าเว็บที่เปิดดูจะกลืนแจ้งเตือนไปเงียบๆ."""
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-07-01"))

    radar.status(today=date(2026, 8, 20))
    assert store.get_seen("CPI") == "2026-06-01"


def test_render_status_is_readable_and_names_the_problem(tmp_path, monkeypatch):
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", lambda key: None)
    text = radar.render_status(radar.status(today=date(2026, 8, 5)), today=date(2026, 8, 5))
    assert "ดึง FRED ไม่ได้" in text


# ---------- แจ้งเตือน 'ระบบมีปัญหา' (คนละเรื่องกับ 'ตลาดมีข่าว') ----------

def test_health_warning_fires_when_fred_cannot_be_reached(tmp_path, monkeypatch):
    posted = _capture_posts(monkeypatch)
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", lambda key: None)

    assert notify.send_health_warning(webhook_url="http://x", today=date(2026, 8, 5)) is True
    assert "ดึงข้อมูลจาก FRED ไม่ได้" in posted[0]


def test_health_warning_stays_quiet_when_everything_is_fine(tmp_path, monkeypatch):
    posted = _capture_posts(monkeypatch)
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01", PPI="2026-06-01",
               UNRATE="2026-06-01", NFP="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-06-01"))

    assert notify.send_health_warning(webhook_url="http://x", today=date(2026, 8, 5)) is False
    assert posted == []


def test_health_warning_is_sent_at_most_once_a_day(tmp_path, monkeypatch):
    """workflow รันชั่วโมงละรอบ — เตือนทุกรอบคือการสอนตัวเองให้เมินการแจ้งเตือน."""
    posted = _capture_posts(monkeypatch)
    _seed_seen(tmp_path, monkeypatch, CPI="2026-06-01")
    monkeypatch.setattr(fred, "latest_two", lambda key: None)

    assert notify.send_health_warning(webhook_url="http://x", today=date(2026, 8, 5)) is True
    assert notify.send_health_warning(webhook_url="http://x", today=date(2026, 8, 5)) is False
    assert notify.send_health_warning(webhook_url="http://x", today=date(2026, 8, 6)) is True
    assert len(posted) == 2


def test_health_key_is_not_mistaken_for_a_real_series(tmp_path, monkeypatch):
    """__health อยู่ในตารางเดียวกับ series จริง — ต้องไม่หลุดเข้าไปในรอบสแกน."""
    _seed_seen(tmp_path, monkeypatch)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "macro.db")
    store.mark_seen(notify._HEALTH_KEY, "2026-08-05")
    monkeypatch.setattr(fred, "latest_two", _fred_at("2026-07-01"))

    alerts = radar.scan_for_alerts(mark=False)
    assert notify._HEALTH_KEY not in {a.key for a in alerts}


# ---------- cache ของ fred ----------

def test_fred_cache_avoids_refetching_the_same_series(monkeypatch):
    calls = []
    monkeypatch.setattr(fred, "_fetch_series_csv", lambda sid: calls.append(sid) or _obs([1.0, 2.0]))
    fred.fetch_series("CPI")
    fred.fetch_series("CPI")
    assert len(calls) == 1


def test_fred_cache_does_not_remember_a_failure(monkeypatch):
    """จำความล้มเหลวไว้ = รอบถัดไปในชั่วโมงเดียวกันจะ 'พัง' ต่อ ทั้งที่ FRED กลับมาแล้ว."""
    results = [[], _obs([1.0, 2.0])]
    monkeypatch.setattr(fred, "_fetch_series_csv", lambda sid: results.pop(0))
    assert fred.fetch_series("CPI") == []
    assert len(fred.fetch_series("CPI")) == 2
