"""Phase 52 — สะพานเชื่อมตอนที่ LLM กับเครื่องยนต์ตอบไม่ตรงกัน.

Phase 51 ทำให้ "ขัดกัน" มองเห็นได้ แต่หยุดแค่นั้น — และป้ายที่บอกว่าขัดกันโดยไม่บอกว่าอะไร
จะชี้ขาด จะกลายเป็นวอลเปเปอร์ภายในสองสัปดาห์ ไฟล์นี้ตอบคำถามถัดไป: **มันแยกกันที่ตัวเลขไหน**

**หลักที่ใช้ (วิธีที่คนทำงานการเงินใช้จริง): ไม่เลือกข้าง แต่สร้างสะพาน**
สองฝั่งมักไม่ได้วัดของสิ่งเดียวกัน หน้าที่คือหาว่าอินพุตตัวไหนทำให้ต่าง แล้วถามว่าอินพุต
ตัวนั้นน่าเชื่อไหม — การเฉลี่ยสองคำตอบเข้าด้วยกันคือการทิ้งข้อมูลที่มีค่าที่สุด

**เคสที่ทำให้เกิดไฟล์นี้ (DUOL 2026-09-24):**
  Operating Income 136M · EBITDA 150M · Pretax 182M · ภาษี **−232M (ได้คืน ไม่ใช่จ่าย)**
  -> Net Income 414M ซึ่ง **สูงกว่า EBITDA 176%** เพราะกลับรายการสำรองภาษีรอตัดบัญชี
  -> P/E 17.8 ที่ดูถูกมาก มี 56% ของตัวหารเป็นเครดิตภาษีก้อนเดียวที่ไม่เกิดซ้ำ
  ฝั่งเงินสด: FCF 360M แต่มี SBC 137M + เงินทุนหมุนเวียน 49M อยู่ข้างใน -> เหลือจริง ~174M
  EV/FCF จึงวิ่งจาก 16.8x (ถูก) ไป 34.8x (แพง) แล้วแต่ว่านิยาม FCF ว่าอะไร

  เครื่องยนต์ยืนที่ 16.8x จึงให้ 3.0/3 · LLM ยืนที่ EV/EBITDA 31.3x จึงว่าแพง
  **ไม่มีใครผิด — ทั้งคู่พูดถูกคนละตัวเลข** และคำตอบที่แท้จริงคือ
  "ถูกจริงถ้าวัดด้วยเงินสด แต่เงินสดก้อนนั้นพึ่งการเติบโตที่ต้องไปต่อ"
"""

_TRUST_FLAGS = ("NEGATIVE_REINVESTMENT", "SUSTAINABLE_DIVERGES", "NOPAT_UNSTABLE",
                "SUSTAINABLE_UNCOMPUTABLE")


def _num(facts: dict, label: str):
    v = facts.get(label)
    return v if isinstance(v, (int, float)) else None


def _facts_map(facts) -> dict:
    """list[Fact|dict] -> {label: value} เฉพาะค่าที่เป็นตัวเลขเดี่ยว (ข้าม series)."""
    out = {}
    for f in facts or []:
        label = f.get("label") if isinstance(f, dict) else getattr(f, "label", None)
        value = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
        if label and isinstance(value, (int, float)):
            out.setdefault(label, value)
    return out


def implied_ebitda(facts: dict, ev: float | None) -> float | None:
    """EBITDA ย้อนกลับจาก EV ÷ (EV/EBITDA) — **ค่าอนุมาน ไม่ใช่ตัวเลขที่บริษัทรายงาน**

    ทำแบบนี้เพราะทั้งสองตัวถูกเก็บไว้แล้ว จึงคำนวณย้อนหลังกับประวัติทั้งหมดได้ทันที
    โดยไม่ต้องรอรอบดึงข้อมูลใหม่ (ต่างจาก SBC ที่เพิ่งเริ่มเก็บ จึงมีเฉพาะรอบใหม่)"""
    ratio = _num(facts, "EV/EBITDA")
    if not ev or not ratio or ratio <= 0:
        return None
    return ev / ratio


