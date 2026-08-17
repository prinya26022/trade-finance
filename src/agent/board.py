"""กระดานสรุปหน้าแรก (Phase 43) — "ตัวไหนน่าสนใจ ดูเร็วๆ แล้วค่อยเจาะ".

ทุกอย่างแปลงเป็นหน่วยเดียวที่รู้สึกได้: **ถ้าราคาวันนี้ = 100 เราคำนวณได้เท่าไร**
เหตุผลที่ต้องแปลง (เจ้าของบอกตรงๆ 2026-08-17 หลังอ่านรายงานฉบับแรก): "ส่วนลด −27%" กับ
"ช่วง 47pp" เป็นหน่วยของเครื่องมือ ไม่ใช่หน่วยที่คนใช้ตัดสินใจ — ส่วน "ราคา 100 คำนวณได้ 73"
กับ "ช่วง 26 ถึง 73" อ่านแล้วเห็นภาพทันทีโดยไม่ต้องรู้ว่า reverse-DCF คืออะไร

**เกณฑ์ตัดสินที่คนอ่านใช้เองได้: ช่วงนั้นคร่อม 100 หรือเปล่า** — คร่อมเมื่อไหร่แปลว่าบางวิธี
วัดบอกถูก บางวิธีบอกแพง = ตัวเลขนี้ตัดสินใจแทนไม่ได้ ต้องไปหาคำตอบเรื่องการเติบโตเอง
ดีกว่าป้าย narrow/mixed/wide ของ Phase 41 ตรงที่ไม่ต้องจำ threshold ของเราเลย

**ที่มาของตัวเลขสองคอลัมน์มาจากคนละที่ โดยตั้งใจ:**
- *คะแนน* อ่านจากแถวที่บันทึกไว้ตรงๆ (`health_score`/`health`) — ต้องเป็นเลขตัวเดียวกับที่
  dashboard/ticker/screener โชว์อยู่แล้วเป๊ะ ถ้าคำนวณใหม่ตรงนี้ หน้าแรกจะเถียงกับตัวเองทันที
  สำหรับแถวที่บันทึกก่อนเอนจิ้นรุ่นปัจจุบัน (ดู engine_version, Phase 37)
- *ราคาที่คำนวณได้ + ช่วง* คำนวณสดจาก `facts` ของแถวนั้น เพราะแถวเก่าไม่มีฟิลด์นี้เลย
  (`fair` มาตอน Phase 40, `agreement` ตอน Phase 41) — คำนวณสดจึงเป็นการ *เพิ่ม* ข้อมูล
  ไม่ใช่การขัดกับของเดิม. ไม่มี network: facts ที่เก็บไว้พอครบสำหรับ reverse-DCF ทั้งชุด
"""
from src.agent.health import (
    PARTIAL_MAX, _bank_valuation_score, _build_duck_fundamentals, _is_bank, _normalize_facts,
    no_valuation_reason,
)
from src.agent.valuation import FALLBACK_RISK_FREE_PCT, reverse_dcf
from src.history.store import latest_per_ticker

# ทุกวิธีวัดให้คำตอบเท่ากันเป๊ะภายในระยะนี้ = ไม่มีอะไรให้เทียบจริง (เพดาน growth กลืนไปหมด)
_IDENTICAL_PP = 0.5


def _at_100(discount_pct: float | None) -> int | None:
    """ส่วนลด % -> 'ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร' (ปัดเป็นจำนวนเต็ม — ทศนิยมของตัวเลข
    ที่แขวนอยู่บนประมาณการการเติบโตคือความแม่นยำปลอม)."""
    return None if discount_pct is None else round(100 * (1 + discount_pct / 100))


def _verdict(agreement: dict | None, at_100: int | None) -> tuple[str, str]:
    """(รหัส, คำอธิบายภาษาคน) — พูดถึง **ตัวเลขว่าใช้ได้ไหม** ไม่ใช่พูดถึงหุ้นว่าน่าซื้อไหม
    ซึ่งเป็นเส้นที่โปรเจกต์นี้ไม่ข้ามมาตั้งแต่ต้น."""
    if at_100 is None:
        return "none", "ยังคำนวณราคาไม่ได้"
    if agreement is None:
        return "single", "มีวิธีวัดเดียว ไม่มีอะไรมาตรวจสอบ"

    # anchor ที่ guard ตัดทิ้งไม่ควรถ่วงคำตัดสิน — มันถูกตัดเพราะรู้ว่าใช้กับธุรกิจแบบนั้นไม่ได้
    # (เช่น สูตร reinvestment กับบริษัทที่ลูกค้าจ่ายล่วงหน้า) ไม่ใช่เพราะเราไม่ชอบคำตอบ
    ok = [c["discount_pct"] for c in agreement["candidates"]
          if not c["rejected"] and c["discount_pct"] is not None]
    if not ok:
        return "single", "ไม่เหลือวิธีวัดที่ใช้ได้"
    lo, hi = min(ok), max(ok)

    if agreement.get("narrow_by_cap") or (hi - lo < _IDENTICAL_PP and len(ok) > 1):
        return "capped", "ทุกวิธีชนเพดานของระบบเท่ากันหมด — แน่นเทียม"
    if lo > 0:
        return "cheap", "ทุกวิธีบอกว่าราคาต่ำกว่าที่คำนวณได้"
    if hi < 0:
        return "expensive", "ทุกวิธีบอกว่าราคาสูงกว่าที่คำนวณได้"
    return "straddles", "บางวิธีบอกถูก บางวิธีบอกแพง — ตัดสินใจแทนไม่ได้"


