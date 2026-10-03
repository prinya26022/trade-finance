"""เครื่องนับคลื่นเอง — ไล่ทุก count ที่ผ่านกฎ แล้วให้คะแนนตามตำราทีละข้อ (ไม่ใช่เปอร์เซ็นต์โอกาส).

ทำไมยอมให้เครื่องนับ หลังจากที่ตั้งใจไม่ให้มันนับมาตลอด: ปัญหาของ "เครื่องนับแทนคน" คือมันจะ
ตอบมาทางเดียวอย่างมั่นใจ. ที่นี่มันต้องตอบ **ทุกทาง** ที่กฎยังไม่ตัดทิ้ง พร้อมเหตุผลว่าแต่ละทาง
เข้าตำรากี่ข้อ — ประโยชน์คือเห็นทางที่ตาคนข้ามไป ไม่ใช่ได้ "คำตอบที่ถูก". ลองครั้งแรกกับ BTC:
เครื่องหา count เหลืองเจอตรงกับที่ผู้ใช้มาร์กทุกจุด แต่เจออีกสองทางที่ผู้ใช้ไม่ได้ลิสต์ไว้ — หนึ่งใน
นั้นคือ zigzag ABC ที่อธิบาย "คลื่น 1 ≈ คลื่น 3" ได้พอดีเท่ากัน

วิธี: จุดกลับตัวจาก zigzag หลายความละเอียด (รวมกัน) -> ไล่ลำดับจุดแบบ DFS ที่ตัดกิ่งทันทีเมื่อ
(1) จุดที่ติดป้ายไม่ใช่ยอด/ก้นจริงของช่วงนั้น หรือ (2) ผิดกฎของ pattern. ขาลงใช้วิธีกลับด้านราคา
(กระจก) แล้วใช้โค้ดขาขึ้นชุดเดียว
"""
from dataclasses import dataclass, field

from src.wave.candles import Candle
from src.wave.pivots import Pivot, zigzag

DEFAULT_PCTS = (0.015, 0.02, 0.03, 0.04, 0.06, 0.08)
MAX_RESULTS = 12           # ทุกทางที่ผ่านกฎควรเห็นได้ — 8 เคยตัด count ทางเลือกของ BTC ที่คะแนนต่ำทิ้ง
MATCH_TOL = 0.003            # จุดห่างกันไม่เกิน 0.3% = จุดเดียวกัน
MATCH_TOL_W4 = 0.01          # ยกเว้นจุด 4: ผู้ใช้มาร์กสามเหลี่ยมที่ E แต่เครื่องใช้ก้นลึกสุด (BTC: 83,131 vs 82,561)


@dataclass
class Guide:
    text: str
    ok: bool
    value: str


@dataclass
class AutoCount:
    pattern: str                    # impulse | zigzag | flat
    labels: list[str]
    pivots: list[Pivot]
    complete: bool
    guides: list[Guide]
    state: str
    kill_level: float | None
    kill_text: str
    matches_user: bool = False

    @property
    def hits(self) -> int:
        return sum(g.ok for g in self.guides)

    @property
    def unchecked(self) -> int:
        """ข้อตามตำราที่ยังตรวจไม่ได้เพราะ pattern ยังไม่จบ (เช่น C ยังไม่จบ = วัดความยาว C ไม่ได้)"""
        return FULL_GUIDES[self.pattern] - len(self.guides)

    @property
    def score(self) -> float:
        """ข้อที่เข้า − ข้อที่ไม่เข้า − ครึ่งหนึ่งของข้อที่ยังตรวจไม่ได้.
        ไม่ใช้สัดส่วน: count ที่ยังไม่จบมีข้อให้ตรวจน้อย ('อยู่ในขา C' ตรวจได้ข้อเดียว) แล้วผ่าน
        1/1 = 100% ขึ้นอันดับหนึ่งทั้งที่หลักฐานน้อยสุด — เจอจริงตอนรันครั้งแรก. 'ยังไม่รู้' ไม่ใช่
        'ผ่าน' จึงหักครึ่งข้อ"""
        return self.hits - (len(self.guides) - self.hits) - 0.5 * self.unchecked


