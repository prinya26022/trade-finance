"""Phase 53.1 — ชั้นกราฟ Week/Month. Offline ล้วน: ราคาสังเคราะห์ที่รู้คำตอบล่วงหน้า.

สิ่งที่ชุดนี้คุ้มครองจริงๆ:
- **ไม่มี look-ahead**: ราคาของสัปดาห์/เดือนที่ยังไม่ปิด เปลี่ยนคะแนนไม่ได้ ไม่ว่าจะแกว่งแค่ไหน
- "ข้อมูลไม่พอ" ต้องเป็น "วัดไม่ได้" พร้อมเหตุผล ไม่ใช่ 0/6
- margin กับ passed ต้องไม่ขัดกันเอง และอ่านทางเดียวกันทุกข้อ (+ = ผ่าน)
- คะแนนนี้ไม่มีฟิลด์ไหนรวมกับ health
"""
import math
from datetime import date, timedelta

import pytest

from src.technical import bars as B
from src.technical.indicators import pct_change, rsi_wilder, sma
from src.technical.score import MIN_WEEKS, score_from_bars, score_from_daily

START = date(2023, 1, 2)    # วันจันทร์


def _daily(price_at, days: int, crypto: bool = False, start: date = START) -> list[B.Bar]:
    """ราคารายวันจาก price_at(i). หุ้นข้ามเสาร์-อาทิตย์ crypto ไม่ข้าม"""
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        if crypto or d.weekday() < 5:
            out.append((d.isoformat(), price_at(i)))
    return out


def _zigzag_up(i: int) -> float:
    """ขาขึ้นที่มีสัปดาห์ลงสลับ (RSI ไม่ติดเพดาน) — แบบที่ตลาดจริงดูเป็น"""
    return 100 * (1.0006 ** i) * (1 + 0.04 * math.sin(i / 5))


def _flat(i: int) -> float:
    return 100.0


DAYS = 3 * 365
ASOF = START + timedelta(days=DAYS)


# ---------- bars: แท่งปิดแล้วเท่านั้น ----------

def test_week_bar_is_labelled_by_friday_and_closes_on_last_trading_day():
    daily = [("2026-09-28", 1.0), ("2026-09-29", 2.0), ("2026-10-01", 3.0)]  # จ. อ. พฤ. (ศุกร์หยุด)
    assert B.weekly(daily, asof=date(2026, 10, 5)) == [("2026-10-02", 3.0)]


def test_week_that_has_not_ended_is_dropped_even_on_its_last_day():
    """รันวันศุกร์ = แท่งศุกร์นั้นยังไม่ปิด. ยอมช้าหนึ่งวันดีกว่าใช้ราคาระหว่างวัน"""
    daily = [("2026-09-28", 1.0), ("2026-10-02", 2.0)]
    assert B.weekly(daily, asof=date(2026, 10, 2)) == []
    assert B.weekly(daily, asof=date(2026, 10, 3)) == [("2026-10-02", 2.0)]


def test_crypto_week_ends_on_sunday():
    daily = [("2026-10-03", 1.0), ("2026-10-04", 2.0), ("2026-10-05", 9.0)]   # ส. อา. จ.
    assert B.weekly(daily, asof=date(2026, 10, 6), end_weekday=B.SUNDAY) == [("2026-10-04", 2.0)]


def test_month_that_has_not_ended_is_dropped():
    daily = [("2026-08-31", 1.0), ("2026-09-15", 2.0), ("2026-09-30", 3.0), ("2026-10-02", 4.0)]
    assert B.monthly(daily, asof=date(2026, 10, 3)) == [("2026-08-31", 1.0), ("2026-09-30", 3.0)]


def test_partial_period_prices_cannot_move_the_score():
    """หัวใจของทั้งชั้น: เติมราคาของสัปดาห์/เดือนที่ยังไม่จบ (ทั้งพุ่งทั้งดิ่ง) คะแนนต้องเท่าเดิมทุกตัวอักษร"""
    asof = date(2026, 10, 3)                      # เสาร์: สัปดาห์ถึง 2 ต.ค. ปิดแล้ว, ต.ค. ยังไม่จบ
    base = _daily(_zigzag_up, (asof - START).days)
    bench = _daily(_flat, (asof - START).days)
    before = score_from_daily(base, bench, asof)
    for wild in (1e-3, 1e6):
        # 5–8 ต.ค.: อยู่ในสัปดาห์และเดือนที่ยังไม่ปิดเมื่อมองจาก asof
        polluted = base + [((asof + timedelta(days=k)).isoformat(), wild) for k in range(2, 6)]
        assert score_from_daily(polluted, bench, asof) == before


