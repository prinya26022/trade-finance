"""Cross-day change detection (Phase 3).

เทียบผลวิเคราะห์ 2 ครั้งล่าสุดของ ticker หนึ่ง แล้วรายงาน "เฉพาะสิ่งที่แตะ thesis"
— ตามหลักลงทุนระยะยาว: เงียบเป็นค่าตั้งต้น เตือนเมื่อมีอะไรเปลี่ยนที่ 'สำคัญ' เท่านั้น
(ไม่เตือนเพราะราคาขยับรายวัน — นั่นคือ noise).

ทำงานล้วนๆ กับข้อมูลใน history store (ไม่เรียก LLM -> ไม่กินโควตา).
"""
from datetime import datetime, timedelta

from src.history.store import history

# เมตริกที่ถือว่า "สำคัญพอจะเตือน" ถ้าขยับแรง (ตัวอื่นเช่น Market Cap แกว่งตามราคา = noise)
MATERIAL_METRICS = {
    "ROIC", "ROE", "Net Margin", "Operating Margin", "Gross Margin",
    "Net Debt / EBITDA", "Interest Coverage", "Current Ratio",
    "DSO", "Inventory % Revenue", "Free Cash Flow", "Revenue",
    "Goodwill % Assets", "Revenue CAGR",
}
METRIC_MOVE_THRESHOLD = 0.15   # ขยับเกิน 15% (relative) ถึงเตือน

# คะแนนสุขภาพกระโดดเกินนี้ (จุด, เต็ม 10) ถึงจะเตือน — ต่ำกว่านี้ถือเป็นแกว่งเล็กน้อยปกติ
# (เช่น confidence ขยับ 0.85->0.9 ทำให้คะแนนต่างกันแค่ 0.05 ไม่ใช่เรื่องต้องเตือน)
HEALTH_JUMP_THRESHOLD = 1.5

# เอาไว้แปล component ที่ขยับแรงสุด -> ข้อความอ่านง่าย พร้อมค่า summary ที่เปลี่ยน (ถ้ามี)
# Phase 18: 'confidence' ไม่ใช่ component ของคะแนนแล้ว (สเปกไม่รวม) — เอาออกจาก mapping นี้
_HEALTH_COMPONENT_LABEL = {
    "strength": ("พื้นฐาน (Piotroski)", None),      # ไม่มี summary field เดี่ยวๆ ให้เทียบตรงๆ แล้ว (คะแนนมาจากหลายเกณฑ์รวมกัน)
    "valuation": ("มุมมองราคา (reverse-DCF)", None),  # เช่นกัน — เป็นตัวเลข gap ไม่ใช่ label เดี่ยวๆ
    "sentiment": ("มุมมองข่าว", "sentiment"),
    "breach_penalty": ("เงื่อนไขออกโดนแตะเปลี่ยน", None),
}


def _fy_int(period: str) -> int:
    """'FY2025' -> 2025 (ไว้หา period ล่าสุด). ไม่ใช่ FY -> -1."""
    try:
        return int(str(period).replace("FY", ""))
    except ValueError:
        return -1


def _latest_by_label(facts: list[dict]) -> dict[str, tuple[str, float]]:
    """จาก facts ทั้งหมด เลือก 'ค่างวดล่าสุด' ของแต่ละ label -> {label: (period, value)}."""
    out: dict[str, tuple[str, float]] = {}
    for f in facts:
        label, period, value = f.get("label"), f.get("period", ""), f.get("value")
        if label is None or value is None:
            continue
        if label not in out or _fy_int(period) > _fy_int(out[label][0]):
            out[label] = (period, float(value))
    return out


def _metric_changes(cur_facts: list[dict], prev_facts: list[dict]) -> list[dict]:
    """เทียบเมตริกสำคัญของ 'งวดล่าสุด' ระหว่าง 2 ครั้ง.
    ปกติรายวันจะเท่ากัน (งบไม่เปลี่ยนทุกวัน) -> เตือนตอนงบใหม่ออกหรือค่าขยับแรงเท่านั้น."""
    if not cur_facts or not prev_facts:
        return []
    cur, prev = _latest_by_label(cur_facts), _latest_by_label(prev_facts)
    changes = []
    for label in MATERIAL_METRICS:
        if label not in cur or label not in prev:
            continue
        (cur_period, cur_val), (prev_period, prev_val) = cur[label], prev[label]
        # งบปีใหม่ออก (period เดินหน้า) = สัญญาณ "มี filing ใหม่"
        if _fy_int(cur_period) > _fy_int(prev_period):
            changes.append({
                "type": "new_filing",
                "metric": label,
                "detail": f"งบใหม่: {label} {prev_period}={prev_val:g} → {cur_period}={cur_val:g}",
                "severity": "info",
            })
            continue
        # งวดเดียวกันแต่ค่าขยับแรง (แก้งบย้อนหลัง/ข้อมูลปรับ)
        if prev_val and abs(cur_val - prev_val) / abs(prev_val) >= METRIC_MOVE_THRESHOLD:
            direction = "ขึ้น" if cur_val > prev_val else "ลง"
            changes.append({
                "type": "metric_move",
                "metric": label,
                "detail": f"{label} {direction} {prev_val:g} → {cur_val:g} ({cur_period})",
                "severity": "warn",
            })
    return changes


