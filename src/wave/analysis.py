"""ตรวจ count + ไล่ฉากทัศน์ที่ราคายังไม่ฆ่า. ฟังก์ชันบริสุทธิ์ทั้งหมด (รับแท่ง+จุด คืนรายงาน).

ทิศทางใช้ตัวคูณ s (+1 ขาขึ้น, −1 ขาลง) — "เลยไปทางเทรนด์" = s*(a−b) > 0 — โค้ดชุดเดียวใช้ได้
ทั้ง impulse ขึ้นและลง ไม่ต้องเขียนสองชุดที่วันหนึ่งจะแก้ไม่ตรงกัน

แยกสามชั้นให้ชัดเพราะน้ำหนักต่างกันมาก:
- **กฎ (rules)**      ผิด = count นั้นใช้ไม่ได้ จบ
- **ฉาก (scenarios)** ทุกการตีความที่ยังไม่ผิดกฎ + ราคาที่ทำให้ตาย + เป้า
- **หลักฐาน (evidence)** แนวโน้มตามตำรา ไม่ใช่กฎ — แสดงเป็นข้อเท็จจริง ไม่รวมเป็นเปอร์เซ็นต์
"""
from dataclasses import dataclass, field
from datetime import datetime

from src.technical.indicators import rsi_wilder
from src.wave.candles import Candle, resample_4h
from src.wave.pivots import Pivot, snap, zigzag

LEGS_PCT_OF_MOVE = 0.15   # นับขาย่อย: ย้อนเกิน 15% ของความยาวขานั้นถึงนับเป็นขาใหม่
EQUAL_TOL = 0.10          # "คลื่น 1 ≈ คลื่น 3" = ยาวต่างกันไม่เกิน 10%


@dataclass
class Rule:
    text: str
    ok: bool
    detail: str


@dataclass
class Scenario:
    key: str
    title: str
    meaning: str
    alive: bool
    kill_level: float | None
    kill_text: str
    confirm_text: str = ""
    targets: list[tuple[str, float]] = field(default_factory=list)
    bias: str = ""        # "up" | "down" — ทิศที่ฉากนี้คาดต่อจากนี้ (ไว้เทียบกับเทรนด์ TF ใหญ่)


@dataclass
class Evidence:
    text: str
    leans: str            # "A" | "B" | "-" — เข้าทางฉากไหน (ตามตำรา ไม่ใช่กฎ)


@dataclass
class Report:
    name: str
    symbol: str
    direction: str
    pivots: list[Pivot]
    last: Candle
    rules: list[Rule]
    state: str
    scenarios: list[Scenario]
    evidence: list[Evidence]
    sub: dict = field(default_factory=dict)       # ขาย่อยหลังคลื่น 4 (ถ้ามี)
    parent: "Report | None" = None
    parent_note: str = ""
    trend: list = field(default_factory=list)     # list[trend.TrendRead] — M/W/D/4H
    divergences: list = field(default_factory=list)
    auto: list = field(default_factory=list)      # list[auto.AutoCount] — เครื่องนับเองระดับนี้

    @property
    def valid(self) -> bool:
        return all(r.ok for r in self.rules)


def fmt(x: float) -> str:
    return f"{x:,.0f}"


def resolve(candles: list[Candle], marks: list[tuple[str, datetime]], direction: str,
            window_h: float) -> list[Pivot]:
    """จุดที่ผู้ใช้มาร์ก -> ราคาจริง. ขาขึ้น: ป้ายคู่ (0,2,4) = ก้น, ป้ายคี่ = ยอด."""
    up = direction == "up"
    out = []
    for i, (label, at) in enumerate(marks):
        kind = ("L" if i % 2 == 0 else "H") if up else ("H" if i % 2 == 0 else "L")
        p = snap(candles, label, at, kind, window_h)
        if p is None:
            raise ValueError(f"ไม่มีแท่งราคารอบ {at} สำหรับจุด {label}")
        out.append(p)
    return out


def _extreme_between(candles: list[Candle], a: datetime, b: datetime, s: int) -> float:
    """จุดที่สวนเทรนด์ลึกที่สุดระหว่าง a..b (ขาขึ้น = low ต่ำสุด) — คลื่น 4 ทรงสามเหลี่ยมมักจบที่ E
    ซึ่งไม่ใช่จุดต่ำสุด กฎ 'ห้ามซ้อนคลื่น 1' ต้องเช็กกับจุดที่ลึกที่สุดจริง ไม่ใช่จุดที่มาร์ก"""
    seg = [c for c in candles if a <= c.ts <= b]
    return min(c.low for c in seg) if s > 0 else max(c.high for c in seg)


