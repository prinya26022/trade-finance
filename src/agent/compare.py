"""เทียบบทวิเคราะห์สองสำนัก: Gemini (อัตโนมัติรายวัน) vs โมเดลที่แปะในแชท (รายเดือน) — Phase 33.

สิ่งที่ **ไม่** ต่างกันแน่ๆ และต้องพูดให้ชัดก่อน: health score ไม่ได้มาจาก LLM เลยตั้งแต่ Phase
17/18 (Piotroski + reverse-DCF จากตัวเลขจริง) ดังนั้นข้อมูลชุดเดียวกัน = คะแนนเท่ากันเป๊ะไม่ว่า
โมเดลไหนตอบ. การเทียบนี้จึงไม่ใช่ 'ใครให้คะแนนสูงกว่า' แต่เป็น 3 อย่างที่ LLM ตัดสินจริง:

1) ป้ายวินิจฉัย — fundamental_strength / valuation_view / sentiment ตรงกันไหม (ไม่ตรง = จุดที่
   ควรไปอ่านเหตุผลของทั้งคู่เอง ไม่ใช่ 'ใครถูก')
2) ความแม่นของการอ้างตัวเลข — facts_grounded_ratio จาก eval ตัวเดียวกัน คือข้อเดียวในนี้ที่
   'ถูก/ผิด' วัดได้จริง
3) ความละเอียด — นับของที่วัดได้: จำนวนตัวเลขที่ยกมาอ้าง, จำนวนจุดอ่อนที่ระบุ, ความยาวสรุป
   (proxy หยาบๆ ยอมรับว่าเยอะไม่เท่ากับดี — จึงโชว์คู่กับ grounding เสมอ ไม่ใช่ตัวเลขเดี่ยว)
"""
from datetime import datetime
from statistics import mean

from src.agent.summarize import Summary
from src.domain.interfaces import Fact
from src.evals.check_grounding import check_facts_grounding
from src.history import claude_store
from src.history.store import get as get_analysis
from src.history.store import history as gemini_history

LABEL_FIELDS = ("fundamental_strength", "valuation_view", "sentiment")


def _gemini_row(ticker: str, period: str, analysis_id: int | None) -> dict | None:
    """คู่เทียบฝั่ง Gemini: ใช้แถวที่ผูกไว้ตอน export ก่อน (ข้อมูลชุดเดียวกัน) — ไม่มีค่อยถอยไป
    หาแถวล่าสุดในงวดเดียวกัน (ยังเทียบได้ แต่คนละ snapshot จึงทำ flag บอกไว้)."""
    if analysis_id:
        row = get_analysis(analysis_id)
        if row:
            return row
    for row in gemini_history(ticker, limit=200):
        if row["run_at"][:7] == period:
            return row
    return None


def _gap_days(pack_created_at: str | None, gemini_run_at: str | None) -> int | None:
    """ห่างกันกี่วันระหว่าง 'ข้อมูลที่ฝั่งแชทได้อ่าน' กับ 'รอบที่ฝั่งรายวันอ่าน' — None ถ้าไม่รู้."""
    if not pack_created_at or not gemini_run_at:
        return None
    try:
        delta = datetime.fromisoformat(pack_created_at) - datetime.fromisoformat(gemini_run_at)
    except ValueError:
        return None
    return abs(delta.days)


def _same_framework(claude_version: str | None, gemini_version: str | None) -> bool | None:
    """True/False = ยืนยันได้ว่ากรอบเดียวกัน/คนละกรอบ; None = ไม่รู้ (แถวใดแถวหนึ่งเก่าเกินกว่า
    จะมีการบันทึกเวอร์ชันไว้) — 'ไม่รู้' ต้องไม่ถูกแสดงเป็น 'เหมือนกัน'."""
    if not claude_version or not gemini_version:
        return None
    return claude_version == gemini_version