def _mirror(cs: list[Candle]) -> list[Candle]:
    return [Candle(c.ts, -c.open, -c.low, -c.high, -c.close) for c in cs]


def _flip(p: Pivot) -> Pivot:
    return Pivot(p.label, p.ts, -p.price, "L" if p.kind == "H" else "H")


class _Seg:
    """ยอด/ก้นของช่วงแท่ง i..j แบบเร็ว (ตารางล่วงหน้า) — DFS เรียกเป็นหมื่นครั้ง"""

    def __init__(self, cs: list[Candle]):
        self.cs = cs
        self.idx = {c.ts: i for i, c in enumerate(cs)}

    def hi(self, i: int, j: int) -> float:
        return max(c.high for c in self.cs[i:j + 1])

    def lo(self, i: int, j: int) -> float:
        return min(c.low for c in self.cs[i:j + 1])


def _pivots(cs: list[Candle], anchor: Pivot, pcts) -> list[Pivot]:
    seen: dict = {}
    for pct in pcts:
        for p in zigzag(cs, pct):
            if p.ts > anchor.ts:
                seen[(p.ts, p.kind)] = p
    return sorted(seen.values(), key=lambda p: p.ts)


def _is_extreme(seg: _Seg, prev: Pivot, p: Pivot, nxt_i: int) -> bool:
    i0, i = seg.idx[prev.ts], seg.idx[p.ts]
    return (seg.hi(i0, nxt_i) <= p.price) if p.kind == "H" else (seg.lo(i0, nxt_i) >= p.price)


# ---------- กฎ + ตำราของแต่ละ pattern (ขาขึ้น; ขาลงกลับด้านมาแล้ว) ----------

def _impulse_ok(v: list[float], complete: bool) -> bool:
    k = len(v) - 1
    if k >= 2 and v[2] <= v[0]:
        return False
    if k >= 3 and v[3] <= v[1]:
        return False
    if k >= 4 and v[4] <= v[1]:
        return False
    if k >= 5:
        l1, l3, l5 = v[1] - v[0], v[3] - v[2], v[5] - v[4]
        if l3 < l1 and l3 < l5:
            return False
    return True


def _impulse_guides(p: list[Pivot]) -> list[Guide]:
    v, t = [x.price for x in p], [x.ts for x in p]
    l1, l3 = v[1] - v[0], v[3] - v[2]
    r2, r4 = (v[1] - v[2]) / l1, (v[3] - v[4]) / l3
    t2, t4 = (t[2] - t[1]).total_seconds(), (t[4] - t[3]).total_seconds()
    g = [Guide("คลื่น 2 ย่อ 50–78.6% ของคลื่น 1", 0.5 <= r2 <= 0.786, f"{r2:.0%}"),
         Guide("คลื่น 4 ย่อ 23.6–50% ของคลื่น 3", 0.236 <= r4 <= 0.5, f"{r4:.0%}"),
         Guide("มีขาที่ยืด (3 ≥ 1.618×1 หรือ 1≈3 ให้ 5 ยืดแทน)",
               l3 >= 1.618 * l1 or abs(l3 / l1 - 1) <= 0.1, f"3 = {l3 / l1:.2f}×1"),
         Guide("คลื่น 4 ใช้เวลานานกว่าคลื่น 2 (สลับทรง)", t4 > t2, f"{t4 / t2:.1f}×" if t2 else "-")]
    if len(v) == 6:
        l5, span = v[5] - v[4], v[3] - v[0]
        fits = [abs(l5 / l1 - 1) <= 0.15, abs(l5 / (0.618 * span) - 1) <= 0.15]
        if abs(l3 / l1 - 1) <= 0.1:
            fits.append(l5 >= 0.85 * span)
        g.append(Guide("คลื่น 5 ≈ คลื่น 1 / 0.618×(0→3) / ยืด ≥ 1×(0→3)", any(fits), f"5 = {l5 / l1:.2f}×1"))
    return g