def _health_jump_driver(ch: dict, ph: dict, cs: dict, ps: dict) -> str:
    """หา component ที่ขยับแรงสุดระหว่าง 2 รอบ (จาก health['components']) แล้วแปลเป็นข้อความ
    อ่านง่าย เช่น 'มุมมองราคา expensive→cheap' — ให้เห็นว่า 'อะไรขับ' คะแนนที่กระโดด ไม่ใช่แค่
    บอกว่ากระโดด (ผู้ใช้ถามหา 'เหตุผล' ตอนคะแนนเด้งผิดปกติ)."""
    cur_c, prev_c = ch.get("components") or {}, ph.get("components") or {}
    deltas = {k: cur_c.get(k, 0) - prev_c.get(k, 0) for k in cur_c}
    driver_key = max(deltas, key=lambda k: abs(deltas[k]), default=None)
    if driver_key is None:
        return ""
    label, summary_key = _HEALTH_COMPONENT_LABEL.get(driver_key, (driver_key, None))
    if driver_key == "confidence" and "confidence" in cs and "confidence" in ps:
        return f"{label} {ps['confidence']:.2f}→{cs['confidence']:.2f}"
    if summary_key and summary_key in cs and summary_key in ps and cs[summary_key] != ps[summary_key]:
        return f"{label} {ps[summary_key]}→{cs[summary_key]}"
    return f"{label} ({deltas[driver_key]:+.1f})"


def _diff(cur: dict, prev: dict) -> list[dict]:
    """เทียบ 2 แถวผลวิเคราะห์ (cur ใหม่กว่า prev) -> list การเปลี่ยนที่แตะ thesis.
    เป็นแกนกลางที่ทั้ง detect_changes (คู่ล่าสุด) และ changes_over_window (สะสมหลายคู่) ใช้ร่วมกัน."""
    cs, ps = cur["summary"], prev["summary"]
    changes: list[dict] = []

    # 1) คำตัดสินพื้นฐานพลิก (strong <-> mixed <-> weak) = thesis สั่นแรงสุด
    if cs["fundamental_strength"] != ps["fundamental_strength"]:
        changes.append({
            "type": "strength_flip",
            "detail": f"พื้นฐานเปลี่ยน: {ps['fundamental_strength']} → {cs['fundamental_strength']}",
            "severity": "alert",
        })

    # 2) มุมมองราคาพลิก (เช่น expensive -> cheap = margin of safety โผล่)
    if cs["valuation_view"] != ps["valuation_view"]:
        changes.append({
            "type": "valuation_flip",
            "detail": f"ราคาเปลี่ยนมุมมอง: {ps['valuation_view']} → {cs['valuation_view']}",
            "severity": "warn",
        })

    # 3) ข่าวที่แตะ thesis 'ชิ้นใหม่' (ไม่เคยมีในครั้งก่อน)
    prev_news = set(ps.get("thesis_relevant_news", []))
    for n in cs.get("thesis_relevant_news", []):
        if n not in prev_news:
            changes.append({"type": "thesis_news", "detail": n, "severity": "warn"})

    # 4) ความน่าเชื่อถือของข้อมูลตก (facts grounding ลดแรง) = เตือนให้ระวังผล
    cf, pf = cur.get("facts_grounded_ratio"), prev.get("facts_grounded_ratio")
    if cf is not None and pf is not None and cf - pf <= -0.2:
        changes.append({
            "type": "trust_drop",
            "detail": f"ความแม่นตัวเลขงบตก {pf:.0%} → {cf:.0%} — ตรวจสอบก่อนเชื่อ",
            "severity": "warn",
        })

    # 5) เมตริกพื้นฐานสำคัญขยับ / มีงบใหม่
    changes += _metric_changes(cur.get("facts", []), prev.get("facts", []))

    # 6) คะแนนสุขภาพกระโดดแรง — สลายเป็น component ที่ขับ ให้เห็นว่า 'ทำไม' ไม่ใช่แค่ 'เปลี่ยน'
    # (แถวเก่าก่อน Phase 10/16 ไม่มี health หรือไม่มี components -> เงียบไว้ ไม่ crash; แถวที่
    # 'excluded' — Phase 18, ข้อมูลไม่พอ/ขาดทุน/crypto — score เป็น None ก็ต้อง guard เหมือนกัน
    # ไม่งั้น None - number ระเบิด)
    ch, ph = cur.get("health"), prev.get("health")
    if (ch and ph and ch.get("components") and ph.get("components")
            and ch.get("score") is not None and ph.get("score") is not None):
        delta = ch["score"] - ph["score"]
        if abs(delta) >= HEALTH_JUMP_THRESHOLD:
            direction = "พุ่งขึ้น" if delta > 0 else "ร่วงลง"
            driver = _health_jump_driver(ch, ph, cs, ps)
            changes.append({
                "type": "health_jump",
                "detail": f"คะแนนสุขภาพ{direction} {ph['score']:.1f} → {ch['score']:.1f} "
                          f"({delta:+.1f}) — หลักๆจาก{driver}",
                "severity": "warn",
            })

    return changes