def _accepted_range(agreement: dict | None) -> tuple[int | None, int | None]:
    if agreement is None:
        return None, None
    ok = [c["discount_pct"] for c in agreement["candidates"]
          if not c["rejected"] and c["discount_pct"] is not None]
    return (_at_100(min(ok)), _at_100(max(ok))) if ok else (None, None)


def build_row(row: dict, risk_free_pct: float = FALLBACK_RISK_FREE_PCT) -> dict:
    """แถวเดียวของกระดาน จากแถว analyses หนึ่งแถว (ไม่แตะ network)."""
    health = row.get("health") or {}
    facts = _normalize_facts(row.get("facts") or [])
    out = {
        "ticker": row["ticker"],
        "run_at": row.get("run_at"),
        "score": health.get("score"),
        "max": health.get("max"),
        "tier": health.get("tier"),
        "partial": bool(health.get("partial")),
        "at_100": None, "lo_100": None, "hi_100": None,
        "lens": None, "verdict": "none", "note": "ยังคำนวณราคาไม่ได้",
        "candidates": [],
    }
    if not facts:
        out["note"] = "แถวนี้ไม่มีข้อมูลงบเก็บไว้"
        return out

    if _is_bank(facts):
        bank = _bank_valuation_score(facts, risk_free_pct)
        fair = bank.get("fair") or {}
        out.update(lens="bank_pb", at_100=_at_100(fair.get("discount_pct")),
                   verdict="bank", note="ธนาคารใช้คนละไม้บรรทัด เทียบกับตัวอื่นตรงๆ ไม่ได้")
        return out

    duck = _build_duck_fundamentals(facts)
    dcf = reverse_dcf(duck, risk_free_pct=risk_free_pct)
    if dcf is None or dcf.get("fair") is None:
        reason, _ = no_valuation_reason(duck, dcf)
        out["note"] = reason
        return out

    agreement = dcf.get("agreement")
    at_100 = _at_100(dcf["fair"]["discount_pct"])
    lo, hi = _accepted_range(agreement)
    verdict, note = _verdict(agreement, at_100)
    out.update(
        lens=dcf.get("lens"), at_100=at_100, lo_100=lo, hi_100=hi,
        verdict=verdict, note=note,
        candidates=[
            {"label": c["label"], "growth": c["growth"], "at_100": _at_100(c["discount_pct"]),
             "used": c["used"], "rejected": c["rejected"], "capped": c["capped"]}
            for c in (agreement or {}).get("candidates", [])
        ],
    )
    return out


def build_board(rows: list[dict] | None = None,
                risk_free_pct: float = FALLBACK_RISK_FREE_PCT) -> list[dict]:
    """กระดานทั้งใบ เรียงตาม **คะแนนคุณภาพ ไม่ใช่ความถูก** — เรียงตามความถูกเมื่อไหร่
    ตารางนี้กลายเป็นรายการแนะนำซื้อทันที ซึ่งไม่ใช่สิ่งที่เครื่องมือนี้ทำ (หลักเดียวกับ
    screener ที่จงใจไม่เรียงตาม fair_discount_pct ตั้งแต่ Phase 40).

    `rows` ฉีดเข้ามาได้เพื่อให้เทสต์ไม่ต้องแตะ DB จริง (บทเรียนจาก Phase 38 ที่
    build_quality_report ไปอ่าน data/watchlist.db ระหว่างรันเทสต์)."""
    src = latest_per_ticker() if rows is None else rows
    board = [build_row(r, risk_free_pct) for r in src]
    # ตัวที่ไม่มีคะแนน (crypto/ข้อมูลไม่พอ) ไปท้ายสุด แต่ไม่หายไป — การซ่อนของที่ประเมินไม่ได้
    # คือสิ่งที่ Phase 29/34 แก้มาแล้วสองรอบ
    board.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["ticker"]))
    return board


def summary(board: list[dict]) -> dict:
    """ตัวเลขสรุปบนหัวกระดาน — 'มีกี่ตัวที่ตัวเลขราคาเชื่อได้จริง' คือคำถามที่ Phase 41 เปิด."""
    usable = [r for r in board if r["verdict"] in ("cheap", "expensive")]
    return {
        "total": len(board),
        "priced": len([r for r in board if r["at_100"] is not None]),
        "usable": len(usable),
        "cheap": len([r for r in board if r["verdict"] == "cheap"]),
        "unreliable": len([r for r in board if r["verdict"] in ("straddles", "capped", "single")]),
    }