def _zigzag_ok(v: list[float], complete: bool) -> bool:
    if len(v) < 2:
        return True
    a = v[1] - v[0]
    if len(v) >= 3 and not (v[0] < v[2] < v[1]):
        return False                        # B ห้ามย้อนเลยจุดเริ่ม A
    if len(v) >= 3 and (v[1] - v[2]) / a >= 0.9:
        return False                        # B ย้อนเกือบหมด = ทรง flat ไม่ใช่ zigzag
    if len(v) >= 4 and v[3] <= v[1]:
        return False                        # C ต้องไปเลยปลาย A
    return True


def _flat_ok(v: list[float], complete: bool) -> bool:
    if len(v) < 2:
        return True
    a = v[1] - v[0]
    if len(v) >= 3 and not (0.9 <= (v[1] - v[2]) / a <= 1.382):
        return False                        # B ย้อน 90–138.2% ของ A
    if len(v) >= 4 and (v[3] - v[2]) < 0.8 * a:
        return False
    return True


def _corrective_guides(p: list[Pivot], pattern: str) -> list[Guide]:
    v, t = [x.price for x in p], [x.ts for x in p]
    a = v[1] - v[0]
    rb = (v[1] - v[2]) / a
    if pattern == "zigzag":
        g = [Guide("B ย้อน 38.2–78.6% ของ A", 0.382 <= rb <= 0.786, f"{rb:.0%}")]
    else:
        g = [Guide("B ย้อนเกือบหมดหรือเกิน A (flat)", rb >= 0.9, f"{rb:.0%}")]
    if len(v) == 4:
        c = v[3] - v[2]
        ratio = c / a
        g.append(Guide("C ≈ 0.618 / 1 / 1.618 เท่าของ A",
                       any(abs(ratio / r - 1) <= 0.1 for r in (0.618, 1.0, 1.618)), f"C = {ratio:.2f}×A"))
        ta, tc = (t[1] - t[0]).total_seconds(), (t[3] - t[2]).total_seconds()
        g.append(Guide("A กับ C ใช้เวลาใกล้กัน (0.5–2 เท่า)", ta > 0 and 0.5 <= tc / ta <= 2, f"{tc / ta:.1f}×" if ta else "-"))
    return g


FULL_GUIDES = {"impulse": 5, "zigzag": 3, "flat": 3}   # จำนวนข้อตามตำราเมื่อ pattern จบครบ

PATTERNS = {
    "impulse": (["0", "1", "2", "3", "4", "5"], _impulse_ok, {5, 6}),
    "zigzag": (["0", "A", "B", "C"], _zigzag_ok, {3, 4}),
    "flat": (["0", "A", "B", "C"], _flat_ok, {3, 4}),
}


def _state(pattern: str, p: list[Pivot], complete: bool) -> tuple[str, float, str]:
    """(ข้อความสถานะ, ราคาที่ทำให้ count นี้ผิด, คำอธิบาย) — ในหน่วยขาขึ้น (กลับด้านทีหลัง)"""
    last = p[-1]
    if pattern == "impulse":
        if complete:
            return "ครบ 5 คลื่นแล้ว → ต่อไปคือปรับฐาน", last.price, "ทำยอดใหม่เหนือคลื่น 5"
        return "อยู่ในคลื่น 5", last.price, "หลุดจุดจบคลื่น 4"
    if complete:
        return f"{pattern} ABC จบแล้ว → ขาเดิมกลับมา", last.price, "ทำยอดใหม่เหนือ C"
    return f"{pattern} อยู่ในขา C", (p[0].price if pattern == "zigzag" else None), \
        "B ย้อนเลยจุดเริ่ม A" if pattern == "zigzag" else "-"