def check_rules(p: list[Pivot], candles: list[Candle], s: int) -> list[Rule]:
    v = [x.price for x in p]
    k = len(p) - 1
    rules: list[Rule] = []
    # ทิศของแต่ละขาต้องสลับถูก — ไม่งั้นที่เหลือไม่มีความหมาย
    bad = [f"{p[i].label}->{p[i + 1].label}" for i in range(k)
           if s * (v[i + 1] - v[i]) * (1 if i % 2 == 0 else -1) <= 0]
    rules.append(Rule("แต่ละขาไปทางที่ถูก (ขึ้น-ลงสลับกัน)", not bad,
                      "ครบ" if not bad else "ขาที่ผิดทิศ: " + ", ".join(bad)))
    if k >= 2:
        m = s * (v[2] - v[0])
        rules.append(Rule("คลื่น 2 ไม่ย้อนเลยจุดเริ่มคลื่น 1", m > 0,
                          f"ก้นคลื่น 2 {fmt(v[2])} เทียบจุดเริ่ม {fmt(v[0])} (ห่าง {fmt(m)})"))
    if k >= 3:
        m = s * (v[3] - v[1])
        rules.append(Rule("คลื่น 3 ไปไกลกว่ายอดคลื่น 1", m > 0,
                          f"ยอดคลื่น 3 {fmt(v[3])} เทียบยอดคลื่น 1 {fmt(v[1])} (เลยไป {fmt(m)})"))
        l1, l3 = abs(v[1] - v[0]), abs(v[3] - v[2])
        if k >= 5:
            l5 = abs(v[5] - v[4])
            ok = not (l3 < l1 and l3 < l5)
            rules.append(Rule("คลื่น 3 ไม่ใช่คลื่นที่สั้นที่สุด", ok,
                              f"1 = {fmt(l1)} · 3 = {fmt(l3)} · 5 = {fmt(l5)}"))
        else:
            note = ("คลื่น 3 ยาวกว่าคลื่น 1 แล้ว — คลื่น 5 ยาวเท่าไหร่ก็ไม่ผิดข้อนี้" if l3 >= l1 else
                    f"คลื่น 3 สั้นกว่าคลื่น 1 → คลื่น 5 ต้องสั้นกว่า {fmt(l3)} (เพดาน {fmt(v[4] + s * l3) if k >= 4 else '-'})")
            rules.append(Rule("คลื่น 3 ไม่ใช่คลื่นที่สั้นที่สุด", True, f"1 = {fmt(l1)} · 3 = {fmt(l3)} — {note}"))
    if k >= 4:
        deepest = _extreme_between(candles, p[3].ts, p[4].ts, s)
        m = s * (deepest - v[1])
        rules.append(Rule("คลื่น 4 ไม่ล้ำเข้าเขตคลื่น 1", m > 0,
                          f"จุดลึกสุดของคลื่น 4 {fmt(deepest)} เทียบยอดคลื่น 1 {fmt(v[1])} (ห่าง {fmt(m)})"))
    return rules


def _legs(candles: list[Candle], a: datetime, b: datetime, move: float, ref: float) -> int:
    """จำนวนขาย่อยระหว่าง a..b — ที่ความละเอียด 15% ของความยาวขา (ขึ้นกับเกณฑ์ บอกไว้ในข้อความ)"""
    seg = [c for c in candles if a <= c.ts <= b]
    inner = [z for z in zigzag(seg, LEGS_PCT_OF_MOVE * move / ref) if a < z.ts < b]
    return len(inner) + 1


def _rsi_at(c4: list[Candle], ts: datetime) -> float | None:
    upto = [c.close for c in c4 if c.ts <= ts]
    return rsi_wilder(upto)


