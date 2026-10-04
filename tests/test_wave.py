"""ตัวตรวจ count คลื่น — offline ล้วน: ราคาสังเคราะห์ที่วางจุดกลับตัวไว้เองจึงรู้คำตอบล่วงหน้า.

สิ่งที่ชุดนี้คุ้มครอง:
- ใช้ราคาจริงจากแท่ง ไม่ใช่เลขที่ผู้ใช้อ่านจากจอ
- กฎเหล็กผิดคือผิด — รวมถึงกรณีที่จุดลึกสุดของคลื่น 4 ไม่ใช่จุดที่มาร์ก (สามเหลี่ยม)
- ทุกฉากที่ยังไม่ตายต้องโชว์ พร้อมราคาที่ทำให้ตาย; ไม่มีเปอร์เซ็นต์ความน่าจะเป็น
- ขาลงใช้โค้ดชุดเดียวกัน (กลับทิศถูก)
"""
from datetime import datetime, timedelta

from src.wave.analysis import analyze, check_rules, resolve
from src.wave.candles import Candle, resample_4h
from src.wave.chart import ema, render_png
from src.wave.count import build
from src.wave.notify import format_message
from src.wave.pivots import zigzag

T0 = datetime(2026, 9, 1)


def path(points: list[tuple[int, float]]) -> list[Candle]:
    """แท่ง 1H ที่ราคาเดินเป็นเส้นตรงระหว่างจุด (ชั่วโมงที่, ราคา) — ยอด/ก้นอยู่ตรงจุดที่วางพอดี"""
    out = []
    for (h0, p0), (h1, p1) in zip(points, points[1:]):
        for h in range(h0, h1):
            a = p0 + (p1 - p0) * (h - h0) / (h1 - h0)
            b = p0 + (p1 - p0) * (h + 1 - h0) / (h1 - h0)
            out.append(Candle(T0 + timedelta(hours=h), a, max(a, b), min(a, b), b))
    return out


def at(h: int) -> datetime:
    return T0 + timedelta(hours=h)


# impulse ขาขึ้นแบบเดียวกับ BTC ตอนนี้: 0→1→2→3→4 (สามเหลี่ยม ก้นลึกสุดก่อนจุด 4) → ขา i → ย่อ ii
BASE = [(0, 100.0), (40, 107.0), (50, 105.0), (80, 112.4), (100, 108.5), (120, 110.5),
        (140, 107.6), (150, 109.6), (160, 108.2)]          # A-B-C-D-E: E (108.2) สูงกว่าก้น C (107.6)
MARKS = [("0", at(0)), ("1", at(40)), ("2", at(50)), ("3", at(80)), ("4", at(160))]


def report(extra: list[tuple[int, float]], shape: str | None = "triangle", marks=MARKS, base=BASE,
           direction: str = "up"):
    candles = path(base + extra)
    pivots = resolve(candles, marks, direction, window_h=3)
    return analyze("TEST", "TEST-USD", direction, pivots, candles, shape)


# ---------- จุดและแท่ง ----------

def test_snap_uses_the_real_extreme_not_the_marked_time():
    candles = path(BASE)
    (p,) = resolve(candles, [("0", at(2))], "up", window_h=3)    # มาร์กคลาดไป 2 ชม.
    assert p.ts == at(0) and p.price == 100.0


def test_zigzag_never_puts_a_high_and_a_low_on_the_same_candle():
    z = zigzag(path(BASE), 0.01)
    assert len({p.ts for p in z}) == len(z)
    assert [p.kind for p in z][:4] == ["L", "H", "L", "H"]


def test_resample_4h_groups_on_utc_boundaries():
    c4 = resample_4h(path([(0, 1.0), (8, 9.0)]))
    assert [c.ts.hour for c in c4] == [0, 4]
    assert c4[0].open == 1.0 and c4[0].close == 5.0 and c4[1].high == 9.0


def test_ema_seeds_with_sma_like_pine():
    e = ema([1.0, 2.0, 3.0, 4.0], 3)
    assert e[:2] == [None, None] and e[2] == 2.0 and e[3] == 0.5 * 4 + 0.5 * 2.0