# ---------- indicators ----------

def test_sma_and_sma_back():
    v = [1, 2, 3, 4, 5]
    assert sma(v, 2) == 4.5
    assert sma(v, 2, back=2) == 2.5
    assert sma(v, 6) is None
    assert sma(v, 3, back=3) is None


def test_rsi_extremes_and_insufficient_data():
    assert rsi_wilder(list(range(1, 20))) == 100.0          # ขึ้นทุกแท่ง
    assert rsi_wilder(list(range(20, 1, -1))) == 0.0        # ลงทุกแท่ง
    assert rsi_wilder([5.0] * 20) == 100.0                  # นิ่งสนิท: TradingView ให้ 100 (down == 0)
    assert rsi_wilder([1.0] * 14) is None                   # ต้องมี n+1 แท่ง


def test_rsi_matches_hand_computed_wilder():
    # n=2: deltas +1,-1,+2 -> seed gain=0.5 loss=0.5 -> gain=(0.5+2)/2=1.25 loss=0.25 -> RS=5
    assert rsi_wilder([10, 11, 10, 12], n=2) == pytest.approx(100 - 100 / 6)


def test_pct_change_refuses_non_positive_base():
    assert pct_change(0, 5) is None
    assert pct_change(100, 110) == pytest.approx(10.0)


# ---------- score ----------

def test_zigzag_uptrend_beating_flat_benchmark_scores_six():
    r = score_from_daily(_daily(_zigzag_up, DAYS), _daily(_flat, DAYS), ASOF)
    assert r["status"] == "ok"
    assert r["score"] == 6, [c for c in r["criteria"] if not c["passed"]]
    assert r["tier"] == "trend_up"


def test_straight_line_up_fails_only_rsi():
    """ขึ้นทุกสัปดาห์ไม่มีพัก = RSI 100 = 'ไล่ราคาที่ร้อนแล้ว' — แนวโน้มดีไม่ได้แปลว่าจังหวะดี"""
    r = score_from_daily(_daily(lambda i: 100 * 1.001 ** i, DAYS), _daily(_flat, DAYS), ASOF)
    failed = [c["key"] for c in r["criteria"] if not c["passed"]]
    assert failed == ["T6"]
    assert r["tier"] == "trend_up"                  # 5/6 ยังเป็นขาขึ้น แต่ข้อที่ตกต้องเห็นได้


def test_downtrend_fails_trend_criteria():
    r = score_from_daily(_daily(lambda i: 100 * 0.999 ** i, DAYS), _daily(_flat, DAYS), ASOF)
    by = {c["key"]: c for c in r["criteria"]}
    assert not by["T1"]["passed"] and not by["T2"]["passed"] and not by["T3"]["passed"]
    assert not by["T4"]["passed"] and not by["T5"]["passed"]
    assert r["tier"] == "trend_down"


def test_margin_sign_always_agrees_with_passed():
    for f in (_zigzag_up, lambda i: 100 * 0.999 ** i, lambda i: 100 * 1.001 ** i):
        r = score_from_daily(_daily(f, DAYS), _daily(_flat, DAYS), ASOF)
        for c in r["criteria"]:
            assert c["passed"] == (c["margin"] >= 0) or c["margin"] == 0, c


def test_too_little_history_is_unmeasurable_not_zero():
    r = score_from_daily(_daily(_zigzag_up, 200), _daily(_flat, 200), START + timedelta(days=200))
    assert r["score"] is None
    assert r["status"] == "unmeasurable"
    assert "Week" in r["reason"]


def test_missing_benchmark_month_is_unmeasurable_not_misaligned():
    """benchmark ขาดเดือนที่ต้องใช้ -> ห้ามเทียบตามตำแหน่ง (จะเทียบผิดเดือนแบบเงียบ)"""
    week = [(f"w{i}", 100.0 + i) for i in range(MIN_WEEKS)]
    month = [(f"2025-{m:02d}-28", 100.0 + m) for m in range(1, 13)] + [("2026-01-31", 120.0)]
    bench = month[1:]                                  # ขาดเดือนแรกที่ momentum ต้องใช้
    r = score_from_bars(week, month, bench)
    assert r["score"] is None
    assert "VT" in r["reason"]


