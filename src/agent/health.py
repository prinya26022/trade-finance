"""Health score 0-10 — สรุป 'สุขภาพธุรกิจโดยรวม' ผสมตัวเลขจริง (Piotroski-style +
reverse-DCF) เข้ากับ label ของ LLM แทนที่จะเชื่อ label ล้วนๆ เหมือนเดิม (Phase 17)

ทำไมเปลี่ยน: สูตรเดิม (Phase 10) เป็นแค่ bucket lookup 4 อัน (strong/mixed/weak,
cheap/fair/unclear/expensive, bullish/neutral/bearish) ที่มาจากการตีความของ LLM
ล้วนๆ — วันไหน LLM ตีความ valuation ต่างจากเดิมนิดเดียว (เช่น expensive -> cheap)
คะแนนกระโดดได้ถึง 2.5-4 แต้มทันที ทั้งที่ธุรกิจไม่ได้เปลี่ยนอะไรเลย (เจอจริงกับ MSFT/NVDA
วันเดียวกัน — ดู commit ที่เพิ่ม changes.py::health_jump).

หลักการใหม่ 'ตัวเลขจริงเป็นหลัก, LLM label เป็น fallback เวลาข้อมูลไม่พอ':
- พื้นฐาน (strength, เต็ม 5): Piotroski-F-Score-style checklist จากตัวเลขจริงใน facts
  (ROIC/ROE/FCF/leverage/สภาพคล่อง/margin trend/dilution) — นับกี่เกณฑ์ผ่านจากกี่เกณฑ์
  ที่คำนวณได้ (ข้อมูลขาด = ข้าม ไม่ใช่ fail กัน penalize บริษัทที่ไม่มีข้อมูลบางอย่าง เช่น
  ไม่มีหนี้เลยจนไม่มี Fact 'Net Debt / EBITDA'). ไม่มี facts พอเช็คเลย -> fallback ไปใช้
  label ของ LLM (สเกลใหม่เป็น /5)
- ราคา (valuation, เต็ม 3): ใช้ reverse-DCF gap (Phase 15: implied growth ที่ตลาด
  price ไว้ ลบด้วย historical revenue CAGR จริง) แทนป้าย cheap/fair/expensive — gap
  ติดลบมาก (ตลาดคาดหวังน้อยกว่าที่เคยทำได้จริง) = ถูก/มี margin of safety, gap บวกมาก
  (คาดหวังเวอร์กว่าผลงานจริง) = แพง/เสี่ยง. คำนวณ reverse-DCF ไม่ได้ (FCF ติดลบ/ราคานอก
  ขอบเขตโมเดล) -> fallback ไปใช้ label ของ LLM เหมือนเดิม
- มุมมองข่าว (sentiment, เต็ม 1): ลดน้ำหนักลงครึ่งหนึ่งจากเดิม (เดิมเต็ม 2) เพราะเป็น
  สัญญาณ noise สุดในบรรดา 4 ตัว — เปลี่ยนได้ทุกวันตามข่าว ไม่ได้แปลว่าธุรกิจเปลี่ยนจริง
- ความมั่นใจข้อมูล (confidence, เต็ม 1): เหมือนเดิม (ความมั่นใจของ LLM เอง 0-1)

คำนวณตอน analyze() แล้วเก็บลง DB ทุกครั้ง เพื่อดู trend ย้อนหลัง + เห็นเหตุผลตอนคะแนน
กระโดดผิดปกติ. `components` คง key เดิมทั้ง 5 ตัว (strength/valuation/sentiment/
confidence/breach_penalty) แม้วิธีคำนวณข้างในจะเปลี่ยน — changes.py::_diff (Phase 16)
diff จาก key พวกนี้หา 'ตัวขับ' คะแนนที่กระโดด จึงยังทำงานได้โดยไม่ต้องแก้.

facts รับได้ทั้ง list[Fact] (dataclass, จาก analyze() สดๆ) และ list[dict] (จาก
history ที่ deserialize จาก JSON — ใช้ตอน backfill คะแนนย้อนหลัง) — normalize ให้
เหมือนกันตั้งแต่ต้นฟังก์ชัน. ไม่ใส่ facts เลย (None) -> ทุก component fallback ไป LLM
label ล้วนๆ (เหมือนพฤติกรรมเดิมก่อน Phase 17 ทุกประการ).

หมายเหตุ: web/lib/health.ts ("Phase 10 formula") เป็น fallback ฝั่ง frontend สำหรับ
แถวเก่าก่อนมีคอลัมน์ persisted เท่านั้น (คำนวณสดตอนนั้นไม่มี facts/reverse-DCF ให้ใช้ในตัว
component ฝั่ง browser) — ไม่ต้องตรงกับไฟล์นี้เป๊ะอีกต่อไป เพราะ Python คือ source of
truth เดียวตั้งแต่ Phase 10.
"""
from types import SimpleNamespace

from src.agent.valuation import reverse_dcf