# ---------- กฎเหล็ก ----------

def test_valid_impulse_passes_every_rule():
    rep = report([(170, 112.0)])
    assert rep.valid, [r for r in rep.rules if not r.ok]


def test_wave2_below_wave1_start_fails():
    base = [(0, 100.0), (40, 107.0), (50, 99.0), (80, 112.0), (100, 108.0)]
    candles = path(base)
    pivots = resolve(candles, MARKS[:4], "up", 3)
    rules = check_rules(pivots, candles, 1)
    assert not next(r for r in rules if r.text.startswith("คลื่น 2")).ok


def test_wave4_overlap_is_checked_at_its_deepest_point_not_the_marked_end():
    """สามเหลี่ยมจบที่ E ซึ่งสูงกว่าก้นจริง — ถ้าเช็กแค่จุดที่มาร์ก จะปล่อย count ที่ผิดกฎผ่าน"""
    base = BASE[:5] + [(120, 110.5), (140, 106.5), (150, 109.6), (160, 108.2)]  # ก้น C หลุดยอดคลื่น 1 (107)
    rep = report([(170, 112.0)], base=base)
    rule = next(r for r in rep.rules if r.text.startswith("คลื่น 4"))
    assert not rule.ok and "106" in rule.detail
    assert rep.scenarios == []                                         # ผิดกฎแล้ว ไม่ไล่ฉากต่อ


def test_wave3_must_exceed_wave1():
    base = [(0, 100.0), (40, 107.0), (50, 104.0), (80, 106.5), (100, 105.0)]
    candles = path(base)
    rules = check_rules(resolve(candles, MARKS[:4], "up", 3), candles, 1)
    assert not next(r for r in rules if r.text.startswith("คลื่น 3 ไป")).ok


# ---------- ฉากทัศน์ในคลื่น 5 ----------

def test_between_the_two_kill_levels_both_scenarios_stay_alive():
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])         # ขา i ไม่เกินยอด 3 แล้วย่อ
    keys = {s.key: s for s in rep.scenarios}
    assert keys["A"].alive and keys["B"].alive
    assert keys["A"].kill_level == 108.2                               # ii ห้ามหลุดจุดเริ่ม i
    assert keys["B"].kill_level == rep.sub["s1"] == 112.3
    assert "truncated" in keys["B"].title
    assert any("truncated" in e.text and e.leans == "A" for e in rep.evidence)


def test_falling_below_the_marked_wave4_end_says_the_count_must_change():
    rep = report([(180, 112.3), (200, 107.9)])
    assert "ไม่ใช่จุดจบคลื่น 4" in rep.state
    assert [s.key for s in rep.scenarios] == ["C"]


def test_wave5_targets_never_include_a_length_that_breaks_the_wave3_rule():
    """คลื่น 3 สั้นกว่าคลื่น 1 -> คลื่น 5 ต้องสั้นกว่าคลื่น 3; เป้าที่เลยเพดานนั้นห้ามโชว์"""
    base = [(0, 100.0), (40, 110.0), (50, 102.0), (80, 111.5), (100, 110.5)]   # 1 = 10, 3 = 9.5
    marks = MARKS[:4] + [("4", at(100))]
    rep = report([(110, 112.5), (120, 111.5)], shape=None, base=base, marks=marks)
    cap = 110.5 + 9.5
    targets = {t: x for s in rep.scenarios for t, x in s.targets if t.startswith("5 =")}
    assert targets and all(x < cap for x in targets.values())
    assert "5 = 1×คลื่น 1" not in targets                         # 110.5 + 10 = 120.5 เลยเพดาน


def test_down_impulse_uses_the_same_rules_mirrored():
    base = [(h, 300 - p) for h, p in BASE]
    rep = report([(180, 187.7), (190, 191.1), (200, 190.5)], base=base, direction="down")   # กระจกของขาขึ้น
    assert rep.valid
    a = next(s for s in rep.scenarios if s.key == "A")
    assert a.alive and a.kill_level == 191.8 and "ทะลุ" in a.kill_text