def test_crypto_uses_sunday_weeks():
    r = score_from_daily(_daily(_zigzag_up, DAYS, crypto=True), _daily(_flat, DAYS), ASOF, "crypto")
    assert date.fromisoformat(r["last_week"]).weekday() == B.SUNDAY
    assert r["asset_type"] == "crypto"


def test_borderline_flags_a_pass_that_barely_passed():
    """ราคาเพิ่งข้ามเส้นเฉลี่ย 40 สัปดาห์มานิดเดียว: ผ่าน แต่ต้องบอกว่าเฉียด"""
    week = [("w", 100.0)] * (MIN_WEEKS - 1) + [("w", 101.0)]
    month = [(f"m{i}", 100.0) for i in range(13)]
    r = score_from_bars(week, month, month)
    t1 = r["criteria"][0]
    assert t1["key"] == "T1" and t1["passed"] and t1["borderline"]


def test_technical_result_has_no_field_combined_with_health():
    """สองความเห็นวางคู่กัน ห้ามบวกกัน (TECHNICAL_LAYER.md ข้อ 2)"""
    r = score_from_daily(_daily(_zigzag_up, DAYS), _daily(_flat, DAYS), ASOF)
    assert not any("health" in k or "total" in k or "combined" in k for k in r)
    assert r["max"] == 6


# ---------- 53.2: ภาพ + Discord (ไม่ยิงเน็ตจริง) ----------

def _evaluated():
    from src.technical.score import evaluate
    return evaluate(_daily(_zigzag_up, DAYS), _daily(_flat, DAYS), ASOF)


def test_chart_renders_a_real_png_for_scored_and_unmeasurable_results():
    from src.technical.chart import render_png
    week, month, r = _evaluated()
    assert render_png("TEST", week, month, r)[:8] == b"\x89PNG\r\n\x1a\n"
    short = score_from_daily(_daily(_zigzag_up, 200), _daily(_flat, 200), START + timedelta(days=200))
    assert render_png("NEW", week[:20], month[:5], short)[:4] == b"\x89PNG"


def test_message_speaks_plain_language_not_tool_jargon():
    """กติการายงาน: คนอ่านต้องไม่เจอ SMA40W / 12-1 / pp — ต้องเจอ 'ถือ 100 บาท เป็นเท่าไหร่'"""
    from src.technical.notify import format_message
    msg = format_message("TEST", _evaluated()[2])
    for jargon in ("SMA", "12-1", " pp", "margin"):
        assert jargon not in msg
    assert "100 บาท เป็น" in msg
    assert "ไม่ใช่สัญญาณซื้อขาย" in msg


def test_message_for_unmeasurable_gives_the_reason():
    from src.technical.notify import format_message
    r = score_from_daily(_daily(_zigzag_up, 200), _daily(_flat, 200), START + timedelta(days=200))
    msg = format_message("NEW", r)
    assert "วัดไม่ได้" in msg and r["reason"] in msg


def test_multipart_body_carries_both_the_text_and_the_image():
    import json
    from src.notify.discord import _multipart
    body, ctype = _multipart({"content": "สวัสดี"}, "a.png", b"\x89PNGDATA")
    boundary = ctype.split("boundary=")[1]
    assert body.count(f"--{boundary}".encode()) == 3          # 2 ส่วน + ตัวปิด
    assert body.endswith(f"--{boundary}--\r\n".encode())
    assert b'name="files[0]"; filename="a.png"' in body and b"\x89PNGDATA" in body
    assert json.dumps({"content": "สวัสดี"}).encode() in body


def test_post_image_skips_quietly_without_webhook(monkeypatch):
    from src.notify import discord
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert discord.post_image("x", b"png") is False


def test_send_posts_png_to_the_technical_channel(monkeypatch):
    from src.notify import discord
    from src.technical import notify
    sent = {}

    class _Resp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        sent["url"], sent["body"], sent["ctype"] = req.full_url, req.data, req.headers["Content-type"]
        return _Resp()

    monkeypatch.setenv(notify.WEBHOOK_ENV, "https://discord.test/technical")
    monkeypatch.setattr(discord.urllib.request, "urlopen", fake_urlopen)
    week, month, r = _evaluated()
    assert notify.send("BTC-USD", week, month, r) is True
    assert sent["url"] == "https://discord.test/technical"
    assert sent["ctype"].startswith("multipart/form-data")
    assert b"\x89PNG" in sent["body"] and b"BTC_USD_" in sent["body"]