# --- fallback buckets: ใช้เมื่อคำนวณจากตัวเลขจริงไม่ได้ (facts ไม่พอ / DCF หาคำตอบไม่ได้) ---
STRENGTH_FALLBACK_PTS = {"strong": 5.0, "mixed": 2.5, "weak": 0.0}   # เดิมเต็ม 4 -> สเกลเป็นเต็ม 5
VALUATION_FALLBACK_PTS = {"cheap": 3.0, "fair": 2.0, "unclear": 1.5, "expensive": 0.5}
SENTIMENT_PTS = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}   # เดิมเต็ม 2 -> ลดครึ่งเหลือเต็ม 1

# เกณฑ์ตัวเลข (heuristic มาตรฐานการเงินทั่วไป ไม่ใช่กฎตายตัว — ปรับได้)
ROIC_THRESHOLD_PCT = 8.0     # สูงกว่าต้นทุนทุนโดยประมาณ
ROE_THRESHOLD_PCT = 10.0
LEVERAGE_MAX_X = 3.0         # Net Debt/EBITDA เกินนี้เริ่มเสี่ยง
CURRENT_RATIO_MIN_X = 1.0    # สภาพคล่องพอจ่ายหนี้ระยะสั้น
GAP_CLAMP_PP = 15.0          # reverse-DCF gap ที่ถือว่า 'สุดขั้ว' แล้ว (จุดร้อยละ) — เกินนี้ clamp กันคะแนนสวิงเกินเหตุ


def _normalize_facts(facts) -> list[dict]:
    """list[Fact] (dataclass) หรือ list[dict] (จาก JSON) -> list[dict] รูปแบบเดียวกันหมด."""
    if not facts:
        return []
    out = []
    for f in facts:
        if hasattr(f, "label"):
            out.append({"label": f.label, "value": f.value, "unit": f.unit, "period": f.period})
        else:
            out.append(f)
    return out


def _scalar(facts: list[dict], label: str) -> float | None:
    """ค่าสเกลาร์ของ label (มีค่าเดียวต่อ label สำหรับเมตริกกลุ่มนี้ — ไม่ใช่อนุกรมหลายปี)."""
    for f in facts:
        if f["label"] == label and f["value"] is not None:
            return float(f["value"])
    return None


def _fy_series(facts: list[dict], label: str) -> list[tuple[str, float]]:
    """อนุกรมรายปี (period ขึ้นต้นด้วย FY) ของ label หนึ่ง เรียงเก่า -> ใหม่."""
    pts = [(f["period"], float(f["value"])) for f in facts
           if f["label"] == label and str(f.get("period", "")).startswith("FY")]
    return sorted(pts, key=lambda p: p[0])


# --- Piotroski-style criteria: check(facts) -> True (ผ่าน) | False (ไม่ผ่าน) | None (ข้อมูลไม่พอ) ---
def _criterion_roic(facts):
    v = _scalar(facts, "ROIC")
    return None if v is None else v > ROIC_THRESHOLD_PCT


def _criterion_roe(facts):
    v = _scalar(facts, "ROE")
    return None if v is None else v > ROE_THRESHOLD_PCT


def _criterion_fcf_positive(facts):
    v = _scalar(facts, "FCF Margin")
    return None if v is None else v > 0.0


def _criterion_revenue_growing(facts):
    v = _scalar(facts, "Revenue CAGR")
    return None if v is None else v > 0.0


def _criterion_leverage_safe(facts):
    v = _scalar(facts, "Net Debt / EBITDA")
    return None if v is None else v < LEVERAGE_MAX_X


def _criterion_liquid(facts):
    v = _scalar(facts, "Current Ratio")
    return None if v is None else v >= CURRENT_RATIO_MIN_X


def _criterion_margin_improving(facts):
    pts = _fy_series(facts, "Operating Margin")
    return None if len(pts) < 2 else pts[-1][1] >= pts[-2][1]


def _criterion_not_diluting(facts):
    pts = _fy_series(facts, "Diluted Shares")
    return None if len(pts) < 2 else pts[-1][1] <= pts[-2][1]


PIOTROSKI_CRITERIA = [
    ("ROIC>8%", _criterion_roic),
    ("ROE>10%", _criterion_roe),
    ("FCF เป็นบวก", _criterion_fcf_positive),
    ("รายได้โตต่อเนื่อง", _criterion_revenue_growing),
    ("หนี้ปลอดภัย", _criterion_leverage_safe),
    ("สภาพคล่องดี", _criterion_liquid),
    ("Margin ดีขึ้น", _criterion_margin_improving),
    ("ไม่เจือจางผู้ถือหุ้น", _criterion_not_diluting),
]