# ---------- ข้อความ / ภาพ / ไฟล์ count ----------

def test_message_has_kill_levels_and_no_probabilities_or_trade_calls():
    msg = format_message(report([(180, 112.3), (190, 108.9), (200, 109.5)]))
    assert "ผิดเมื่อ" in msg and "สรุประดับ" in msg
    plain = msg.replace("ขาย่อย", "")                 # "ขาย่อย" ไม่ใช่คำว่าขาย
    for banned in ("โอกาส", "ความน่าจะเป็น", "ซื้อ", "ขาย"):
        assert banned not in plain


def test_chart_renders_png():
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    assert render_png(rep, path(BASE + [(180, 112.3), (190, 108.9), (200, 109.5)]))[:4] == b"\x89PNG"


def test_build_from_spec_with_parent_note():
    hourly = path(BASE + [(180, 112.3), (190, 108.9), (200, 109.5)])

    def fake(symbol, interval, period):
        return hourly

    spec = {"symbol": "TEST-USD", "name": "ขาว", "direction": "up", "snap_hours": 3,
            "wave4": "triangle", "marks": [[l, t.isoformat()] for l, t in MARKS],
            "parent": {"name": "เหลือง", "snap_hours": 3, "marks": [[l, t.isoformat()] for l, t in MARKS]}}
    rep = build(spec, fake)
    assert rep.parent is not None and rep.parent.valid
    assert "ฉาก B" in rep.parent_note and "เหลือง" in rep.parent_note


# ---------- เทรนด์หลาย TF + divergence ----------

def _daily(prices: list[float], start: datetime = datetime(2020, 1, 1)) -> list[Candle]:
    out, prev = [], prices[0]
    for i, p in enumerate(prices):
        out.append(Candle(start + timedelta(days=i), prev, max(prev, p), min(prev, p), p))
        prev = p
    return out


def test_rsi_series_last_value_matches_the_week_month_layer():
    """สองที่ในโปรเจกต์ต้องให้ RSI เดียวกันจากราคาเดียวกัน"""
    from src.technical.indicators import rsi_wilder
    from src.wave.trend import rsi_series
    import math
    xs = [100 + 10 * math.sin(i / 3) + i * 0.2 for i in range(80)]
    assert abs(rsi_series(xs)[-1] - rsi_wilder(xs)) < 1e-9


def test_macd_signal_is_sma9_like_the_users_script():
    from src.wave.trend import ema, macd_series
    xs = [float(i % 7 + i) for i in range(60)]
    m, sig = macd_series(xs)
    assert sig[-1] == sum(m[-9:]) / 9
    assert m[-1] == ema(xs, 12)[-1] - ema(xs, 26)[-1]


def _leg(start: float, n: int, step: float, dip: float) -> list[float]:
    """ขาราคาที่มีแท่งสวนทุกแท่งที่ 3 — ขาตรงๆ ไม่มีแท่งสวนเลย RSI จะติด 100 ตลอดและไม่เกิดยอด"""
    out, p = [], start
    for i in range(n):
        p += -dip if i % 3 == 2 else step
        out.append(p)
    return out


def test_bearish_divergence_is_found_and_confirmed_five_bars_late():
    """ยอดแรกพุ่งแรง (RSI สูง) ยอดสองสูงกว่าแต่ไต่ช้ากว่า (RSI ต่ำกว่า) = bearish divergence"""
    from src.wave.trend import divergences
    a = _leg(100, 20, 1.0, 0.5)
    b = _leg(a[-1], 12, 4.0, 1.0)            # พุ่งแรง -> ยอด 140
    c = _leg(b[-1], 10, -2.0, -1.0)
    d = _leg(c[-1], 21, 1.6, 1.0)            # ไต่ช้ากว่า -> ยอด ~144.4
    e = _leg(d[-1], 12, -2.0, -1.0)
    cs = _daily(a + b + c + d + e)
    (dv,) = [x for x in divergences("D", cs, "RSI") if x.kind == "bear"]
    assert dv.price_now > dv.price_prev and dv.ind_now < dv.ind_prev
    i = next(k for k, c in enumerate(cs) if c.ts == dv.pivot_ts)
    assert cs[i + 5].ts == dv.confirmed_ts                # ยืนยันช้า 5 แท่งเสมอ
    # ตัดข้อมูลให้เหลือไม่ถึง 5 แท่งหลังยอด -> ต้องยังไม่เห็น (ไม่ใช้ข้อมูลอนาคต)
    assert not [x for x in divergences("D", cs[:i + 5], "RSI") if x.pivot_ts == dv.pivot_ts]


