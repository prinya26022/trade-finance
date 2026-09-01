"""สัญญาณแต่ละตัว — ฟังก์ชันบริสุทธิ์ล้วน (รับ TickerData คืน Signal ไม่แตะเน็ต ไม่แตะ DB).

**ทุกเกณฑ์ในไฟล์นี้เป็นค่าที่เราเลือกเอง ไม่ใช่ค่าที่ธรรมชาติกำหนด** — จึงต้องทำสองอย่าง
เสมอ ตามบทเรียน Phase 48 (เส้น 15pp ที่ซ่อนอยู่จนมองไม่เห็น):
  1. เขียนเหตุผลของตัวเลขไว้ตรงที่ตั้งมัน ไม่ใช่ในเอกสารแยก
  2. รายงาน `margin` = ห่างจากเส้นเท่าไร ให้เห็นว่าคำตอบ 'เฉียด' หรือ 'ขาดลอย'

และ **ไม่มีคะแนนรวมเป็นเลขเดียว** โดยตั้งใจ — "ความเสี่ยงฟองสบู่ 63%" เป็นความแม่นยำปลอม
ที่เถียงกับมันไม่ได้ ส่วน "4 ใน 7 เงื่อนไขเป็นจริง และนี่คือรายชื่อ" เถียงได้ทีละข้อ
"""
from dataclasses import dataclass, field

from src.aicapex.universe import HYPERSCALERS, LEVERED, POWER

OK, WATCH, ALERT, UNKNOWN = "ok", "watch", "alert", "unknown"
_SEVERITY = {OK: 0, UNKNOWN: 1, WATCH: 2, ALERT: 3}


@dataclass
class Signal:
    key: str
    label: str                       # ชื่อที่คนอ่านเข้าใจโดยไม่ต้องรู้ศัพท์การเงิน
    state: str                       # ok | watch | alert | unknown
    value: float | None
    unit: str
    watch_at: float | None           # เส้นที่เริ่ม 'ต้องจับตา'
    alert_at: float | None           # เส้นที่ 'เป็นจริงแล้ว'
    detail: str                      # หนึ่งประโยคที่เถียงได้ ไม่ใช่คำคุณศัพท์
    rows: list[dict] = field(default_factory=list)
    missing: str | None = None       # ทำไมถึง unknown — ต้องบอก ไม่ใช่เงียบ

    @property
    def margin(self) -> float | None:
        """ห่างจากเส้นที่ 'เริ่มต้องจับตา' เท่าไร (+ = ข้ามเส้นไปแล้ว). None ถ้าวัดไม่ได้.

        เครื่องหมายอิงทิศทางที่แย่ลงเสมอ ไม่ใช่ค่าลบ/บวกทางคณิตศาสตร์ — สัญญาณที่ 'ยิ่งต่ำ
        ยิ่งแย่' (เช่นส่วนต่างเครดิต) ต้องได้ margin เป็นบวกเมื่อข้ามเส้นเหมือนกัน ไม่งั้น
        คนอ่านต้องจำเองว่าตัวไหนอ่านกลับด้าน ซึ่งคือที่มาของการอ่านผิด"""
        if self.value is None or self.watch_at is None:
            return None
        worse_when_higher = (self.alert_at is None) or (self.alert_at >= self.watch_at)
        raw = self.value - self.watch_at
        return round(raw if worse_when_higher else -raw, 2)

    @property
    def borderline(self) -> bool:
        """เฉียดเส้นทั้งสองฝั่ง — เกือบติดกับเพิ่งติด อ่านต่างกัน แต่ทั้งคู่แปลว่า
        คำตอบแขวนอยู่บนเกณฑ์ที่เราตั้งเอง (แนวคิดเดียวกับ close_call ของ Phase 48)"""
        m = self.margin
        if m is None or self.watch_at is None:
            return False
        scale = abs(self.watch_at) if self.watch_at else 1.0
        return abs(m) <= max(0.1 * scale, 0.01)


def _pct_change(closes, days: int):
    """% เปลี่ยนของราคาปิดในช่วง N วันทำการล่าสุด (ต้องมีข้อมูลครบถึงจะคืนค่า)."""
    if not closes or len(closes) <= days:
        return None
    start, end = closes[-days - 1][1], closes[-1][1]
    return None if start <= 0 else round((end / start - 1) * 100, 2)


