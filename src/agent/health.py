"""Health score 0-10 — สรุป 'สุขภาพธุรกิจโดยรวม' จากสัญญาณที่ eval/LLM สรุปมาแล้ว.

เป็น heuristic แบบ deterministic + โปร่งใส (ไม่เรียก LLM ซ้ำ, ไม่ใช่คำแนะนำซื้อขาย —
แค่ 'ภาพรวมคุณภาพ' ให้ triage ง่ายขึ้น). คำนวณตอน analyze() แล้วเก็บลง DB ทุกครั้ง
(ต่างจากเดิมที่ web/lib/health.ts คำนวณสดฝั่ง frontend อย่างเดียว ไม่มีประวัติ) —
เพื่อดู trend ย้อนหลังได้ และถ้าคะแนนเด้งผิดปกติ เห็นได้ว่า 'เหตุผล' ตอนนั้นคืออะไร
(เป็นอีกชั้นของ eval: ช่วยจับความผิดปกติของ pipeline เอง ไม่ใช่แค่ของธุรกิจ).

สูตรตรงกับ web/lib/health.ts เป๊ะ — ถ้าแก้ที่นี่ ต้องแก้อีกฝั่งด้วย (ฝั่ง TS ใช้เป็น
fallback สำหรับแถวเก่าก่อนมีคอลัมน์นี้เท่านั้น).
"""
STRENGTH_PTS = {"strong": 4, "mixed": 2, "weak": 0}
VALUATION_PTS = {"cheap": 3, "fair": 2, "unclear": 1.5, "expensive": 0.5}
SENTIMENT_PTS = {"bullish": 2, "neutral": 1, "bearish": 0}


def compute_health(summary, breaches: list[dict] | None = None) -> dict:
    """summary = Pydantic Summary (ต้องการ fundamental_strength/valuation_view/sentiment/confidence),
    breaches = ผลจาก check_invalidation(ticker)['breaches'] (severity 'alert' = เงื่อนไขออกโดนแตะ).
    คืน dict: score (0-10), tier (strong/ok/weak), label (ไทย), reasons (list[str] โปร่งใส),
    components (dict คะแนนย่อยต่อองค์ประกอบ — ใช้ diff ระหว่าง 2 รอบเพื่อหาว่า 'อะไรขับ' คะแนน
    ที่กระโดด แทนที่จะต้อง parse ข้อความ reasons; ดู src/agent/changes.py::_diff)."""
    reasons: list[str] = []
    components: dict[str, float] = {}

    strength = STRENGTH_PTS.get(summary.fundamental_strength, 2)
    reasons.append(f"พื้นฐาน {summary.fundamental_strength} (+{strength:g}/4)")
    components["strength"] = strength

    valuation = VALUATION_PTS.get(summary.valuation_view, 1.5)
    reasons.append(f"ราคา {summary.valuation_view} (+{valuation:g}/3)")
    components["valuation"] = valuation

    sentiment = SENTIMENT_PTS.get(summary.sentiment, 1)
    reasons.append(f"มุมมอง {summary.sentiment} (+{sentiment:g}/2)")
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