def test_trend_reads_up_down_and_mixed():
    from src.wave.trend import read
    import math
    wave = lambda i: 8 * math.sin(i / 6)
    up = read("D", _daily([100 + i * 0.5 + wave(i) for i in range(400)]))
    down = read("D", _daily([400 - i * 0.5 + wave(i) for i in range(400)]))
    assert up.state == "up" and down.state == "down"
    assert {"EMA50", "EMA200"} <= set(up.lines)
    turn = read("D", _daily([100 + i * 0.5 + wave(i) for i in range(300)] +
                            [250 - i * 1.5 + wave(i) for i in range(40)]))
    assert turn.state in ("mixed", "down")


def test_timeframes_only_include_closed_bars():
    from src.wave.trend import timeframes
    daily = _daily([100.0] * 70, start=datetime(2026, 8, 1))          # 1 ส.ค. – 9 ต.ค.
    tfs = timeframes(daily, [], asof=datetime(2026, 10, 3, 14), crypto=True)
    assert tfs["M"][-1].ts.month == 9                                  # ต.ค. ยังไม่จบ
    assert tfs["D"][-1].ts == datetime(2026, 10, 2)                    # วันนี้ยังไม่ปิด
    assert all(c.ts < datetime(2026, 9, 28) for c in tfs["W"])         # สัปดาห์ 28 ก.ย.–4 ต.ค. ยังไม่จบ


def test_scenarios_carry_the_direction_they_expect():
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    bias = {s.key: s.bias for s in rep.scenarios}
    assert bias == {"A": "up", "B": "down"}


def test_summary_fits_one_discord_message_with_the_image():
    from src.notify.discord import DISCORD_CONTENT_LIMIT
    from src.wave.notify import format_summary
    from src.wave.trend import TrendRead
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    rep.trend = [TrendRead("D", "up", 1.0), TrendRead("W", "mixed", 1.0)]
    s = format_summary(rep)
    assert len(s) <= DISCORD_CONTENT_LIMIT and "ยังตัดสินไม่ได้" in s and "D 🟢" in s


def test_equal_waves_1_and_3_add_fifth_wave_extension_targets():
    """1 ≈ 3 (ไม่มีขาไหนยืด) -> ตำราคาดว่า 5 ยืด: เป้า 1× และ 1.618× ของระยะ 0→3 จากจุดจบคลื่น 4"""
    base = [(0, 100.0), (40, 107.0), (50, 105.0), (80, 112.3), (100, 108.5), (120, 110.5),
            (140, 107.6), (150, 109.6), (160, 108.2)]                 # คลื่น 1 = 7.0, คลื่น 3 = 7.3
    rep = report([(180, 112.0), (190, 109.0), (200, 109.5)], base=base)
    a = {t: x for t, x in next(s for s in rep.scenarios if s.key == "A").targets}
    assert abs(a["5 ยืด = 1×(0→3)"] - (108.2 + 12.3)) < 1e-6
    assert abs(a["5 ยืด = 1.618×(0→3)"] - (108.2 + 1.618 * 12.3)) < 1e-6


def test_no_extension_targets_when_wave3_already_extended():
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)],
                 base=[(0, 100.0), (40, 103.0), (50, 101.5), (80, 112.4), (100, 108.5), (120, 110.5),
                       (140, 107.6), (150, 109.6), (160, 108.2)])     # คลื่น 3 = 10.9 เทียบคลื่น 1 = 3
    a = [t for t, _ in next(s for s in rep.scenarios if s.key == "A").targets]
    assert not any(t.startswith("5 ยืด") for t in a)