# ---------- 53.3: radar — ส่งเฉพาะตัวที่เปลี่ยน ----------

def _fetcher(prices: dict):
    """fetch ปลอม: {ticker: list รายวัน | None}. VT เป็นเส้นแบนเสมอถ้าไม่ระบุ"""
    table = {"VT": _daily(_flat, DAYS), **prices}
    return lambda t: table.get(t)


UP = _daily(_zigzag_up, DAYS)
DOWN = _daily(lambda i: 100 * 0.999 ** i, DAYS)


def test_first_run_records_silently_instead_of_announcing_everything(tmp_path):
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    r = scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    assert r.changes == [] and r.bootstrapped == ["AAA"]


def test_tier_flip_is_reported_with_before_and_after(tmp_path):
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    same = scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    assert same.changes == []                                   # ไม่เปลี่ยน = ไม่ส่ง
    flipped = scan([("AAA", "stock")], _fetcher({"AAA": DOWN}), ASOF, "v1", db)
    (c,) = flipped.changes
    assert (c.before["tier"], c.result["tier"]) == ("trend_up", "trend_down")
    assert c.rule_change is False and c.week and c.month       # ภาพวาดจากแท่งชุดเดียวกับคะแนน


def test_unmeasurable_blip_does_not_overwrite_state_or_fire_twice(tmp_path):
    """ok -> วัดไม่ได้ -> ok ต้องไม่กลายเป็น 'เปลี่ยน' สองครั้งที่ไม่มีอะไรเกิดขึ้นจริง"""
    from src.technical import store
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    blip = scan([("AAA", "stock")], _fetcher({"AAA": UP[-30:]}), ASOF, "v1", db)
    assert blip.unmeasurable == ["AAA"] and blip.changes == []
    assert store.states(db)["AAA"]["tier"] == "trend_up"
    back = scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    assert back.changes == []


def test_fetch_failure_is_our_problem_not_the_tickers_result(tmp_path):
    from src.technical import store
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    r = scan([("AAA", "stock")], _fetcher({"AAA": None}), ASOF, "v1", db)
    assert r.fetch_failed == ["AAA"] and r.unmeasurable == []
    assert store.states(db) == {}


def test_missing_benchmark_aborts_the_whole_run_without_recording(tmp_path):
    from src.technical import store
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    r = scan([("AAA", "stock")], lambda t: None if t == "VT" else UP, ASOF, "v1", db)
    assert r.aborted and store.states(db) == {}


def test_flip_in_the_same_run_as_a_rule_change_says_so(tmp_path):
    from src.technical.notify import format_message
    from src.technical.radar import scan
    db = tmp_path / "t.db"
    scan([("AAA", "stock")], _fetcher({"AAA": UP}), ASOF, "v1", db)
    (c,) = scan([("AAA", "stock")], _fetcher({"AAA": DOWN}), ASOF, "v2", db).changes
    assert c.rule_change is True
    msg = format_message("AAA", c.result, c.before, c.rule_change)
    assert "เปลี่ยนจาก" in msg and "แก้เกณฑ์" in msg


def test_tech_version_ignores_comments_but_covers_the_scoring_files():
    from src.technical.radar import TECH_MODULES, tech_version
    assert "src/technical/score.py" in TECH_MODULES
    assert len(tech_version()) == 12


def test_crypto_is_fetched_as_the_coin_not_the_same_named_etf(tmp_path):
    """'BTC' ใน yfinance คือ ETF ราคา $37 — watchlist เก็บ 'BTC' จึงต้องดึง 'BTC-USD'
    แต่บันทึกผลภายใต้ชื่อเดิมใน watchlist"""
    from src.technical import store
    from src.technical.radar import scan
    asked = []
    table = {"VT": _daily(_flat, DAYS), "BTC-USD": _daily(_zigzag_up, DAYS, crypto=True)}

    def fetch(t):
        asked.append(t)
        return table.get(t)

    db = tmp_path / "t.db"
    r = scan([("BTC", "crypto"), ("AAPL", "stock")], fetch, ASOF, "v1", db)
    assert "BTC-USD" in asked and "BTC" not in asked and "AAPL" in asked
    assert r.bootstrapped == ["BTC"] and "BTC" in store.states(db)