def _current_invalidation(ticker: str) -> list[dict]:
    """invalidation breach ของสถานะปัจจุบัน (เงื่อนไขออกที่ผู้ใช้ตั้งเองโดนแตะ).
    lazy import กัน circular: invalidation.py ใช้ _latest_by_label จากไฟล์นี้."""
    from src.agent.invalidation import check_invalidation
    return check_invalidation(ticker)["breaches"]


def detect_changes(ticker: str) -> dict:
    """คืน dict สรุปสิ่งที่ต้องดู: invalidation breach (เงื่อนไขออกของผู้ใช้) มาก่อนเสมอ
    ตามด้วยการเปลี่ยนแปลงระหว่าง 2 ครั้งล่าสุด. changes ว่าง = ไม่มีอะไรสำคัญ (เงียบไว้).
    หมายเหตุ: invalidation เช็คได้แม้มีผลวิเคราะห์แค่ครั้งเดียว (เทียบสถานะปัจจุบันกับ rule
    ไม่ใช่เทียบกับครั้งก่อน) จึงไม่ติด guard len(rows) < 2 เหมือน diff."""
    breaches = _current_invalidation(ticker)   # ขึ้นก่อน (severity alert — เรื่องเงื่อนไขที่ *คุณ* ตั้ง)

    rows = history(ticker, limit=2)   # [ล่าสุด, ก่อนหน้า]
    diff_changes = _diff(rows[0], rows[1]) if len(rows) >= 2 else []

    result = {"ticker": ticker, "changes": breaches + diff_changes}
    if len(rows) >= 2:
        result["from"], result["to"] = rows[1]["run_at"], rows[0]["run_at"]
    else:
        result["note"] = "ยังไม่มีผลก่อนหน้าให้เทียบ (แสดงเฉพาะ invalidation)"
    return result


def changes_over_window(ticker: str, days: int) -> list[dict]:
    """สะสมการเปลี่ยนแปลงทุกคู่ต่อเนื่องกันในช่วง `days` วันที่ผ่านมา (ไว้ทำ weekly/monthly report).
    เดินจากเก่าไปใหม่ เทียบทีละคู่ติดกัน -> ได้การเปลี่ยนแปลง 'สะสม' ตลอดช่วง ไม่ใช่แค่ต้น-ท้าย
    (เพราะถ้าขยับขึ้นแล้วลงกลับมาที่เดิม ก็ยังถือว่าเคยมีสัญญาณเตือนระหว่างทาง ไม่อยากให้หายไป)."""
    # invalidation breach ปัจจุบันขึ้นก่อนเสมอ (สำคัญสุด ต้องเห็นทุก cadence — แม้มี run เดียว)
    out: list[dict] = list(_current_invalidation(ticker))

    rows = history(ticker, limit=200)   # ใหม่สุดก่อน (DESC)
    if len(rows) < 2:
        return out

    cutoff = datetime.now() - timedelta(days=days)
    windowed = []
    for r in rows:
        windowed.append(r)
        if datetime.fromisoformat(r["run_at"]) < cutoff:
            break   # เก็บ 1 แถวที่เก่ากว่า cutoff ไว้เป็น 'จุดเทียบตั้งต้น' ของหน้าต่างนี้
    windowed.reverse()   # กลับเป็นเก่า -> ใหม่

    for i in range(1, len(windowed)):
        prev_row, cur_row = windowed[i - 1], windowed[i]
        for c in _diff(cur_row, prev_row):
            out.append({**c, "as_of": cur_row["run_at"]})
    return out