def find_counts(candles: list[Candle], anchor: Pivot, pcts=DEFAULT_PCTS,
                user: list[Pivot] | None = None) -> list[AutoCount]:
    """ทุก count จาก anchor (ยอด/ก้นใหญ่) ที่ผ่านกฎ — เรียงตามจำนวนข้อที่เข้าตำรา (มาก->น้อย)."""
    down = anchor.kind == "H"
    cs = _mirror(candles) if down else candles
    a = _flip(anchor) if down else anchor
    seg = _Seg(cs)
    if a.ts not in seg.idx:
        return []
    piv = _pivots(cs, a, pcts)
    last_i = len(cs) - 1
    results: dict = {}

    def emit(pattern, seq, complete):
        labels = PATTERNS[pattern][0][:len(seq)]
        pts = [Pivot(l, x.ts, x.price, x.kind) for l, x in zip(labels, seq)]
        guides = (_impulse_guides(pts) if pattern == "impulse" and len(pts) >= 5
                  else _corrective_guides(pts, pattern) if pattern != "impulse" else [])
        state, kill, kill_text = _state(pattern, pts, complete)
        if down:
            pts = [_flip(x) for x in pts]
            kill = -kill if kill is not None else None
        key = (pattern, tuple((x.ts, round(x.price)) for x in pts))
        results[key] = AutoCount(pattern, labels, pts, complete, guides, state, kill, kill_text)

    def dfs(pattern, seq):
        labels, ok, ends = PATTERNS[pattern]
        v = [x.price for x in seq]
        if not ok(v, False):
            return
        n = len(seq)
        if n in ends:
            # จุดสุดท้ายต้องเป็นยอด/ก้นจริงจนถึงปัจจุบัน — ถ้าราคาหลังจากนั้นเลยไปแล้ว ป้ายนั้นผิดที่
            if _is_extreme(seg, seq[-2], seq[-1], last_i):
                complete = n == len(labels)
                if not complete or ok(v, True):
                    emit(pattern, seq, complete)
        if n == len(labels):
            return
        want = "H" if seq[-1].kind == "L" else "L"
        for p in piv:
            if p.ts <= seq[-1].ts or p.kind != want:
                continue
            # ป้ายก่อนหน้าต้องเป็นยอด/ก้นจริงของช่วงระหว่างเพื่อนบ้านทั้งสอง
            if n >= 2 and not _is_extreme(seg, seq[-2], seq[-1], seg.idx[p.ts]):
                continue
            if n == 1 and not _is_extreme(seg, seq[0], seq[0], seg.idx[p.ts]):
                continue
            dfs(pattern, seq + [p])

    for pattern in PATTERNS:
        dfs(pattern, [a])

    out = list(results.values())
    if user:
        for c in out:
            c.matches_user = c.pattern == "impulse" and _same(c.pivots, user)
    out.sort(key=lambda c: (-c.score, -len(c.guides)))
    return out


def _same(a: list[Pivot], b: list[Pivot]) -> bool:
    if len(a) < len(b):
        return False
    return all(abs(x.price / y.price - 1) <= (MATCH_TOL_W4 if i == 4 else MATCH_TOL)
               for i, (x, y) in enumerate(zip(a, b)))


def pick(counts: list[AutoCount], n: int = MAX_RESULTS) -> list[AutoCount]:
    """ตัดให้เหลือ n อันดับแรก — แต่ count ที่ตรงกับของผู้ใช้ต้องอยู่เสมอ ไม่ว่าอันดับไหน
    (การหายไปจากรายการเพราะตกอันดับ จะอ่านผิดเป็น 'เครื่องไม่เจอ count ของคุณ')"""
    top = counts[:n]
    mine = [c for c in counts[n:] if c.matches_user]
    return top + mine[:1]