# ---------- Phase 54.2: เครื่องนับเอง / มุมมอง Claude / snapshot ----------

def _anchor(candles):
    from src.wave.pivots import Pivot
    c = min(candles[:5], key=lambda x: x.low)
    return Pivot("0", c.ts, c.low, "L")


def test_auto_finds_the_users_impulse_and_flags_it():
    from src.wave.auto import find_counts
    candles = path(BASE + [(180, 112.3), (190, 108.9), (200, 109.5)])
    user = resolve(candles, MARKS, "up", 3)
    counts = find_counts(candles, _anchor(candles), pcts=(0.005, 0.01, 0.02), user=user)
    mine = [c for c in counts if c.matches_user]
    assert mine and mine[0].pattern == "impulse"
    assert all(c.pattern in ("impulse", "zigzag", "flat") for c in counts)


def test_auto_counts_never_break_the_hard_rules():
    from src.wave.auto import find_counts
    candles = path(BASE + [(180, 112.3), (190, 108.9), (200, 109.5)])
    for c in find_counts(candles, _anchor(candles), pcts=(0.005, 0.01, 0.02)):
        v = [p.price for p in c.pivots]
        if c.pattern == "impulse":
            assert v[2] > v[0] and v[3] > v[1] and (len(v) < 5 or v[4] > v[1])
        if c.pattern == "zigzag" and len(v) >= 3:
            assert v[0] < v[2] < v[1]


def test_unfinished_pattern_does_not_win_just_by_having_fewer_checks():
    """1/1 ข้อ ต้องไม่ชนะ 3/4 ข้อ — 'ยังตรวจไม่ได้' ไม่ใช่ 'ผ่าน'"""
    from src.wave.auto import AutoCount, Guide
    few = AutoCount("zigzag", [], [], False, [Guide("x", True, "")], "", None, "")
    many = AutoCount("impulse", [], [], False, [Guide("x", True, "")] * 3 + [Guide("y", False, "")], "", None, "")
    assert few.unchecked == 2 and many.unchecked == 1
    assert many.score > few.score


def test_pick_keeps_the_users_count_even_when_ranked_low():
    from src.wave.auto import AutoCount, pick
    counts = [AutoCount("impulse", [], [], False, [], "", None, "") for _ in range(15)]
    counts[-1].matches_user = True
    assert counts[-1] in pick(counts, n=5)


def test_auto_mirrors_for_down_moves():
    from src.wave.auto import find_counts
    from src.wave.pivots import Pivot
    candles = path([(h, 300 - p) for h, p in BASE] + [(180, 187.7), (190, 191.1), (200, 190.5)])
    top = max(candles[:5], key=lambda x: x.high)
    counts = find_counts(candles, Pivot("0", top.ts, top.high, "H"), pcts=(0.005, 0.01, 0.02))
    imp = [c for c in counts if c.pattern == "impulse"]
    assert imp and all(c.pivots[1].price < c.pivots[0].price for c in imp)   # คลื่น 1 ลง


def test_claude_view_roundtrip_carries_its_age(tmp_path, monkeypatch):
    from src.wave import claude
    monkeypatch.setattr(claude, "VIEW_DIR", tmp_path)
    claude.save_view("btc", "**มุมมอง**\n- ข้อหนึ่ง", 84842.0, asof=datetime(2026, 10, 3, 15, 0), by="Claude")
    v = claude.load_view("btc", now=datetime(2026, 10, 4, 3, 0))
    assert v["text"].startswith("**มุมมอง**") and v["price"] == "84,842" and v["age_hours"] == 12.0
    assert claude.load_view("missing") is None


def test_pack_contains_the_same_report_text_and_forbids_trade_calls(tmp_path, monkeypatch):
    from src.wave import claude
    monkeypatch.setattr(claude, "PACK_DIR", tmp_path)
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    text = format_message(rep)
    pack = claude.make_pack("btc", rep, text).read_text(encoding="utf-8")
    assert text in pack and "ห้ามแนะนำซื้อ/ขาย" in pack


