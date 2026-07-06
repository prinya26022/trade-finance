"""Cross-day change detection (Phase 3).

เทียบผลวิเคราะห์ 2 ครั้งล่าสุดของ ticker หนึ่ง แล้วรายงาน "เฉพาะสิ่งที่แตะ thesis"
— ตามหลักลงทุนระยะยาว: เงียบเป็นค่าตั้งต้น เตือนเมื่อมีอะไรเปลี่ยนที่ 'สำคัญ' เท่านั้น
(ไม่เตือนเพราะราคาขยับรายวัน — นั่นคือ noise).

ทำงานล้วนๆ กับข้อมูลใน history store (ไม่เรียก LLM -> ไม่กินโควตา).
"""
from src.history.store import history

# เมตริกที่ถือว่า "สำคัญพอจะเตือน" ถ้าขยับแรง (ตัวอื่นเช่น Market Cap แกว่งตามราคา = noise)
MATERIAL_METRICS = {
    "ROIC", "ROE", "Net Margin", "Operating Margin", "Gross Margin",
    "Net Debt / EBITDA", "Interest Coverage", "Current Ratio",
    "DSO", "Inventory % Revenue", "Free Cash Flow", "Revenue",
    "Goodwill % Assets", "Revenue CAGR",
}
METRIC_MOVE_THRESHOLD = 0.15   # ขยับเกิน 15% (relative) ถึงเตือน


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


def detect_changes(ticker: str) -> dict:
    """คืน dict สรุปการเปลี่ยนแปลงที่แตะ thesis ระหว่าง 2 ครั้งล่าสุด.
    changes ว่าง = ไม่มีอะไรสำคัญ (เงียบไว้ ไม่ต้องเตือน)."""
    rows = history(ticker, limit=2)   # [ล่าสุด, ก่อนหน้า]
    if len(rows) < 2:
        return {"ticker": ticker, "changes": [], "note": "ยังไม่มีผลก่อนหน้าให้เทียบ"}

    cur, prev = rows[0], rows[1]
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

    return {
        "ticker": ticker,
        "from": prev["run_at"],
        "to": cur["run_at"],
        "changes": changes,
    }
