"""เช็คกับความเป็นจริง (Phase 44) — "ราคานี้เรียกร้องให้บริษัทใหญ่แค่ไหน".

reverse-DCF บอกว่า "ตลาด price NVDA ไว้ที่ FCF โต 33.8%/ปี" ซึ่งเป็นข้อความที่**เถียงไม่ได้**
เพราะไม่มีอะไรให้เทียบ — 33.8% เยอะไหม? เทียบกับอะไร? ตัวนี้เดินตัวเลขนั้นไปข้างหน้าจริงๆ แล้ว
ถามคำถามที่เถียงได้: **บริษัทต้องมีรายได้เท่าไรถึงจะทำ FCF ก้อนนั้นได้**

ต่างจาก Phase 40/43 ตรงที่สองเฟสนั้นแปลงหน่วยอยู่ในโลกของโมเดลเหมือนเดิม (gap -> %ราคา ->
"ถ้าราคา 100") ส่วนอันนี้เอาตัวเลขออกไป**ชนกับเพดานทางกายภาพ** — ขนาดตลาดรวม จำนวนลูกค้าที่มี
อยู่จริงบนโลก margin สูงสุดที่ธุรกิจแบบนั้นเคยทำได้. เป็น check ที่โมเดลทำเองไม่ได้ (เราไม่มี
ข้อมูล TAM และจะไม่แต่งขึ้นมา) แต่เจ้าของทำได้ในห้าวินาที = แบ่งงานกันถูกฝั่ง

**การแยกส่วนที่เป็นหัวใจจริงๆ ของเฟสนี้:** FCF growth เท่ากันเรียกร้องไม่เท่ากัน ขึ้นกับว่าเหลือ
ที่ให้ margin ขยายแค่ไหน — บริษัทที่ margin ถูกกดอยู่ (AMZN 0.4%, MSFT 5.0% จาก capex) โต FCF
ได้หลายเท่าโดย**ไม่ต้องโตรายได้เลย** แค่ margin กลับมาปกติ ส่วนบริษัทที่ margin ชนเพดานแล้ว
(MA 47.6%) ทุกเปอร์เซ็นต์ของ FCF ต้องมาจากรายได้ล้วนๆ. วัดจริงแล้วมันพลิกการอ่านบางตัว: AMZN
เป็นตัวที่กระดานบอกว่าแพงที่สุด (ราคา 100 -> คำนวณได้ 5) แต่ราคานั้นเรียกร้องให้รายได้โตแค่
3.5%/ปี เพราะ margin ทำงานแทนเกือบทั้งหมด — สองมุมนี้ตอบคนละคำถาม และการที่มันไม่ตรงกันคือข้อมูล

**ห้ามอ่านเป็นคำพยากรณ์:** ตัวเลข "ปีที่ 10" ผูกกับ horizon 10 ปีที่ล็อกไว้ในสเปก เปลี่ยนเป็น
15 ปีตัวเลขก็เปลี่ยน (implied growth จะถูก solve ใหม่ด้วย) สิ่งที่อ่านได้คือ**การเทียบข้ามตัว**
เพราะทุกตัวใช้หน้าต่างเดียวกัน — หลักเดียวกับที่ Phase 40 บอกว่าราคาที่คุ้มค่าไม่ได้ calibrate
ในเชิงระดับสัมบูรณ์
"""

# เพดาน FCF margin ที่บริษัทมหาชนทำได้จริงแบบยั่งยืน — ไม่ใช่ค่าที่คิดขึ้นเอง: MA ใน watchlist
# วันนี้อยู่ที่ 47.6% ซึ่งเป็นระดับสูงสุดของกลุ่มธุรกิจที่แทบไม่ต้องใช้สินทรัพย์เลย. ใช้เป็น
# **สมมติฐานที่ใจกว้างที่สุด** โดยตั้งใจ: ถ้าให้ margin ดีที่สุดเท่าที่เป็นไปได้แล้วยังต้องโต
# รายได้หลายเท่า ข้อเรียกร้องนั้นก็หนักจริง ไม่ใช่หนักเพราะเราตั้งสมมติฐานแคบ
FCF_MARGIN_CEILING_PCT = 50.0