def _gemini_grounding(row: dict | None) -> dict | None:
    """แถว analyses เก็บ grounding ไว้แค่ 'ratio' (คนละดีไซน์กับตาราง claude_analyses ที่เก็บทั้ง
    ก้อน) — 'จำนวนตัวเลขที่ยกมาอ้าง' จึงไม่มีในคอลัมน์ไหนเลย. คำนวณสดจาก summary+facts ที่เก็บไว้
    ในแถวนั้นด้วย eval ตัวเดียวกัน (deterministic, ไม่เรียก LLM) แทนการปล่อยว่างหรือเดา —
    ไม่งั้นช่อง 'ความละเอียด' ของฝั่ง Gemini จะเป็น N/A ตลอด แล้วเทียบไม่ได้จริง."""
    if not row or not row.get("facts"):
        return None
    try:
        summary = Summary.model_validate(row["summary"])
        facts = [Fact(**f) for f in row["facts"]]
    except Exception:
        return None      # แถวเก่าที่ schema ไม่ตรงแล้ว — ข้ามการนับ ไม่ใช่ล้มทั้งการเทียบ
    return {"facts": check_facts_grounding(summary, facts)}


def _detail(summary: dict, grounding: dict | None) -> dict:
    """ตัวชี้วัด 'ความละเอียด' ที่นับได้จากคำตอบตรงๆ (ไม่ใช่ความเห็น)."""
    facts_grounding = (grounding or {}).get("facts") or {}
    return {
        "strength_reasons": len(summary.get("strength_reasons") or []),
        "weak_points": len(summary.get("weak_points") or []),
        "what_to_watch": len(summary.get("what_to_watch") or []),
        "thesis_relevant_news": len(summary.get("thesis_relevant_news") or []),
        "cited_numbers": facts_grounding.get("cited_count"),
        "beginner_summary_chars": len(summary.get("beginner_summary") or ""),
        "thesis_assessment_chars": len(summary.get("thesis_assessment") or ""),
    }


def _side(row: dict | None, grounding: dict | None) -> dict | None:
    """ส่งเหตุผลตัวเต็มของทั้งสองฝั่งไปด้วย ไม่ใช่แค่ป้าย — เพราะคำถามที่ควรถามตอนสองสำนักไม่ตรงกัน
    คือ 'อีกฝั่งเห็นอะไรที่เราไม่เห็น' ซึ่งอ่านจากป้าย strong/cheap อย่างเดียวไม่มีทางตอบได้.
    ข้อมูลไม่ใหญ่ (ไม่กี่ตัวต่อเดือน) จึงไม่ต้องมี endpoint แยกให้กดดูรายตัว."""
    if row is None:
        return None
    summary = row.get("summary") or {}
    # คอลัมน์ facts_grounded_ratio ถูกเขียนไว้ 'ตอนรันวันนั้น' = ผูกกับ eval เวอร์ชันตอนนั้น.
    # ถ้ามีการคำนวณสดให้ (ฝั่ง Gemini คำนวณใหม่ทุกครั้งใน _gemini_grounding) ต้องใช้ตัวสด —
    # ไม่งั้นหลังแก้ eval (2026-08: หน่วยไทย/วันที่) จะกลายเป็นเทียบ 'v2 กับ v1' คนละเครื่องวัด
    # ซึ่งเป็นความผิดพลาดแบบเดียวกับที่ health.comparable_score กันไว้เรื่องคะแนน /8 กับ /11
    live_ratio = ((grounding or {}).get("facts") or {}).get("facts_grounded_ratio")
    return {
        "fundamental_strength": row.get("fundamental_strength"),
        "valuation_view": row.get("valuation_view"),
        "sentiment": row.get("sentiment"),
        "confidence": row.get("confidence"),
        "price": row.get("price"),
        "price_ok": row.get("price_ok"),
        "news_grounded_ratio": row.get("news_grounded_ratio"),
        "facts_grounded_ratio": live_ratio if live_ratio is not None else row.get("facts_grounded_ratio"),
        "detail": _detail(summary, grounding),
        "beginner_summary": summary.get("beginner_summary", ""),
        "strength_reasons": summary.get("strength_reasons") or [],
        "weak_points": summary.get("weak_points") or [],
        "what_to_watch": summary.get("what_to_watch") or [],
        "thesis_assessment": summary.get("thesis_assessment", ""),
        "run_at": row.get("run_at"),
    }