def analyze(name: str, symbol: str, direction: str, pivots: list[Pivot], candles: list[Candle],
            wave4_shape: str | None = None, now: datetime | None = None) -> Report:
    s = 1 if direction == "up" else -1
    v = [x.price for x in pivots]
    k = len(pivots) - 1
    last = candles[-1]
    rules = check_rules(pivots, candles, s)
    after = [c for c in candles if c.ts > pivots[-1].ts]
    ext = (lambda c: c.high) if s > 0 else (lambda c: c.low)          # ไปทางเทรนด์
    back = (lambda c: c.low) if s > 0 else (lambda c: c.high)         # สวนเทรนด์
    beyond = (lambda a, b: s * (a - b) > 0)
    rep = Report(name, symbol, direction, pivots, last, rules, "", [], [])

    if not rep.valid:
        rep.state = "count นี้ผิดกฎเหล็ก — ต้องนับใหม่ก่อน ไม่ไล่ฉากทัศน์ต่อ"
        return rep

    l1 = abs(v[1] - v[0]) if k >= 1 else 0.0
    if k == 1:
        rep.state = "จบคลื่น 1 แล้ว · กำลังอยู่ในคลื่น 2"
        rep.scenarios.append(Scenario(
            "A", "คลื่น 2 กำลังย่อ", "ย่อลงมาพักก่อนคลื่น 3", True, v[0],
            f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[0])} (จุดเริ่มคลื่น 1)",
            targets=[(f"ย่อ {r:.1%}", v[1] - s * r * l1) for r in (0.5, 0.618, 0.786)]))
    elif k == 2:
        rep.state = "จบคลื่น 2 แล้ว · กำลังอยู่ในคลื่น 3"
        rep.scenarios.append(Scenario(
            "A", "คลื่น 3 กำลังวิ่ง", "ขาที่มักแรงและยาวที่สุด", True, v[2],
            f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[2])} (จุดเริ่มคลื่น 3)",
            f"ผ่าน {fmt(v[1])} (ยอดคลื่น 1)",
            [(f"3 = {r}×1", v[2] + s * r * l1) for r in (1.0, 1.618, 2.618)]))
    elif k == 3:
        l3 = abs(v[3] - v[2])
        rep.state = "จบคลื่น 3 แล้ว · กำลังอยู่ในคลื่น 4"
        rep.scenarios.append(Scenario(
            "A", "คลื่น 4 กำลังพักฐาน", "พักก่อนขาสุดท้าย", True, v[1],
            f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[1])} (ยอดคลื่น 1 — ห้ามซ้อน)",
            targets=[(f"ย่อ {r:.1%}", v[3] - s * r * l3) for r in (0.236, 0.382, 0.5)]))
    elif k == 4:
        _in_wave5(rep, candles, after, s, ext, back, beyond, wave4_shape, now)
    else:
        whole = abs(v[5] - v[0])
        broke = any(beyond(ext(c), v[5]) for c in after)
        rep.state = "ครบ 5 คลื่นตามที่มาร์ก"
        rep.scenarios += [
            Scenario("B", "impulse จบแล้ว · เริ่มปรับฐาน (ABC)", "ขาใหญ่ทั้งขาจบ รอบนี้คือการพักใหญ่",
                     not broke, v[5], f"{'ทะลุ' if s > 0 else 'หลุด'} {fmt(v[5])} (ยอดคลื่น 5)",
                     targets=[(f"ย่อ {r:.1%} ของทั้งขา", v[5] - s * r * whole) for r in (0.382, 0.5, 0.618)]),
            Scenario("A", "คลื่น 5 ยังไม่จบ (ยืด)", "ยอดที่มาร์กเป็นแค่ขาย่อยในคลื่น 5", True, v[4],
                     f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[4])} (จุดเริ่มคลื่น 5)",
                     f"ทำยอดใหม่เลย {fmt(v[5])}"),
        ]
    _set_bias(rep, direction)
    return rep


# ฉากที่ "ไปต่อทางเทรนด์ของ count" vs "ย่อ/ปรับฐาน" — key เดียวกันมีความหมายต่างกันตามสถานะ
_WITH_TREND = {1: set(), 2: {"A"}, 3: set(), 4: {"A"}, 5: {"A"}}


def _set_bias(rep: Report, direction: str) -> None:
    other = "down" if direction == "up" else "up"
    k = len(rep.pivots) - 1
    for sc in rep.scenarios:
        sc.bias = direction if sc.key in _WITH_TREND.get(k, set()) else other