def test_snapshot_roundtrip_and_api_guards(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.wave import claude, snapshot
    monkeypatch.setattr(snapshot, "SNAP_DIR", tmp_path)
    monkeypatch.setattr(claude, "VIEW_DIR", tmp_path / "claude")
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    snapshot.write("btc", rep, b"\x89PNGw", b"\x89PNGa", "msg")
    client = TestClient(app)
    assert client.get("/api/waves").json()["stems"] == ["btc"]
    body = client.get("/api/wave/btc").json()
    assert body["available"] and body["report"]["symbol"] == "TEST-USD" and body["claude"] is None
    assert client.get("/api/wave/btc/image/auto").content == b"\x89PNGa"
    assert client.get("/api/wave/nope").json()["available"] is False
    assert client.get("/api/wave/btc/image/other").status_code == 404
    assert client.get("/api/wave/..%2Fx/image/wave").status_code == 404


# ---------- แจ้งเตือนเมื่อแท่ง 4H ปิดผ่านเส้น (ข้อ 2) ----------

def _bar(h: int, close: float) -> Candle:
    return Candle(T0 + timedelta(hours=h), close, close, close, close)


def test_scenarios_know_which_side_their_lines_are_on():
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    a = next(s for s in rep.scenarios if s.key == "A")
    b = next(s for s in rep.scenarios if s.key == "B")
    assert (a.kill_side, a.confirm_side, a.confirm_level) == ("below", "above", 112.3)
    assert (b.kill_side, b.confirm_side, b.confirm_level) == ("above", "below", 108.2)


def test_first_run_has_nothing_to_compare_so_it_stays_quiet():
    from src.wave.alerts import crossings
    assert crossings(None, [_bar(0, 1.0)]) == []


def test_a_closed_bar_beyond_last_runs_kill_line_fires_once():
    from src.wave.alerts import crossings, levels_of
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    prev = {"last_bar": (T0 + timedelta(hours=200)).isoformat(), "levels": levels_of(rep)}
    bars = [_bar(196, 107.0),                      # ก่อนรอบก่อน — ไม่นับ (เห็นไปแล้ว)
            _bar(204, 109.0), _bar(208, 108.0), _bar(212, 107.5)]
    hits = crossings(prev, bars)
    # เส้นเดียวกัน (108.2) คือเส้นตายของ A และเส้นยืนยันของ B — แจ้งทั้งคู่ ที่แท่งแรกที่ผ่าน ครั้งเดียว
    assert sorted((h.key, h.kind, h.close) for h in hits) == [("A", "kill", 108.0), ("B", "confirm", 108.0)]


def test_wick_through_the_line_does_not_count_only_the_close():
    from src.wave.alerts import crossings, levels_of
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    prev = {"last_bar": (T0 + timedelta(hours=200)).isoformat(), "levels": levels_of(rep)}
    wick = Candle(T0 + timedelta(hours=204), 109.0, 109.2, 107.0, 109.1)       # low แทงเส้น 108.2 แต่ปิดเหนือ
    assert crossings(prev, [wick]) == []


def test_confirm_line_crossing_is_reported_as_clearer_not_dead():
    from src.wave.alerts import crossings, format_alert, levels_of
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    prev = {"last_bar": (T0 + timedelta(hours=200)).isoformat(), "levels": levels_of(rep)}
    hits = crossings(prev, [_bar(204, 112.6)])
    assert {(h.key, h.kind) for h in hits} == {("A", "confirm"), ("B", "kill")}
    text = format_alert("TEST", hits, rep)
    assert "ชัดขึ้น" in text and "ตายแล้ว" in text and "ปิด" in text


def test_alert_state_roundtrip(tmp_path):
    from src.wave import alerts
    rep = report([(180, 112.3), (190, 108.9), (200, 109.5)])
    alerts.save_state("btc", rep, [_bar(200, 109.5)], tmp_path)
    st = alerts.load_state("btc", tmp_path)
    assert st["last_bar"] == (T0 + timedelta(hours=200)).isoformat() and {l["key"] for l in st["levels"]} == {"A", "B"}
    assert alerts.load_state("none", tmp_path) is None