def _avg(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return mean(nums) if nums else None


def compare_period(period: str, model: str | None = None) -> dict:
    """ผลเทียบทั้งงวด — ticker ที่ยังไม่มีคำตอบจากแชทจะไม่อยู่ในนี้ (ไม่มีอะไรให้เทียบ)."""
    claude_rows = [r for r in claude_store.for_period(period)
                   if model is None or r["model"] == model]

    rows = []
    for c in claude_rows:
        g = _gemini_row(c["ticker"], period, c.get("analysis_id"))
        c_side = _side(c, c.get("grounding"))
        g_side = _side(g, _gemini_grounding(g))
        agree = {
            field: (None if g_side is None else c_side[field] == g_side[field])
            for field in LABEL_FIELDS
        }
        rows.append({
            "ticker": c["ticker"],
            "model": c["model"],
            # linked = จับคู่กับแถวที่บันทึกไว้ตอน export (คู่ที่ใกล้ที่สุดที่มี) — ตั้งใจ **ไม่**
            # เรียกว่า 'ข้อมูลชุดเดียวกัน' เพราะไม่จริง: ฝั่งแชทได้ snapshot ที่ดึงสดตอน export
            # ส่วนฝั่งรายวันคือรอบของมันเอง ซึ่งเกิดคนละเวลา. ห่างกันกี่วันจึงต้องบอกออกไปตรงๆ
            # ให้คนอ่านชั่งเองว่าความเห็นที่ต่างกันมาจากการตีความ หรือมาจากราคา/งบคนละวัน
            "linked": bool(c.get("analysis_id")) and g is not None
                      and g["id"] == c.get("analysis_id"),
            "data_gap_days": _gap_days(c.get("pack_created_at"), g["run_at"] if g else None),
            # กรอบที่ใช้ตัดสินคนละเวอร์ชัน = คนละข้อสอบ ความต่างที่เห็นอ่านเป็น 'ใครเก่งกว่า'
            # ไม่ได้ (บทเรียนเดียวกับ basis_changes ของ Phase 32). None ทั้งคู่ = แถวเก่าก่อนมี
            # การบันทึกเวอร์ชัน -> ไม่ยืนยันว่าเหมือนกัน แต่ก็ไม่ตั้งธงเท็จ
            "same_framework": _same_framework(c.get("framework_version"),
                                              (g or {}).get("framework_version")),
            "claude": c_side,
            "gemini": g_side,
            "agree": agree,
        })

    paired = [r for r in rows if r["gemini"] is not None]
    totals = {
        "tickers": len(rows),
        "paired": len(paired),
        "agree_rate": {
            field: (_avg([r["agree"][field] for r in paired]) if paired else None)
            for field in LABEL_FIELDS
        },
        "facts_grounded_avg": {
            "claude": _avg([r["claude"]["facts_grounded_ratio"] for r in rows]),
            "gemini": _avg([r["gemini"]["facts_grounded_ratio"] for r in paired]),
        },
        "news_grounded_avg": {
            "claude": _avg([r["claude"]["news_grounded_ratio"] for r in rows]),
            "gemini": _avg([r["gemini"]["news_grounded_ratio"] for r in paired]),
        },
        "detail_avg": {
            side: {
                key: _avg([r[side]["detail"][key] for r in (rows if side == "claude" else paired)])
                for key in ("strength_reasons", "weak_points", "what_to_watch",
                            "cited_numbers", "beginner_summary_chars")
            }
            for side in ("claude", "gemini")
        },
    }

    disagreements = [
        {"ticker": r["ticker"],
         "field": field,
         "claude": r["claude"][field],
         "gemini": r["gemini"][field]}
        for r in paired for field in LABEL_FIELDS if r["agree"][field] is False
    ]

    # เวลาของงวด: งานนี้ทำนานๆ ครั้ง (เดือนละหน) หน้าเว็บจึงต้องบอกได้ว่า 'ที่เห็นอยู่นี่ของเมื่อไหร่'
    # ไม่งั้นคนเปิดมากลางเดือนจะเข้าใจว่าตัวเลขเป็นของวันนี้ — ผิดคนละเรื่องกับหน้าอื่นที่รันทุกวัน
    return {
        "period": period,
        "model": model,
        "models": sorted({r["model"] for r in claude_rows}),
        "snapshot_at": min((r["pack_created_at"] for r in claude_rows
                            if r.get("pack_created_at")), default=None),
        "imported_at": max((r["run_at"] for r in claude_rows), default=None),
        "rows": rows,
        "totals": totals,
        "disagreements": disagreements,
    }


def render_text(result: dict) -> str:
    """ตารางสำหรับอ่านใน terminal (CLI ใช้) — สั้นๆ พอเห็นว่า 'ต่างตรงไหน' แล้วไปอ่านตัวเต็มเอง."""
    lines = [f"เทียบผลงวด {result['period']}"
             + (f" (model={result['model']})" if result["model"] else ""), ""]
    header = f"{'ticker':7} | {'strength (C/G)':24} | {'valuation (C/G)':24} | {'facts grounded':18}"
    lines += [header, "-" * len(header)]
    for r in result["rows"]:
        g = r["gemini"] or {}
        def pair(field):
            return f"{r['claude'][field] or '-'} / {g.get(field) or '-'}"
        def ratio(side_key, side):
            v = side.get(side_key) if side else None
            return f"{v:.0%}" if isinstance(v, (int, float)) else "N/A"
        lines.append(
            f"{r['ticker']:7} | {pair('fundamental_strength'):24} | "
            f"{pair('valuation_view'):24} | "
            f"{ratio('facts_grounded_ratio', r['claude'])} / {ratio('facts_grounded_ratio', g):>6}"
            + ("   (ไม่มีคู่เทียบ)" if not g
               else f"   (ข้อมูลห่าง {r['data_gap_days']} วัน)" if r["data_gap_days"] else "")
            + ("   ⚠ คนละ framework" if r["same_framework"] is False else "")
        )

    t = result["totals"]
    def pct(v):
        return f"{v:.0%}" if isinstance(v, (int, float)) else "N/A"
    def num(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"

    lines += ["", f"เทียบได้ {t['paired']}/{t['tickers']} ตัว", "",
              "ตรงกันกี่ %:  "
              + "  ".join(f"{f}={pct(t['agree_rate'][f])}" for f in LABEL_FIELDS),
              f"อ้างเลขตรง Fact:  Claude={pct(t['facts_grounded_avg']['claude'])}  "
              f"Gemini={pct(t['facts_grounded_avg']['gemini'])}",
              "ความละเอียดเฉลี่ย (จุดแข็ง/จุดอ่อน/สิ่งที่ต้องจับตา/เลขที่อ้าง/ตัวอักษรสรุป):"]
    for side in ("claude", "gemini"):
        d = t["detail_avg"][side]
        lines.append(f"  {side:7} {num(d['strength_reasons'])} / {num(d['weak_points'])} / "
                     f"{num(d['what_to_watch'])} / {num(d['cited_numbers'])} / "
                     f"{num(d['beginner_summary_chars'])}")

    if result["disagreements"]:
        lines += ["", "จุดที่เห็นไม่ตรงกัน (ไปอ่านเหตุผลของทั้งคู่):"]
        lines += [f"  {d['ticker']:6} {d['field']:22} Claude={d['claude']}  Gemini={d['gemini']}"
                  for d in result["disagreements"]]
    return "\n".join(lines)
