"""พิสูจน์ว่า 'ใครเป็นคนตอบ' ไม่ทำให้ตัวเลขที่ระบบใช้ตัดสินเปลี่ยน (Phase 33.4).

ทำไมต้องมี: ตั้งแต่เริ่มเทียบสองสำนัก คำตอบที่ให้ไว้ตลอดคือ "health score ไม่ได้มาจาก LLM
ข้อมูลชุดเดียวกันจึงได้คะแนนเท่ากันไม่ว่าโมเดลไหนตอบ" — นั่นเป็นการอ้างจากการอ่านโค้ด ซึ่งเป็น
หลักฐานที่อ่อนที่สุดชนิดหนึ่ง (โค้ดเปลี่ยนได้ คนอ่านตกหล่นได้ และเคยตกหล่นมาแล้วจริงในเรื่อง
สกุลเงิน). ไฟล์นี้เปลี่ยนคำอ้างนั้นให้เป็นการวัด: ป้อน **facts ชุดเดียวกันเป๊ะ** แล้วสลับเฉพาะ
'บทวิเคราะห์ของใคร' จากนั้นเทียบผลลัพธ์ฝั่ง deterministic ทั้งหมด.

สิ่งที่ **ต้อง** เท่ากันทุกตัว: health score/tier/max, ทุกเกณฑ์ย่อยใน fundamental, ขาราคา
(reverse-DCF หรือ justified P/B), และเงื่อนไขผิด thesis (breaches)
สิ่งที่ **ควร** ต่างได้: sentiment ซึ่งเป็น metadata ล้วนตั้งแต่ 19.3.1 — ต่างได้โดยไม่กระทบคะแนน
(ถ้าวันไหน sentiment กลับมามีผลกับคะแนนอีก eval นี้จะจับได้ทันทีในฐานะ 'คะแนนต่างกัน')
"""
from src.agent.health import compute_health
from src.agent.invalidation import current_breaches


def _score_with(summary_sentiment: str, facts, breaches, risk_free_pct: float) -> dict:
    """คำนวณชั้น deterministic ทั้งหมดโดยให้ LLM มีอิทธิพลได้แค่ทางเดียวเท่าที่โค้ดเปิดช่องไว้
    (คือ summary.sentiment) — ถ้ามีช่องอื่นแอบอยู่ ผลจะออกมาไม่เท่ากันแล้วเทสต์จะฟ้อง."""
    summary = type("S", (), {"sentiment": summary_sentiment})()
    health = compute_health(summary, breaches, facts, risk_free_pct)
    return {
        "score": health["score"],
        "max": health["max"],
        "tier": health["tier"],
        "partial": health.get("partial"),
        "fundamental_score": health["fundamental"]["score"],
        "criteria": health["fundamental"].get("criteria"),
        "valuation_score": (health["valuation"] or {}).get("score"),
        "valuation_reason": (health["valuation"] or {}).get("reason"),
        "breach_penalty": health["components"].get("breach_penalty"),
    }


def compare_one(facts, sentiment_a: str, sentiment_b: str, price: float | None = None,
                thesis: dict | None = None, risk_free_pct: float = 4.0) -> dict:
    """เทียบผล deterministic ของสองบทวิเคราะห์บน facts ชุดเดียวกัน; identical=True คือสิ่งที่ต้องได้."""
    breaches = current_breaches(facts, price, thesis) if price is not None else []
    a = _score_with(sentiment_a, facts, breaches, risk_free_pct)
    b = _score_with(sentiment_b, facts, breaches, risk_free_pct)
    differing = sorted(k for k in a if a[k] != b[k])
    return {"identical": not differing, "differing_fields": differing, "a": a, "b": b}


def check_period(period: str, model: str | None = None) -> dict:
    """รันกับข้อมูลจริงของงวดหนึ่ง: ทุก ticker ที่มีทั้งบทวิเคราะห์จากแชทและรอบรายวัน.

    ใช้ facts จาก pack snapshot (ชุดที่ฝั่งแชทได้อ่านจริง) ให้ทั้งสองฝั่ง — เพื่อให้ตัวแปรเดียว
    ที่ต่างกันคือ 'ใครเขียนบทวิเคราะห์' ไม่ใช่ 'ข้อมูลคนละวัน' ซึ่งจะทำให้พิสูจน์อะไรไม่ได้เลย.
    """
    from src.agent.handoff import load_pack
    from src.history import claude_store
    from src.history.store import get as get_analysis

    pack = load_pack(period)
    facts_by_ticker = {i["ticker"].upper(): i["facts"] for i in pack["items"]}

    rows = []
    for c in claude_store.for_period(period):
        if model is not None and c["model"] != model:
            continue
        facts = facts_by_ticker.get(c["ticker"])
        gemini = get_analysis(c["analysis_id"]) if c.get("analysis_id") else None
        if facts is None or gemini is None:
            rows.append({"ticker": c["ticker"], "skipped": "ไม่มี facts/คู่เทียบ"})
            continue

        result = compare_one(facts, c["sentiment"], gemini["sentiment"])
        rows.append({
            "ticker": c["ticker"],
            "sentiment_chat": c["sentiment"],
            "sentiment_daily": gemini["sentiment"],
            "sentiment_differs": c["sentiment"] != gemini["sentiment"],
            **result,
        })

    compared = [r for r in rows if "identical" in r]
    return {
        "period": period,
        "compared": len(compared),
        "identical": sum(1 for r in compared if r["identical"]),
        "sentiment_differed": sum(1 for r in compared if r["sentiment_differs"]),
        "rows": rows,
    }


def render_text(report: dict) -> str:
    lines = [f"ผลลัพธ์ขึ้นกับ 'ใครตอบ' หรือไม่ — งวด {report['period']}", ""]
    for r in report["rows"]:
        if "identical" not in r:
            lines.append(f"  {r['ticker']:6} ข้าม ({r['skipped']})")
            continue
        mark = "เท่ากันทุกค่า" if r["identical"] else f"ต่าง: {', '.join(r['differing_fields'])}"
        note = "  (โทนต่างกัน)" if r["sentiment_differs"] else ""
        lines.append(f"  {r['ticker']:6} {mark}{note}")

    same = report["identical"] == report["compared"] and report["compared"] > 0
    lines += [
        "",
        f"เทียบได้ {report['compared']} ตัว · ผลตรงกันทุกค่า {report['identical']} ตัว "
        f"· โทนข่าวต่างกัน {report['sentiment_differed']} ตัว",
        "",
        ("สรุป: เปลี่ยนโมเดลไม่ทำให้คะแนน/เกณฑ์ย่อย/ขาราคา/เงื่อนไขผิด thesis เปลี่ยนเลย "
         "แม้โทนข่าวจะต่างกัน" if same else
         "สรุป: มีตัวที่ผลไม่ตรงกัน — แปลว่ามีช่องที่ LLM มีอิทธิพลต่อคะแนนอยู่จริง ต้องตามแก้"),
    ]
    return "\n".join(lines)