def _closes(data: dict, ticker: str):
    d = data.get(ticker)
    return getattr(d, "closes", None) or []


def _basket_change(data: dict, tickers, days: int):
    """ผลตอบแทนถัวเฉลี่ยเท่ากันทุกตัวของตะกร้า — ตัวที่ไม่มีข้อมูลถูกข้าม (ไม่นับเป็น 0%
    ซึ่งจะทำให้ตะกร้าดูนิ่งกว่าความจริง). None ถ้าไม่เหลือตัวไหนเลย"""
    vals = [c for t in tickers if (c := _pct_change(_closes(data, t), days)) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _state(value, watch_at: float, alert_at: float, higher_is_worse: bool) -> str:
    if value is None:
        return UNKNOWN
    if higher_is_worse:
        return ALERT if value >= alert_at else (WATCH if value >= watch_at else OK)
    return ALERT if value <= alert_at else (WATCH if value <= watch_at else OK)


# ─────────────────────────────────────────────────────────────────────────────
# 1. hyperscaler เผาเงิน — กลไกที่ BIS ชี้ตรงๆ
# ─────────────────────────────────────────────────────────────────────────────
def hyperscaler_fcf(data: dict) -> Signal:
    """กี่รายใน 4 รายใหญ่ที่กระแสเงินสดอิสระติดลบในไตรมาสล่าสุด.

    เกณฑ์เป็นการ **นับ** ไม่ใช่การวัดระดับ เพราะบริษัทมูลค่าล้านล้านดอลลาร์ที่เผาเงินสด
    เป็นเหตุการณ์เชิงประเภท ไม่ใช่เรื่องมากน้อย — 1 ราย = ผิดปกติแล้ว, 2 รายขึ้นไป =
    ไม่ใช่เรื่องเฉพาะบริษัท แต่เป็นเรื่องของอุตสาหกรรม"""
    rows, unknown = [], []
    for t, name in HYPERSCALERS.items():
        d = data.get(t)
        fcf = d.fcf_q[0] if (d and d.fcf_q) else None
        if fcf is None:
            unknown.append(t)
            continue
        rows.append({"ticker": t, "name": name, "fcf_b": round(fcf / 1e9, 2),
                     "quarter": d.quarter_ends[0] if d.quarter_ends else None,
                     "negative": fcf < 0})
    if not rows:
        return Signal("hyperscaler_fcf", "รายใหญ่เผาเงินสด", UNKNOWN, None, "ราย", 1, 2,
                      "ดึงงบกระแสเงินสดไม่ได้เลย", [], f"ไม่มีข้อมูล: {', '.join(unknown)}")

    n = sum(1 for r in rows if r["negative"])
    who = ", ".join(f"{r['name']} {r['fcf_b']:+.1f}B" for r in rows if r["negative"])
    detail = (f"{n} ใน {len(rows)} รายมีกระแสเงินสดอิสระติดลบในไตรมาสล่าสุด ({who})"
              if n else f"ทั้ง {len(rows)} รายยังมีกระแสเงินสดอิสระเป็นบวก")
    return Signal("hyperscaler_fcf", "รายใหญ่เผาเงินสด", _state(n, 1, 2, True), n, "ราย",
                  1, 2, detail, rows, f"ไม่มีข้อมูล: {', '.join(unknown)}" if unknown else None)


def capex_vs_depreciation(data: dict) -> Signal:
    """capex หารด้วยค่าเสื่อมราคาไตรมาสล่าสุด เฉลี่ยทั้งกลุ่ม.

    ตัวเลขนี้แปลว่า **ค่าเสื่อมในอนาคตต้องโตอีกกี่เท่าจึงจะตามทันเงินที่กำลังจ่ายอยู่วันนี้**
    1.0 = แค่เปลี่ยนของที่หมดอายุ (สภาวะนิ่ง) · 2.0 = กำลังเพิ่มขนาดสินทรัพย์เท่าตัว ·
    3.5+ = ค่าเสื่อมที่ยังไม่ปรากฏในงบกำไรขาดทุนวันนี้ จะกดกำไรอย่างหนักในอีกไม่กี่ปี
    เกณฑ์มาจากเลขคณิตของตัวมันเอง ไม่ได้ปรับให้พอดีกับข้อมูลวันนี้"""
    rows = []
    for t, name in HYPERSCALERS.items():
        d = data.get(t)
        capex = abs(d.capex_q[0]) if (d and d.capex_q and d.capex_q[0] is not None) else None
        da = d.da_q[0] if (d and d.da_q and d.da_q[0] is not None) else None
        if not capex or not da or da <= 0:
            continue
        rows.append({"ticker": t, "name": name, "ratio": round(capex / da, 2),
                     "capex_b": round(capex / 1e9, 1), "da_b": round(da / 1e9, 1)})
    if not rows:
        return Signal("capex_vs_da", "จ่ายล่วงหน้าเกินค่าเสื่อมที่บันทึกไว้", UNKNOWN, None, "เท่า",
                      2.0, 3.5, "ดึง capex/ค่าเสื่อมไม่ได้", [], "ไม่มีข้อมูลงบกระแสเงินสด")

    avg = round(sum(r["ratio"] for r in rows) / len(rows), 2)
    worst = max(rows, key=lambda r: r["ratio"])
    return Signal("capex_vs_da", "จ่ายล่วงหน้าเกินค่าเสื่อมที่บันทึกไว้",
                  _state(avg, 2.0, 3.5, True), avg, "เท่า", 2.0, 3.5,
                  f"กลุ่มนี้จ่ายลงทุนเฉลี่ย {avg} เท่าของค่าเสื่อมที่บันทึกอยู่ "
                  f"(สูงสุด {worst['name']} {worst['ratio']} เท่า) — "
                  f"ค่าเสื่อมในอนาคตต้องโตประมาณเท่านี้จึงจะตามทัน", rows)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ชั้นที่กู้เงิน — จุดที่จะแตกก่อน
# ─────────────────────────────────────────────────────────────────────────────
def neocloud_leverage(data: dict) -> Signal:
    """หนี้รวมหารส่วนของผู้ถือหุ้น ของรายที่สูงสุดในชั้นที่กู้มาซื้อชิป.

    ใช้ **ตัวที่สูงสุด ไม่ใช่ค่าเฉลี่ย** เพราะการผิดนัดชำระหนี้ไม่ได้เฉลี่ยกัน — รายเดียวที่
    ล้มก็พอจะทำให้เจ้าหนี้ตีราคาหลักประกันของทั้งกลุ่มใหม่ทันที
    เกณฑ์อ้างอิงจากบริษัทลีสซิ่ง/REIT ทั่วไปที่ 2-3 เท่าถือว่าปกติ — เกิน 5 เท่าบนสินทรัพย์
    ที่ยังเถียงกันอยู่ว่ามูลค่าซากเท่าไร คือคนละเรื่องกับลีสซิ่งเครื่องบินหรืออาคาร"""
    rows = []
    for t, name in LEVERED.items():
        d = data.get(t)
        debt = d.total_debt_q[0] if (d and d.total_debt_q and d.total_debt_q[0] is not None) else None
        eq = d.equity_q[0] if (d and d.equity_q and d.equity_q[0] is not None) else None
        if not debt or not eq or eq <= 0:
            continue
        rows.append({"ticker": t, "name": name, "ratio": round(debt / eq, 2),
                     "debt_b": round(debt / 1e9, 2), "equity_b": round(eq / 1e9, 2)})
    if not rows:
        return Signal("neocloud_leverage", "หนี้เทียบทุนของชั้นที่กู้มาซื้อชิป", UNKNOWN, None,
                      "เท่า", 3.0, 5.0, "ดึงงบดุลไม่ได้", [], "ไม่มีข้อมูลงบดุล")

    worst = max(rows, key=lambda r: r["ratio"])
    return Signal("neocloud_leverage", "หนี้เทียบทุนของชั้นที่กู้มาซื้อชิป",
                  _state(worst["ratio"], 3.0, 5.0, True), worst["ratio"], "เท่า", 3.0, 5.0,
                  f"{worst['name']} มีหนี้ {worst['debt_b']}B ต่อทุน {worst['equity_b']}B "
                  f"= {worst['ratio']} เท่า (สูงสุดในกลุ่ม)", rows)


def neocloud_debt_growth(data: dict) -> Signal:
    """หนี้รวมทั้งชั้นโตกี่ % เทียบไตรมาสก่อน.

    ระดับหนี้บอกว่า 'ตอนนี้ตึงแค่ไหน' ส่วนอัตราเร่งบอกว่า 'อีกนานแค่ไหนจะตึง' ซึ่งเป็นคำถาม
    ที่มีประโยชน์กว่าเมื่อยังไม่มีอะไรพัง
    10%/ไตรมาส = ~46%/ปี · 20%/ไตรมาส = ~107%/ปี ซึ่งเร็วกว่ารายได้ของธุรกิจไหนก็ตามที่
    จะตามทันได้ — เกณฑ์มาจากการทบต้น ไม่ได้มาจากการดูข้อมูลก่อนแล้วตั้งทีหลัง"""
    now = prev = 0.0
    rows = []
    for t, name in LEVERED.items():
        d = data.get(t)
        if not d or len(d.total_debt_q) < 2:
            continue
        a, b = d.total_debt_q[0], d.total_debt_q[1]
        if a is None or b is None or b <= 0:
            continue
        now += a
        prev += b
        rows.append({"ticker": t, "name": name, "debt_b": round(a / 1e9, 2),
                     "prev_b": round(b / 1e9, 2), "qoq_pct": round((a / b - 1) * 100, 1)})
    if not rows or prev <= 0:
        return Signal("neocloud_debt_growth", "หนี้ของชั้นที่กู้ โตเร็วแค่ไหน", UNKNOWN, None,
                      "%/ไตรมาส", 10.0, 20.0, "ดึงงบดุลย้อนหลังไม่พอ", [],
                      "ต้องมีอย่างน้อย 2 ไตรมาส")

    qoq = round((now / prev - 1) * 100, 1)
    return Signal("neocloud_debt_growth", "หนี้ของชั้นที่กู้ โตเร็วแค่ไหน",
                  _state(qoq, 10.0, 20.0, True), qoq, "%/ไตรมาส", 10.0, 20.0,
                  f"หนี้รวมทั้งชั้นไปจาก {round(prev / 1e9, 1)}B เป็น {round(now / 1e9, 1)}B "
                  f"ในไตรมาสเดียว ({qoq:+.1f}%)", rows)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ตลาดเริ่มตีราคาใหม่หรือยัง — มาก่อนงบการเงินเสมอ
# ─────────────────────────────────────────────────────────────────────────────
def credit_stress(data: dict, days: int = 60) -> Signal:
    """หุ้นกู้เครดิตอ่อน (HYG) ทำได้แย่กว่าเครดิตแข็ง (LQD) กี่ pp ใน 60 วันทำการ.

    นี่คือสัญญาณที่ใกล้กลไกจริงที่สุดเท่าที่ข้อมูลฟรีให้ได้: ถ้าดีลกู้ซื้อ GPU จะพัง มัน
    ต้องพังผ่านตลาดเครดิต ไม่ใช่ผ่านราคาหุ้น. ปกติสองตัวนี้วิ่งห่างกันในระดับ ±1-2pp
    ส่วน −5pp ใน 3 เดือนคือขนาดที่เห็นตอนปี 2008/2020/2022

    **ข้อจำกัดที่ต้องรู้:** HYG ครอบหุ้นกู้ผลตอบแทนสูงทั้งตลาด ไม่ได้เจาะเฉพาะหนี้ที่ค้ำด้วย
    GPU (ซึ่งส่วนใหญ่เป็นสินเชื่อเอกชน ไม่ซื้อขายในตลาด) — จึงเป็นตัวแทนหยาบ ไม่ใช่ของจริง"""
    hyg = _pct_change(_closes(data, "HYG"), days)
    lqd = _pct_change(_closes(data, "LQD"), days)
    if hyg is None or lqd is None:
        return Signal("credit_stress", "ตลาดเครดิตเริ่มตึงหรือยัง", UNKNOWN, None, "pp",
                      -2.0, -5.0, "ดึงราคา HYG/LQD ไม่ได้", [], "ไม่มีราคา HYG หรือ LQD")

    spread = round(hyg - lqd, 2)
    return Signal("credit_stress", "ตลาดเครดิตเริ่มตึงหรือยัง",
                  _state(spread, -2.0, -5.0, False), spread, "pp", -2.0, -5.0,
                  f"ใน {days} วันทำการ เครดิตอ่อนทำได้ {spread:+.2f}pp เทียบเครดิตแข็ง "
                  f"(HYG {hyg:+.2f}% vs LQD {lqd:+.2f}%)",
                  [{"ticker": "HYG", "pct": hyg}, {"ticker": "LQD", "pct": lqd}])


def levered_vs_market(data: dict, days: int = 60) -> Signal:
    """ตะกร้าชั้นที่กู้เงิน ทำได้แย่กว่า S&P 500 กี่ pp ใน 60 วันทำการ.

    ต้องเทียบกับตลาดเสมอ — "หุ้นกลุ่มนี้ลง 20%" ไม่มีความหมายถ้าทั้งตลาดลง 20%
    กลุ่มนี้มีค่าเบต้าราว 2-3 เท่าโดยธรรมชาติ ตลาดลง 10% จึงลง 20-30% เป็นเรื่องปกติ
    ส่วนที่ **แย่กว่าตลาดเกิน 25pp** คือความเครียดเฉพาะตัว ไม่ใช่เบต้า"""
    basket = _basket_change(data, LEVERED, days)
    spy = _pct_change(_closes(data, "SPY"), days)
    if basket is None or spy is None:
        return Signal("levered_vs_market", "ชั้นที่กู้เงิน โดนเทเทียบตลาดแค่ไหน", UNKNOWN, None,
                      "pp", -15.0, -25.0, "ดึงราคาไม่ได้", [], "ไม่มีราคาตะกร้าหรือ SPY")

    rel = round(basket - spy, 2)
    rows = [{"ticker": t, "pct": _pct_change(_closes(data, t), days)} for t in LEVERED]
    return Signal("levered_vs_market", "ชั้นที่กู้เงิน โดนเทเทียบตลาดแค่ไหน",
                  _state(rel, -15.0, -25.0, False), rel, "pp", -15.0, -25.0,
                  f"ใน {days} วันทำการ ตะกร้านี้ {basket:+.1f}% เทียบตลาด {spy:+.1f}% "
                  f"= {rel:+.1f}pp", rows)


def power_vs_market(data: dict, days: int = 60) -> Signal:
    """ตะกร้าไฟฟ้าเทียบตลาด — ตัวแทนของ 'ตลาดยังเชื่อว่าจะมีการสร้าง datacenter จริงไหม'.

    ไฟฟ้าเป็นข้อจำกัดทางกายภาพที่ปลอมไม่ได้: จะเซ็นสัญญาเช่ากี่ฉบับก็ได้ แต่ถ้าไม่มีไฟ
    ก็เปิดเครื่องไม่ได้ กลุ่มนี้จึงตีราคาปริมาณที่จะสร้าง**จริง** ไม่ใช่ปริมาณที่ประกาศ"""
    basket = _basket_change(data, POWER, days)
    spy = _pct_change(_closes(data, "SPY"), days)
    if basket is None or spy is None:
        return Signal("power_vs_market", "กลุ่มไฟฟ้ายังเชื่อการสร้างจริงไหม", UNKNOWN, None,
                      "pp", -15.0, -25.0, "ดึงราคาไม่ได้", [], "ไม่มีราคาตะกร้าหรือ SPY")

    rel = round(basket - spy, 2)
    rows = [{"ticker": t, "pct": _pct_change(_closes(data, t), days)} for t in POWER]
    return Signal("power_vs_market", "กลุ่มไฟฟ้ายังเชื่อการสร้างจริงไหม",
                  _state(rel, -15.0, -25.0, False), rel, "pp", -15.0, -25.0,
                  f"ใน {days} วันทำการ ตะกร้าไฟฟ้า {basket:+.1f}% เทียบตลาด {spy:+.1f}% "
                  f"= {rel:+.1f}pp", rows)


SIGNALS = (hyperscaler_fcf, capex_vs_depreciation, neocloud_leverage,
           neocloud_debt_growth, credit_stress, levered_vs_market, power_vs_market)


def worst_state(signals) -> str:
    """สถานะรวม = ตัวที่แย่ที่สุด ไม่ใช่ค่าเฉลี่ย — เฉลี่ยจะกลบสัญญาณเดียวที่กำลังกรีดร้อง"""
    return max((s.state for s in signals), key=lambda st: _SEVERITY[st], default=UNKNOWN)