def _strength_points(summary, facts: list[dict]) -> tuple[float, str]:
    results = [(label, check(facts)) for label, check in PIOTROSKI_CRITERIA]
    computable = [(label, ok) for label, ok in results if ok is not None]
    if not computable:
        pts = STRENGTH_FALLBACK_PTS.get(summary.fundamental_strength, 2.5)
        return pts, f"พื้นฐาน (จาก LLM, ไม่มีตัวเลขพอเช็ค Piotroski) {summary.fundamental_strength} (+{pts:g}/5)"
    passed = [label for label, ok in computable if ok]
    pts = round(5.0 * len(passed) / len(computable), 2)
    passed_text = ", ".join(passed) if passed else "ไม่ผ่านเกณฑ์ไหนเลย"
    return pts, f"พื้นฐาน: ผ่าน {len(passed)}/{len(computable)} เกณฑ์ ({passed_text}) (+{pts:g}/5)"


def _valuation_points(summary, facts: list[dict]) -> tuple[float, str]:
    market_cap = _scalar(facts, "Market Cap")
    fcf_yield = _scalar(facts, "FCF Yield")
    historical_cagr = _scalar(facts, "Revenue CAGR")
    if market_cap and fcf_yield is not None:
        # ย้อน FCF ดอลลาร์กลับจาก FCF Yield ที่เก็บไว้ (fcf = fcf_yield% * market_cap) —
        # ไม่ต้องพึ่งอ็อบเจกต์ StockFundamentals ตัวเต็ม ใช้ได้ทั้งตอนวิเคราะห์สดและ backfill
        # ย้อนหลังจาก facts ที่เก็บไว้ใน DB (คนละ code path แต่ผลเหมือนกัน)
        fcf = fcf_yield / 100.0 * market_cap
        fund_like = SimpleNamespace(free_cash_flow=fcf, market_cap=market_cap, revenue_cagr=historical_cagr)
        dcf = reverse_dcf(fund_like)
        if dcf and dcf["implied_growth"] is not None and dcf["historical_cagr"] is not None:
            gap = dcf["gap"]
            clamped = max(-GAP_CLAMP_PP, min(GAP_CLAMP_PP, gap))
            pts = round(3.0 * (1 - (clamped + GAP_CLAMP_PP) / (2 * GAP_CLAMP_PP)), 2)
            return pts, (
                f"ราคา: ตลาดคาด FCF โต {dcf['implied_growth']:.1f}%/ปี เทียบเคยโตจริง "
                f"{dcf['historical_cagr']:.1f}%/ปี (gap {gap:+.1f}pp, reverse-DCF) (+{pts:g}/3)"
            )
    pts = VALUATION_FALLBACK_PTS.get(summary.valuation_view, 1.5)
    return pts, f"ราคา (จาก LLM, reverse-DCF คำนวณไม่ได้) {summary.valuation_view} (+{pts:g}/3)"


def _sentiment_points(summary) -> tuple[float, str]:
    pts = SENTIMENT_PTS.get(summary.sentiment, 0.5)
    return pts, f"มุมมองข่าว {summary.sentiment} (+{pts:g}/1)"


def compute_health(summary, breaches: list[dict] | None = None, facts=None) -> dict:
    """summary = Pydantic Summary (ต้องการ fundamental_strength/valuation_view/sentiment/
    confidence), breaches = ผลจาก check_invalidation(ticker)['breaches'] (severity 'alert'
    = เงื่อนไขออกโดนแตะ), facts = list[Fact] หรือ list[dict] ของรอบนี้ (ไม่ใส่ = fallback
    ไป LLM label ล้วนๆ ทุก component).
    คืน dict: score (0-10), tier (strong/ok/weak), label (ไทย), reasons (list[str],
    ~4-5 บรรทัด อ่านง่าย — 1 บรรทัดต่อ component แม้เนื้อหาข้างในจะละเอียดขึ้น),
    components (dict คะแนนย่อย 5 key เดิม ให้ changes.py diff หาตัวขับคะแนนที่กระโดด)."""
    facts = _normalize_facts(facts)
    reasons: list[str] = []
    components: dict[str, float] = {}

    strength, r = _strength_points(summary, facts)
    reasons.append(r)
    components["strength"] = strength

    valuation, r = _valuation_points(summary, facts)
    reasons.append(r)
    components["valuation"] = valuation

    sentiment, r = _sentiment_points(summary)
    reasons.append(r)
    components["sentiment"] = sentiment

    conf_pts = max(0.0, min(1.0, summary.confidence))
    reasons.append(f"ความมั่นใจข้อมูล {summary.confidence:g} (+{conf_pts:.1f}/1)")
    components["confidence"] = conf_pts

    score = strength + valuation + sentiment + conf_pts

    has_breach = any(b.get("severity") == "alert" for b in (breaches or []))
    components["breach_penalty"] = -3.0 if has_breach else 0.0
    if has_breach:
        score -= 3
        reasons.append("เงื่อนไขออกโดนแตะ (−3)")

    score = max(0.0, min(10.0, score))
    rounded = round(score, 1)
    tier = "strong" if rounded >= 7 else "ok" if rounded >= 4.5 else "weak"
    label = {"strong": "แข็งแรง", "ok": "พอใช้", "weak": "อ่อน"}[tier]

    return {"score": rounded, "tier": tier, "label": label, "reasons": reasons, "components": components}