def required_scale(fcf_base: float | None, growth_pct: float | None, years: int | None,
                   revenue: float | None, fcf_margin_pct: float | None) -> dict | None:
    """"ถ้า FCF ต้องโต growth_pct ต่อปีเป็นเวลา years ปี บริษัทต้องใหญ่แค่ไหน" (None ถ้าคำนวณไม่ได้).

    revenue กับ fcf_base ต้องเป็นสกุลเดียวกัน — ทั้งคู่มาจากงบ จึงใช่เสมอ (ตัวที่งบกับราคาคนละ
    สกุลถูกปฏิเสธตั้งแต่ reverse_dcf แล้ว ไม่มาถึงตรงนี้)
    """
    if None in (fcf_base, growth_pct, years, revenue) or fcf_base <= 0 or revenue <= 0:
        return None

    fcf_needed = fcf_base * (1 + growth_pct / 100.0) ** years

    # เพดานคือ "ดีที่สุดเท่าที่เป็นไปได้" — บริษัทที่ทำได้เกินค่าคงที่นี้อยู่แล้ว (MA) ใช้ของ
    # ตัวเองเป็นเพดาน ไม่งั้นจะกลายเป็นการบังคับให้มันแย่ลงกว่าความจริงเพื่อให้เข้าสูตรเรา
    margin_today = fcf_margin_pct if fcf_margin_pct is not None else None
    ceiling = max(FCF_MARGIN_CEILING_PCT, margin_today or 0.0)

    # FCF สูงสุดที่ทำได้ถ้ารายได้ไม่โตขึ้นเลย แต่ margin ขึ้นไปชนเพดาน
    fcf_from_margin_alone = revenue * ceiling / 100.0
    margin_alone_enough = fcf_needed <= fcf_from_margin_alone

    revenue_needed = fcf_needed / (ceiling / 100.0)
    revenue_multiple = revenue_needed / revenue
    # ถ้า margin อย่างเดียวพอแล้ว "อัตราการเติบโตของรายได้ที่ต้องการ" คือ 0 ไม่ใช่ตัวเลขติดลบ
    # (ติดลบจะอ่านว่า "ต้องหดตัว" ซึ่งไม่ใช่ข้อเรียกร้อง มันแค่แปลว่าไม่มีข้อเรียกร้อง)
    revenue_cagr_needed = (
        round((revenue_multiple ** (1 / years) - 1) * 100, 2) if revenue_multiple > 1 else 0.0
    )

    return {
        "years": years,
        "at_growth": round(growth_pct, 2),
        "fcf_now": round(fcf_base, 2),
        "fcf_needed": round(fcf_needed, 2),
        "fcf_multiple": round(fcf_needed / fcf_base, 2),
        "margin_today_pct": round(margin_today, 2) if margin_today is not None else None,
        "margin_ceiling_pct": round(ceiling, 2),
        "revenue_now": round(revenue, 2),
        "revenue_needed": round(revenue_needed, 2),
        "revenue_multiple": round(revenue_multiple, 2),
        "revenue_cagr_needed_pct": revenue_cagr_needed,
        # ธงที่สำคัญที่สุด: ราคานี้ไม่ได้เรียกร้องการเติบโตเลย แค่ margin กลับมาปกติก็พอ
        "margin_alone_enough": margin_alone_enough,
    }


def reality_check(dcf: dict, revenue: float | None, fcf_margin_pct: float | None) -> dict | None:
    """เทียบสองข้อเรียกร้องข้างกัน: ที่ **ตลาด** ขอ (implied) กับที่ **เรา** ขอ (realistic).

    ตัวเดียวกับ gap ที่โชว์อยู่แล้ว แต่ในหน่วยที่เอาไปชนกับความรู้เรื่องอุตสาหกรรมได้ —
    "ต่างกัน 17pp" เถียงไม่ได้ ส่วน "ตลาดขอให้รายได้โต 8.9 เท่า เราขอ 2.1 เท่า" เถียงได้ทันที
    """
    if not dcf:
        return None
    years = dcf.get("years")
    fcf_base = dcf.get("fcf_base")
    market = required_scale(fcf_base, dcf.get("implied_growth"), years, revenue, fcf_margin_pct)
    ours = required_scale(fcf_base, dcf.get("realistic_growth"), years, revenue, fcf_margin_pct)
    if market is None and ours is None:
        return None
    return {"market": market, "ours": ours}