def _in_wave5(rep: Report, candles, after, s, ext, back, beyond, wave4_shape, now) -> None:
    p, v = rep.pivots, [x.price for x in rep.pivots]
    l1, l3 = abs(v[1] - v[0]), abs(v[3] - v[2])
    cap = v[4] + s * l3 if l3 < l1 else None
    w5 = [(f"5 = 1×คลื่น 1", v[4] + s * l1),
          (f"5 = 0.618×(0→3)", v[4] + s * 0.618 * abs(v[3] - v[0])),
          (f"5 = 1.618×คลื่น 1", v[4] + s * 1.618 * l1)]
    if l1 and abs(l3 / l1 - 1) <= EQUAL_TOL:
        # ตำรา: impulse มักมีขาเดียวที่ยืด — 1 ≈ 3 และไม่มีขาไหนถึง 1.618 เท่า -> ขาที่ยืดคือ 5
        # คลื่น 5 แบบยืดมักยาว 1–1.618 เท่าของระยะรวม 0→3 (วัดจากจุดจบคลื่น 4)
        span = abs(v[3] - v[0])
        w5 += [("5 ยืด = 1×(0→3)", v[4] + s * span), ("5 ยืด = 1.618×(0→3)", v[4] + s * 1.618 * span)]
    if cap is not None:   # เป้าที่ทำให้คลื่น 3 กลายเป็นคลื่นสั้นสุด = ผิดกฎ ห้ามโชว์เป็นเป้า
        w5 = [(t, x) for t, x in w5 if s * (cap - x) > 0]

    broke4 = [c for c in after if not beyond(back(c), v[4]) and back(c) != v[4]]
    if broke4:
        rep.state = (f"ราคา{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[4])} ไปแล้ว — จุดที่มาร์กเป็นคลื่น 4 "
                     "ไม่ใช่จุดจบคลื่น 4 (หรือ count ต้องเปลี่ยน)")
        rep.scenarios.append(Scenario("C", "คลื่น 4 ยังไม่จบ", "ยังพักฐานต่อ จุดที่มาร์กเป็นแค่ขาย่อย",
                                      True, v[1], f"ล้ำเขตคลื่น 1 ที่ {fmt(v[1])}"))
        return
    if not after:
        rep.state = "เพิ่งจบคลื่น 4 · คลื่น 5 ยังไม่เริ่มให้เห็น"
        return

    i_top = max(after, key=ext) if s > 0 else min(after, key=ext)
    s1 = ext(i_top)
    post = [c for c in after if c.ts > i_top.ts]
    pull_c = (min(post, key=back) if s > 0 else max(post, key=back)) if post else None
    pull = back(pull_c) if pull_c else None
    move = abs(s1 - v[4])
    legs = _legs(candles, p[4].ts, i_top.ts, move, v[4])
    rep.sub = {"s1": s1, "s1_ts": i_top.ts, "pull": pull, "pull_ts": pull_c.ts if pull_c else None,
               "legs": legs}

    if pull is None or abs(s1 - pull) < 0.236 * move:
        rep.state = f"อยู่ในคลื่น 5 · ขาแรกจาก {fmt(v[4])} ยังวิ่งอยู่ (ยอดล่าสุด {fmt(s1)})"
        rep.scenarios.append(Scenario("A", "คลื่น 5 กำลังวิ่ง", "ขาสุดท้ายของ impulse", True, v[4],
                                      f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[4])} (จุดเริ่มคลื่น 5)",
                                      targets=w5))
        return

    rep.state = (f"อยู่ในคลื่น 5 · ขาแรกจาก {fmt(v[4])} ไป {fmt(s1)} แล้วย่อมา {fmt(pull)} — "
                 f"คำถามคือขานั้นเป็น 'i ของ 5' หรือ '5 จบแล้ว'")
    truncated = not beyond(s1, v[3])
    a_alive = beyond(pull, v[4])
    rep.scenarios += [
        Scenario("A", "ขาแรกคือ i ของ 5 · ตอนนี้อยู่ใน ii",
                 "คลื่น 5 เพิ่งเริ่ม — ย่อพักก่อนขา iii ที่มักแรงที่สุด", a_alive, v[4],
                 f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[4])} (ii ห้ามย้อนเลยจุดเริ่ม i)",
                 f"{'ทะลุ' if s > 0 else 'หลุด'} {fmt(s1)} (ยอดขา i)",
                 [("iii = 1×i", pull + s * move), ("iii = 1.618×i", pull + s * 1.618 * move)] + w5),
        Scenario("B", "คลื่น 5 จบแล้วที่ " + fmt(s1) + (" (truncated)" if truncated else ""),
                 "ขาขึ้นชุดนี้ครบ 5 คลื่น — ต่อไปคือการปรับฐาน", True, s1,
                 f"{'ทะลุ' if s > 0 else 'หลุด'} {fmt(s1)} (ถ้าทำยอดใหม่ = คลื่น 5 ยังไม่จบ)",
                 f"{'หลุด' if s > 0 else 'ทะลุ'} {fmt(v[4])} (จุดเริ่มคลื่น 5)",
                 [(f"ย่อ {r:.1%} ของ 0→5", s1 - s * r * abs(s1 - v[0])) for r in (0.382, 0.5, 0.618)]),
    ]
    if legs == 3:
        rep.scenarios.append(Scenario(
            "C", "ขาจาก 4 เป็นแค่ 3 ขาย่อย — คลื่น 4 อาจยังไม่จบ",
            "ทรงขาแบบปรับฐาน ไม่ใช่แรงส่ง: อาจเป็นขาเด้งข้างในคลื่น 4 ที่ยังไม่จบ", True, v[3],
            f"{'ทะลุ' if s > 0 else 'หลุด'} {fmt(v[3])} (ยอดคลื่น 3 — ถ้าเลยไป คลื่น 5 เริ่มแน่)"))

    ev = rep.evidence
    gap = abs(s1 - v[3])
    if truncated:
        ev.append(Evidence(f"ยอดขาแรก {fmt(s1)} ไม่เกินยอดคลื่น 3 {fmt(v[3])} (ขาดอีก {fmt(gap)}) — "
                           "ถ้า 5 จบตรงนี้คือ 5 แบบ truncated ซึ่งเกิดได้แต่ไม่บ่อย", "A"))
    else:
        ev.append(Evidence(f"ยอดขาแรก {fmt(s1)} เกินยอดคลื่น 3 แล้ว {fmt(gap)}", "-"))
    ratio = l3 / l1 if l1 else 0
    if abs(ratio - 1) <= EQUAL_TOL:
        ev.append(Evidence(f"คลื่น 1 ({fmt(l1)}) ≈ คลื่น 3 ({fmt(l3)}) — ตามตำรา คลื่น 5 มักเป็นขาที่ยืด", "A"))
    if wave4_shape == "triangle":
        deepest = _extreme_between(candles, p[3].ts, p[4].ts, s)
        width = abs(v[3] - deepest)
        tgt = v[4] + s * width
        ev.append(Evidence(f"คลื่น 4 เป็นสามเหลี่ยมกว้าง {fmt(width)} — แรงพุ่งหลังสามเหลี่ยมมักยาวราว"
                           f"ความกว้าง (~{fmt(tgt)}); ขาแรกไปได้ {fmt(move)} = {move / width:.0%}",
                           "B" if move >= 0.8 * width else "A"))
    c4 = resample_4h(candles, now)
    r3, r1 = _rsi_at(c4, p[3].ts), _rsi_at(c4, i_top.ts)
    if r3 is not None and r1 is not None:
        weaker = (r1 < r3) if s > 0 else (r1 > r3)
        ev.append(Evidence(f"RSI 4H ที่ยอดขาแรก {r1:.0f} เทียบที่ยอดคลื่น 3 {r3:.0f} — "
                           + ("แรงส่งอ่อนลง (เข้าทางยอดสุดท้าย)" if weaker else "แรงส่งไม่อ่อนลง"),
                           "B" if weaker else "A"))
    depth = abs(s1 - pull) / move
    ev.append(Evidence(f"ย่อจากยอดขาแรกมาแล้ว {depth:.0%} ของขา"
                       + (" — ถ้าเป็น ii ก็เป็น ii ที่ลึกมาก (ปกติ 50–62%)" if depth > 0.786 else ""),
                       "B" if depth > 0.786 else "-"))
    ev.append(Evidence(f"ขาจาก {fmt(v[4])} ไป {fmt(s1)} แบ่งได้ {legs} ขาย่อยที่ความละเอียด 1H "
                       "(5 ขา = ทรงแรงส่ง ทั้ง i และ 5 เป็นทรงนี้ได้ · 3 ขา = ทรงปรับฐาน)",
                       "-"))
