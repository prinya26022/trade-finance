"""Company biography timeline (Phase 14) — เรื่องราวหลายปีว่า 'ทำไมธุรกิจมาอยู่จุดนี้'.

รวม 2 แหล่งที่ material จริง (ไม่ใช่ราคากระตุก — เลี่ยงกับดัก news→price attribution):
  1. เหตุการณ์ที่บริษัทยื่นตามกฎหมาย (8-K signal สูง ย้อนหลังหลายปี จาก EDGAR)
  2. จุดพลิกของพื้นฐาน (margin/revenue/FCF ที่เปลี่ยนอย่างมีนัยจากปีก่อน — จาก facts + XBRL)

build_timeline() = deterministic ล้วน (ไม่เรียก LLM, test ได้) — เป็นโครงกระดูกของเรื่อง.
narrate_timeline() = ให้ LLM เรียงโครงนั้นเป็น 'เรื่องเล่า' 1 ย่อหน้า (research ไม่ใช่คำแนะนำ).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

MARGIN_INFLECTION_PP = 3.0   # margin เปลี่ยน >= 3 percentage points เทียบปีก่อน = จุดพลิกที่ควรเล่า


def _series_from_facts(facts, label: str) -> list[tuple[str, float]]:
    """[(FYxxxx, value), ...] เรียงเก่า->ใหม่ ของ label หนึ่งจาก list[Fact] (เฉพาะงวด FY)."""
    pts = [(f.period, f.value) for f in facts
           if f.label == label and (f.period or "").startswith("FY")]
    return sorted(pts)


def _fy_year(period: str) -> int | None:
    m = period[2:] if period.startswith("FY") else period
    return int(m) if m.isdigit() else None


def _fundamental_inflections(facts, xbrl: dict) -> list[dict]:
    """จุดพลิกพื้นฐานรายปี: margin เปลี่ยนแรง, รายได้หดตัว, FCF พลิกเป็นลบ.
    คืน list ของ event dict (date ประมาณจากปีงบ = สิ้นปีปฏิทินนั้น เพื่อจัดเรียงรวมกับ 8-K ได้)."""
    events: list[dict] = []

    # (1) margin เปลี่ยนแรงเทียบปีก่อน (ขึ้น/ลง >= เกณฑ์)
    for label in ("Operating Margin", "Net Margin", "Gross Margin"):
        series = _series_from_facts(facts, label)
        for (p_prev, v_prev), (p_cur, v_cur) in zip(series, series[1:]):
            delta = v_cur - v_prev
            if abs(delta) >= MARGIN_INFLECTION_PP:
                direction = "พุ่งขึ้น" if delta > 0 else "หดลง"
                year = _fy_year(p_cur)
                events.append({
                    "date": f"{year}-12-31" if year else p_cur,
                    "period": p_cur,
                    "kind": "fundamental",
                    "label": label,
                    "detail": f"{label} {direction} {v_prev:g}% → {v_cur:g}% ({p_cur})",
                })

    # (2) รายได้หดตัว (YoY ติดลบ) — จาก XBRL (ตัวเลขจริงจาก 10-K)
    revenue = sorted((p, v) for p, v in xbrl.get("Revenues", []))
    for (p_prev, v_prev), (p_cur, v_cur) in zip(revenue, revenue[1:]):
        if v_prev and v_cur < v_prev:
            year = _fy_year(p_cur)
            pct = (v_cur - v_prev) / v_prev * 100
            events.append({
                "date": f"{year}-12-31" if year else p_cur,
                "period": p_cur,
                "kind": "fundamental",
                "label": "Revenue",
                "detail": f"รายได้หดตัว {pct:+.1f}% ({p_cur}) — ครั้งแรกที่ไม่โต",
            })

    # (3) FCF พลิกจากบวกเป็นลบ (เผาเงินสด) — สัญญาณคุณภาพกำไรเปลี่ยน
    fcf = _series_from_facts(facts, "Free Cash Flow")
    for (p_prev, v_prev), (p_cur, v_cur) in zip(fcf, fcf[1:]):
        if v_prev > 0 and v_cur < 0:
            year = _fy_year(p_cur)
            events.append({
                "date": f"{year}-12-31" if year else p_cur,
                "period": p_cur,
                "kind": "fundamental",
                "label": "Free Cash Flow",
                "detail": f"FCF พลิกเป็นลบ ({p_cur}) — เริ่มเผาเงินสด",
            })

    return events


def build_timeline(ticker: str) -> list[dict]:
    """โครงเรื่องหลายปี = 8-K material (ย้อนหลัง) + จุดพลิกพื้นฐาน, เรียงใหม่ก่อน.
    deterministic — ไม่เรียก LLM. [] ถ้าดึงข้อมูลไม่ได้เลย."""
    from src.providers.registry import get_providers
    from src.providers.stock.edgar import material_8k_history
    from src.providers.stock.xbrl import get_annual_series

    ticker = ticker.upper()
    try:
        facts = get_providers("stock").fundamentals.get_fundamentals(ticker).to_facts()
    except Exception:
        facts = []
    xbrl = get_annual_series(ticker)

    events: list[dict] = [
        {"date": e["date"], "period": e["date"][:4], "kind": "8-K",
         "label": "SEC 8-K", "detail": e["category"], "url": e.get("url", "")}
        for e in material_8k_history(ticker)
    ]
    events += _fundamental_inflections(facts, xbrl)
    events.sort(key=lambda e: e["date"], reverse=True)   # ใหม่ก่อน (feed style)
    return events


_NARRATE_PROMPT = """You are a fundamental analyst. Below is a chronological timeline of a
company's MATERIAL events (SEC 8-K filings the company was legally required to file) and its
FUNDAMENTAL inflection points (margin/revenue/cash-flow changes from real filings), for {ticker}.