def build_bridge(facts, valuation: dict | None) -> dict | None:
    """บันไดคัดกรอง 4 ขั้น + ตาราง 'แพงหรือถูกแล้วแต่นิยาม FCF'.

    คืน None ถ้าไม่มีอะไรให้กระทบยอด (ไม่มี valuation หรือไม่มี facts) — ไม่คืนกล่องว่าง
    ที่อ่านแล้วเหมือนตรวจแล้วไม่เจออะไร
    """
    if not valuation or not facts:
        return None
    fm = _facts_map(facts)
    ev = valuation.get("ev")
    ebitda = implied_ebitda(fm, ev)
    ni = _num(fm, "Net Income")
    cfo = _num(fm, "CFO")
    capex = _num(fm, "Capex")
    sbc = _num(fm, "Stock Based Comp")
    nwc = _num(fm, "NWC Change")
    pe = _num(fm, "P/E")
    ev_ebitda = _num(fm, "EV/EBITDA")
    fcf = (cfo + capex) if (cfo is not None and capex is not None) else None

    steps, missing = [], []

    # ── ขั้น 1: multiples เห็นตรงกันเองไหม ────────────────────────────────
    # ถ้าตัวคูณสองตัวที่วัดของเดียวกันให้คำตอบคนละทาง แปลว่า **ตัวหารตัวใดตัวหนึ่งมีปัญหา**
    # ไม่ใช่ว่าหุ้นทั้งถูกทั้งแพงพร้อมกัน
    if pe is not None and ev_ebitda is not None:
        pe_cheap, ebitda_rich = pe < 25, ev_ebitda > 25
        conflict = pe_cheap and ebitda_rich
        steps.append({
            "key": "multiples_agree",
            "question": "ตัวคูณต่างๆ เห็นตรงกันเองไหม",
            "flagged": conflict,
            "detail": f"P/E {pe:.1f} · EV/EBITDA {ev_ebitda:.1f}",
            "means": ("ตัวคูณสองตัวชี้คนละทาง — ตัวเลขกำไรน่าสงสัย ต้องไปดูว่ากำไรมาจากไหน"
                      if conflict else "ตัวคูณไปทางเดียวกัน ไม่มีอะไรขัดกันเอง"),
        })
    else:
        missing.append("P/E หรือ EV/EBITDA")

    # ── ขั้น 2: กำไรสุทธิสูงกว่า EBITDA ไหม ──────────────────────────────
    # เป็นไปไม่ได้จากการดำเนินงาน — ถ้าเกิดขึ้น แปลว่ามีรายการใต้เส้น (ภาษี/รายการพิเศษ)
    # และทุกอย่างที่คำนวณจากกำไรสุทธิ (P/E, ROE) ใช้อ่านความถูกแพงไม่ได้
    if ni is not None and ebitda:
        over = ni > ebitda
        steps.append({
            "key": "ni_above_ebitda",
            "question": "กำไรสุทธิสูงกว่า EBITDA ไหม",
            "flagged": over,
            "detail": f"Net Income {ni/1e6:,.0f}M · EBITDA (อนุมาน) {ebitda/1e6:,.0f}M"
                      + (f" = สูงกว่า {(ni/ebitda-1)*100:.0f}%" if over else ""),
            "means": ("มีรายการใต้เส้นดันกำไรขึ้น (ภาษี/รายการพิเศษ) — P/E ใช้อ่านความถูกไม่ได้"
                      if over else "กำไรสุทธิต่ำกว่า EBITDA ตามปกติ ไม่มีรายการพิเศษดันไว้"),
        })
    else:
        missing.append("Net Income หรือ EBITDA")

    # ── ขั้น 3: FCF สูงกว่า EBITDA ไหม ───────────────────────────────────
    # ปกติ FCF ต้องต่ำกว่า EBITDA (หลังภาษี ดอกเบี้ย capex) — ถ้าสูงกว่า แปลว่าเงินสดส่วนเกิน
    # มาจาก SBC ที่บวกกลับ หรือเงินรับล่วงหน้า ซึ่ง **ทั้งสองอย่างพึ่งการเติบโตที่ต้องไปต่อ**
    if fcf is not None and ebitda:
        over = fcf > ebitda
        why = []
        if sbc:
            why.append(f"SBC {abs(sbc)/1e6:,.0f}M")
        if nwc and nwc > 0:
            why.append(f"เงินทุนหมุนเวียน +{nwc/1e6:,.0f}M")
        steps.append({
            "key": "fcf_above_ebitda",
            "question": "FCF สูงกว่า EBITDA ไหม",
            "flagged": over,
            "detail": f"FCF {fcf/1e6:,.0f}M · EBITDA {ebitda/1e6:,.0f}M"
                      + (f" — ส่วนเกินมาจาก {', '.join(why)}" if over and why else ""),
            "means": ("เงินสดส่วนหนึ่งไม่ได้มาจากการดำเนินงานล้วน — ความถูกนี้พึ่งการเติบโตที่ต้องไปต่อ"
                      if over else "FCF ต่ำกว่า EBITDA ตามปกติ"),
        })
    else:
        missing.append("FCF หรือ EBITDA")

    # ── ขั้น 4: เครื่องยนต์เชื่อ anchor ของตัวเองไหม ──────────────────────
    # ข้อนี้ไม่ต้องเดาเลย ระบบเขียนไว้เองอยู่แล้วทุกรอบ แค่ไม่เคยถูกเอามาวางตรงนี้
    flags = [f for f in (valuation.get("flags") or []) if f in _TRUST_FLAGS]
    steps.append({
        "key": "engine_self_doubt",
        "question": "เครื่องยนต์เชื่อ anchor ของตัวเองไหม",
        "flagged": bool(flags),
        "detail": (", ".join(flags) if flags else "ไม่มีธงเตือน"),
        "means": ("ระบบติดธงไว้เองว่าไม่ไว้ใจวิธีประมาณการเติบโตของตัวเองกับตัวนี้ — "
                  "คะแนนที่ได้จึงไม่ควรถูกพิงหนัก" if flags
                  else "ไม่มีธง — คะแนนของเครื่องยนต์ยืนบน anchor ที่มันเชื่อ"),
    })

    # ── ตาราง: แพงหรือถูก แล้วแต่ว่านิยาม FCF ว่าอะไร ────────────────────
    ladder = []
    if ev and fcf:
        def add(label, cash, note):
            if cash and cash > 0:
                ladder.append({"label": label, "multiple": round(ev / cash, 1),
                               "cash_m": round(cash / 1e6), "note": note})
        add("EV / FCF ที่รายงาน", fcf, "ตัวที่เครื่องยนต์ยืนอยู่")
        if sbc:
            add("EV / FCF หัก SBC", fcf - abs(sbc),
                "หักค่าตอบแทนเป็นหุ้น — ต้นทุนจริงที่จ่ายด้วยการเจือจาง")
            if nwc and nwc > 0:
                add("EV / FCF หัก SBC หักเงินทุนหมุนเวียน", fcf - abs(sbc) - nwc,
                    "หักเงินรับล่วงหน้าที่จะหายไปถ้าการเติบโตชะลอ")
        if ebitda:
            ladder.append({"label": "EV / EBITDA", "multiple": round(ev / ebitda, 1),
                           "cash_m": round(ebitda / 1e6), "note": "ตัวที่ LLM มักยืนอยู่"})
    if sbc is None:
        missing.append("Stock Based Comp (เริ่มเก็บ Phase 52 — แถวก่อนหน้านั้นไม่มี)")

    hits = [s for s in steps if s["flagged"]]
    # ขั้น 1-3 พูดถึง **ตัวเลขในงบ** ส่วนขั้น 4 เป็นบริบทของโมเดลเรา — วัดจากข้อมูลจริงพบว่า
    # ธง guard ติดกับ 7 ใน 16 ตัว ถ้านับข้อ 4 เป็นเหตุผลที่จะโชว์สะพาน มันจะขึ้นเกือบทุกตัว
    # แล้วกลายเป็นวอลเปเปอร์ ซึ่งคือปัญหาเดียวกับที่สะพานนี้ถูกสร้างมาแก้
    accounting = [s for s in steps if s["flagged"] and s["key"] != "engine_self_doubt"]

    if len(accounting) >= 2:
        conclusion = ("ทั้งสองฝั่งถูก แต่ถูกคนละตัวเลข — ถูกจริงถ้าวัดด้วยเงินสดที่รายงาน "
                      "แต่เงินสดก้อนนั้นพึ่งการเติบโตที่ต้องไปต่อ และความถูกฝั่งกำไรเป็นภาพลวงทางบัญชี")
    elif accounting:
        conclusion = ("เจอจุดที่สองฝั่งแยกกัน: " + " · ".join(s["question"] for s in accounting)
                      + " — อ่านคะแนนโดยรู้ข้อนี้ไว้")
    elif hits:
        conclusion = ("ตัวเลขในงบไม่มีอะไรขัดกันเอง — ที่ต่างกันมาจากการตีความ "
                      "แต่ระบบติดธงไม่ไว้ใจ anchor ของตัวเองไว้ จึงอย่าพิงคะแนนหนักเกินไป")
    else:
        conclusion = "ไม่พบจุดที่สองฝั่งควรแยกกัน — ความต่างน่าจะมาจากการตีความ ไม่ใช่ตัวเลข"

    return {"steps": steps, "hits": len(hits), "accounting_hits": len(accounting),
            "ladder": ladder, "conclusion": conclusion, "missing": missing,
            "ebitda_is_derived": ebitda is not None}