Write in THAI, 3-6 sentences, the STORY of how this business got to where it is today — connect
the material events to the fundamental changes into one coherent arc (e.g. leadership change →
restructuring → margin recovery/decline). Explain what the multi-year picture says about the
business. This is RESEARCH to help an investor understand the company — NOT a buy/sell/timing
call, and do NOT attribute stock-price moves to specific news (you have no price data and that
would be hindsight storytelling). Stick to fundamentals and filed events.

TIMELINE (newest first):
{timeline}
"""


def narrate_timeline(ticker: str, generate=None) -> str:
    """ให้ LLM เรียง timeline เป็น 'เรื่องเล่า' 1 ย่อหน้า. generate = ฟังก์ชัน (prompt)->str
    inject ได้ (test ใช้ของปลอม); default = ยิง Gemini จริง. คืน '' ถ้าไม่มี event ให้เล่า."""
    events = build_timeline(ticker)
    if not events:
        return ""
    timeline_text = "\n".join(f"- {e['date']} [{e['kind']}] {e['detail']}" for e in events)
    prompt = _NARRATE_PROMPT.format(ticker=ticker.upper(), timeline=timeline_text)

    if generate is None:
        generate = _gemini_generate
    return generate(prompt).strip()


def _gemini_generate(prompt: str) -> str:
    import google.genai as genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return resp.text or ""


if __name__ == "__main__":
    # python -m src.agent.timeline SBUX          -> โครง timeline + เรื่องเล่าจาก agent
    # python -m src.agent.timeline SBUX --save    -> narrate แล้วเก็บลง DB (ให้หน้า detail อ่าน)
    import sys

    tk = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    tl = build_timeline(tk)
    print(f"=== {tk} timeline ({len(tl)} events) ===")
    for e in tl:
        print(f"  {e['date']}  [{e['kind']:11}] {e['detail']}")
    print("\n🧠 เรื่องเล่า:")
    narrative = narrate_timeline(tk)
    print(narrative)
    if "--save" in sys.argv and narrative:
        from src.agent.timeline_store import save_narrative
        save_narrative(tk, narrative)
        print(f"\n[saved narrative for {tk}]")