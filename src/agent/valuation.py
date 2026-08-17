"""Reverse-DCF (Phase 18, per scoring_spec.md, + valuation_guard_growth_lens.md): แทนที่จะ
พยากรณ์ growth แล้วคำนวณราคา (DCF ปกติ, พยากรณ์ผิดง่าย), เราแก้สมการย้อนกลับ — เอา 'ราคาตลาด
ปัจจุบัน' ตั้งเป็นโจทย์ แล้วหาว่า 'ตลาดกำลัง price การเติบโตของ FCF ไว้ที่กี่ % ต่อปี' (implied
growth) ถึงจะได้ราคานี้พอดี แล้วเทียบกับ 'realistic_growth' ห่างกันแค่ไหน

ค่าคงที่ต้องล็อกเหมือนกันทุกหุ้น (ตามกฎเหล็กของสเปก — ห้ามให้อะไรลอยตามใจนอกจาก FCF/β/ตัวที่
solve ไม่งั้น cheap พลิกเป็น expensive ได้ง่ายๆ และเทียบข้ามหุ้นไม่ได้เลย):
- Forecast horizon 10 ปี, Terminal growth 2.5%, ERP มาตรฐาน (ไม่ลอยตามหุ้น)
- WACC = CAPM (Rf + β×ERP) — Rf ล็อกเป็นค่าเดียว ณ วันรัน (ตลาดรวม ไม่ใช่ต่อหุ้น), β ตั้งเพดาน
  [0.7, 1.6] กัน beta เพี้ยนของหุ้นเล็กมาบิด WACC
- FCF base = ค่าเฉลี่ย FCF 3 ปีย้อนหลัง (กันปีที่ผิดปกติปีเดียวมาบิดผลทั้งโมเดล)
- EV target = Market Cap + Net Debt (bridge หนี้เข้าไปด้วยถึงจะเทียบข้ามหุ้นที่มี leverage
  ต่างกันได้ยุติธรรม)

realistic_growth: sustainable_growth (reinvestment_rate × ROIC) เป็น 'value lens' ค่าเริ่มต้น
— แต่สูตรนี้พังกับหุ้น asset-light + deferred-revenue (เช่น DUOL: ΔNWC ติดลบเพราะลูกค้าจ่าย
ล่วงหน้าทำให้ reinvestment_rate ติดลบทั้งที่บริษัทโตจริง 40%+) valuation_guard() ตรวจจับกรณีนี้
(NOPAT บางเฉียบ/reinvestment ติดลบ/sustainable ขัดแย้งกับ CAGR จริงมหาศาล) แล้ว route ไป
'growth lens' แทน — ใช้ growth ล่าสุดจริงที่ fade ลงหา terminal เป็น anchor แทนสูตรที่พัง พร้อม
Rule-of-40 modifier กันหุ้นที่ 'โตไม่จริง+เผาเงิน' ถูกตัดสินว่าถูกอย่างผิดๆ

Phase 19.4 (2026-07, audit): แก้ 2 บั๊ก/design gap ที่พบตอนตรวจ reverse-DCF ต่อจาก 19.3.1 —
(1) `_fcf_base_3yr` เดิม assume fcf_series เรียงใหม่->เก่าเสมอแล้วหยิบ [:3] ตรงๆ แต่พาธที่ใช้
คำนวณ valuation component ของ health score (health.py::_build_duck_fundamentals) ป้อนเรียง
เก่า->ใหม่ (ตรงข้าม) ทำให้หยิบ 3 ปีเก่าสุดแทนที่จะเป็นล่าสุด — ยืนยันจริงกับ NVDA: fcf_base ต่ำกว่า
ความจริงถึง 2 เท่า (30.6B vs 61.5B) เพราะเป็นบริษัทโตเร็ว 3 ปีเก่าสุดกับล่าสุดต่างกันมหาศาล ตอนนี้
sort เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา) เหมือน _rev_growth_recent. (2) growth lens เดิมเทียบ
implied_growth (FCF growth ที่ตลาด price ไว้) กับ realistic_growth ที่ anchor จาก REVENUE growth —
apples-to-oranges เวลา margin กำลังขยายตัว (FCF โตเร็วกว่า revenue เป็นปกติจาก operating leverage)
ตอนนี้ anchor จาก FCF CAGR ก่อนเสมอถ้าคำนวณได้ (unit เดียวกับ implied_growth ตรงๆ) fallback ไป
revenue growth เฉพาะตอน FCF history สั้นเกินไป/สลับเครื่องหมาย. Backfill dry-run บน watchlist จริง:
14/107 แถวคะแนนเปลี่ยน (NVDA/GOOGL/MSFT +1.0 แต้ม จากขา fcf_base — DUOL เจอบั๊กจริงเหมือนกันแต่
score ไม่ขยับเพราะ gap ติดลบมากอยู่แล้วทั้งก่อน/หลัง).
"""
from dataclasses import dataclass

from src.agent.grading import graded_below

DEFAULT_TERMINAL_GROWTH = 0.025  # โตตลอดไปเท่า GDP/เงินเฟ้อระยะยาวโดยประมาณ — ห้ามสูงกว่านี้
DEFAULT_YEARS = 10
DEFAULT_ERP = 0.0525              # equity risk premium มาตรฐาน (จุดกึ่งกลาง 5-5.5%) — ล็อกค่าเดียว
FALLBACK_RISK_FREE_PCT = 4.0      # ใช้ตอนดึง ^TNX ไม่ได้ (ดู src/providers/stock/market.py)

BETA_FLOOR = 0.7   # กัน beta ของหุ้นเล็ก/ข้อมูลเพี้ยนมาบิด WACC จนเทียบข้ามหุ้นไม่ได้
BETA_CAP = 1.6

SUSTAINABLE_GROWTH_CAP = 0.20     # value lens: ไม่มีบริษัทไหนโตสองหลักสูงได้ตลอด 10 ปี
CAP_INITIAL_GROWTH = 0.35         # growth lens: เพดาน growth ปีแรก (ไม่เชื่อว่ายั่งยืนเกินนี้)
MIN_NOPAT_MARGIN = 0.02           # NOPAT/Revenue ต่ำกว่านี้ = ฐานไม่นิ่ง ratio ระเบิด -> NOPAT_UNSTABLE
DIVERGENCE_TRIGGER_PP = 15.0      # |sustainable − historical CAGR| (pp) เกินนี้ = ไม่ไว้ใจ sustainable
RULE40_WEAK = 20.0                # (growth% + FCF margin%) ต่ำกว่านี้ = โตไม่จริง (growth lens เท่านั้น)

# ขอบเขตการเติบโตที่โมเดลนี้ยอมแก้สมการหา (-30% ถึง +60% ต่อปี) — นอกช่วงนี้ถือว่า
# 'ราคาสุดโต่งเกินกว่าจะตีความเป็นตัวเลข growth ที่มีความหมาย'
_GROWTH_LO = -0.30
_GROWTH_HI = 0.60
_TOLERANCE = 1e-6
_MAX_ITER = 200


def intrinsic_value(
    fcf_base: float, growth: float, discount_rate: float, terminal_growth: float, years: int
) -> float:
    """PV ของ FCF ที่โต `growth`/ปี เป็นเวลา `years` ปี + terminal value (Gordon growth)
    ที่ปีสุดท้าย คิดลดกลับมาปัจจุบัน. Monotonic เพิ่มขึ้นตาม growth (growth สูง = value สูง)
    — สมบัตินี้คือสิ่งที่ทำให้ bisection หา implied growth ด้านล่างใช้ได้. เทียบกับ EV (ไม่ใช่
    market cap ตรงๆ) จึง 'fcf_base'/'discount_rate' ต้องเป็น WACC-level ไม่ใช่ cost-of-equity."""
    pv = 0.0
    cash_flow = fcf_base
    for t in range(1, years + 1):
        cash_flow = cash_flow * (1 + growth)
        pv += cash_flow / (1 + discount_rate) ** t
    terminal_fcf = cash_flow * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv += terminal_value / (1 + discount_rate) ** years
    return pv


# ช่วง growth ที่โชว์ข้างราคาที่คุ้มค่า (pp บวก/ลบจาก realistic) — **ไม่ใช่ช่วงความเชื่อมั่นทาง
# สถิติ** เราไม่มีการแจกแจงของ growth และไม่ควรแกล้งว่ามี. มันคือเครื่องมือวัดความไว: ตัวเลข
# ราคาเดี่ยวๆ อ่านเหมือนความจริงที่คำนวณได้ ทั้งที่มันแขวนอยู่บนประมาณการตัวเดียวที่สามเฟสล่าสุด
# (35/36/38) พิสูจน์แล้วว่าเปราะ — anchor เปลี่ยนหน้าต่าง CVX ก็เด้ง -11% เป็น +3% ในวันเดียว
FAIR_BAND_PP = 3.0


def fair_market_cap(fcf_base: float | None, growth_pct: float | None, wacc_pct: float | None,
                    terminal_growth_pct: float | None, years: int | None,
                    net_debt: float) -> float | None:
    """market cap ที่ทำให้ implied growth เท่ากับ growth ที่ให้มาพอดี (None ถ้าคำนวณไม่ได้).

    นี่คือ reverse-DCF เดินย้อนทาง และมัน **ง่ายกว่าขาไป**: ขาไปต้องแก้สมการหา growth จาก EV
    (bisection) ส่วนขากลับแทนค่า growth ลงไปตรงๆ แล้วอ่าน EV ออกมา — ใช้ `intrinsic_value`
    ตัวเดียวกับที่ให้คะแนนจริง ไม่มีสูตรที่สอง

    รับหน่วยเป็น % ทั้งหมดเพราะ dict ที่เก็บใน analyses.valuation_json เก็บเป็น % —
    ให้คนเรียกส่งของที่มีอยู่ในมือได้เลย ไม่ต้องแปลงหน่วยเอง (ซึ่งเป็นจุดที่พลาดง่ายที่สุด)
    """
    if None in (fcf_base, growth_pct, wacc_pct, terminal_growth_pct, years) or fcf_base <= 0:
        return None
    wacc, g_term = wacc_pct / 100.0, terminal_growth_pct / 100.0
    if wacc <= g_term:
        return None                      # โมเดล Gordon ใช้ไม่ได้ (ตัวหารติดลบ/เป็นศูนย์)
    ev = intrinsic_value(fcf_base, growth_pct / 100.0, wacc, g_term, years)
    mcap = ev - net_debt
    # หนี้สุทธิกลืนมูลค่ากิจการทั้งก้อน = ส่วนของผู้ถือหุ้นไม่เหลืออะไรตามโมเดลนี้ ซึ่งเป็นข้อความที่
    # แรงเกินกว่าจะพูดจาก DCF ธรรมดา -> ไม่ตอบดีกว่าตอบเลขติดลบที่ดูเหมือนคำนวณมาอย่างดี
    return mcap if mcap > 0 else None


def fair_value(dcf: dict, market_cap: float | None, band_pp: float = FAIR_BAND_PP) -> dict | None:
    """ราคาที่ 'ตลาดคาดเท่ากับที่เราคาดพอดี' + ความไวของมัน (None ถ้าคำนวณไม่ได้).

    **มันไม่ใช่ราคาเป้าหมาย และไม่ใช่สัญญาณซื้อ** — โปรเจกต์นี้ไม่ฟันธงจังหวะโดยตั้งใจ. สิ่งที่
    ฟังก์ชันนี้ทำคือ *แปลงหน่วย* ของ gap ที่แสดงอยู่แล้ว: "gap +6.4pp" เป็นตัวเลขที่รู้สึกไม่ได้
    ส่วน "ตลาดขอราคาสูงกว่าที่ประมาณการของเรารองรับ 22.8%" คือเรื่องเดียวกันในหน่วยที่เจ้าของ
    ใช้ซื้อขายจริง. ข้อมูลเท่าเดิม อ่านออกคนละระดับ

    คืน `discount_pct` เป็นหลัก ไม่ใช่ราคาต่อหุ้น เพราะสัดส่วนนี้ไม่ต้องใช้จำนวนหุ้นเลย —
    บทเรียนสดๆ จาก Phase 39: `Diluted Shares` ของ MA (971M ถ่วงน้ำหนัก) ต่างจากหุ้นคงเหลือจริง
    (883.58M) อยู่ 9.9% การหารด้วยมันจะได้ราคาต่อหุ้นที่ผิดเงียบๆ. ฝั่งที่รู้ราคาวันนี้อยู่แล้ว
    คูณกลับเองได้เป๊ะ

    `band` = ราคาที่ growth ต่างจากประมาณการเรา ±band_pp — อยู่ที่นี่เพราะเลขเดี่ยวๆ ให้ความ
    แม่นยำปลอม. `pct_per_pp` สรุปความไวเป็นตัวเลขเดียว: "โตต่างไป 1pp ราคาขยับกี่ %"

    **ระดับสัมบูรณ์ของตัวเลขนี้ไม่ได้ถูก calibrate** — วัดจริงกับ 6 ตัวแล้วติดลบทั้งหมด (AAPL -67%
    ถึง JPM -10%) เพราะ anchor ฝั่งเราอนุรักษ์นิยมกว่าที่ตลาด price ไว้อย่างเป็นระบบ. สิ่งที่อ่านได้
    จริงคือ (1) การเทียบข้ามตัว และ (2) ความไว — AAPL -67% ที่ 2.5%/pp มั่นคงกว่า CVX -28% ที่
    6.2%/pp มาก ทั้งที่ตัวเลขหน้าบ้านชวนให้คิดตรงกันข้าม. อย่าอ่านว่า "ทุกตัวแพงเกินไป"
    """
    if not dcf or market_cap is None or market_cap <= 0:
        return None
    realistic = dcf.get("realistic_growth")
    ev = dcf.get("ev")
    if realistic is None or ev is None:
        return None

    net_debt = ev - market_cap
    args = (dcf.get("fcf_base"), dcf.get("wacc"), dcf.get("terminal_growth"), dcf.get("years"))
    base = fair_market_cap(args[0], realistic, *args[1:], net_debt)
    if base is None:
        return None

    def _row(growth: float) -> dict | None:
        mcap = fair_market_cap(args[0], growth, *args[1:], net_debt)
        if mcap is None:
            return None
        return {"growth": round(growth, 2), "discount_pct": round((mcap / market_cap - 1) * 100, 1)}

    band = [r for r in (_row(realistic - band_pp), _row(realistic), _row(realistic + band_pp)) if r]
    lo, hi = _row(realistic - band_pp), _row(realistic + band_pp)
    pct_per_pp = (round((hi["discount_pct"] - lo["discount_pct"]) / (2 * band_pp), 1)
                  if lo and hi else None)

    return {
        "market_cap": round(base, 2),
        "discount_pct": round((base / market_cap - 1) * 100, 1),   # ลบ = ราคาวันนี้แพงกว่า
        "at_growth": realistic,
        "band_pp": band_pp,
        "band": band,
        "pct_per_pp": pct_per_pp,
    }


# ── ความมั่นใจในราคาที่คุ้มค่า (Phase 41) ─────────────────────────────────────────
# วัดจริงกับ watchlist ทั้งชุด 2026-08-17 แล้วพบว่า `pct_per_pp` ที่ Phase 40 โชว์เป็น "ตัววัด
# ความเปราะ" นั้น **ซ้ำซ้อนกับตัวเลขที่อยู่ข้างๆ มันเอง**: ความยืดหยุ่นของ EV ต่อ growth 1pp
# แทบคงที่ทุกตัว (6.5-7.7% ของ EV) เพราะมันขึ้นกับ (wacc, g, horizon) ไม่ใช่ตัวบริษัท — ดังนั้น
#     pct_per_pp ≈ 7 × (ราคาที่คุ้มค่า ÷ ราคาตลาด)
# คลาดเคลื่อนเฉลี่ย 8.2% สูงสุด 21.2% จาก 12 ตัวที่คำนวณได้. แปลว่า "DUOL ไวกว่า AAPL 6 เท่า"
# เป็นความจริงเชิงกลไกล้วน (fair/price ของ DUOL สูงกว่า 6 เท่า) ไม่ได้แปลว่าธุรกิจ DUOL
# ประเมินยากกว่า — ซึ่งเป็นสิ่งที่คำว่า "ความไว" ชวนให้เข้าใจ
#
# ความเปราะจริงอยู่คนละที่: **ราคาที่คุ้มค่าแขวนอยู่บน "การเลือก anchor" ไม่ใช่บน ±1pp รอบ
# anchor ที่เลือกแล้ว.** เรามีวิธีวัดการเติบโตอยู่หลายทางที่มีเหตุผลพอกัน (โครงสร้าง:
# reinvestment × ROIC / ประวัติ: FCF CAGR สั้น-ยาว, รายได้) — ถ้าทุกทางตอบใกล้กัน คำตอบมั่นคง
# ถ้าตอบคนละเรื่อง คำตอบคือเหรียญที่โยนไปแล้วหนึ่งครั้ง. วัดจริง: MA ทุก anchor ตอบ 8.1-9.9%
# (ส่วนลดขยับแค่ 11pp) แต่ MSFT โครงสร้างบอก 17.2% ประวัติ FCF บอก 3.3-5.0% — ส่วนลดวิ่งจาก
# -27% ถึง -74%. ทั้งที่ pct_per_pp ของ MA (6.1) สูงกว่า MSFT (5.4) ด้วยซ้ำ
_SPREAD_NARROW_PP = 25.0   # ส่วนลดขยับน้อยกว่านี้เมื่อสลับ anchor = ทุกวิธีเห็นตรงกัน
_SPREAD_WIDE_PP = 60.0     # เกินนี้ = คำตอบขึ้นกับว่าเลือก anchor ไหน มากกว่าขึ้นกับตัวธุรกิจ

ANCHOR_LABELS = {
    "sustainable": "โครงสร้าง: reinvestment × ROIC",
    "fcf_long": "ประวัติ: FCF CAGR ยาว (งบที่ยื่นจริง)",
    "fcf": "ประวัติ: FCF CAGR (หน้าต่าง yfinance)",
    "revenue_recent": "ประวัติ: รายได้โตปีล่าสุด",
    "revenue_cagr": "ประวัติ: รายได้ CAGR",
}
# ครอบครัวของ anchor — สองครอบครัวนี้ตอบคนละคำถาม ("ธุรกิจลงทุนกลับเท่าไรแล้วได้ผลตอบแทน
# เท่าไร" vs "ที่ผ่านมามันโตเท่าไรจริง") การที่มันไม่ตรงกันจึงเป็นข้อมูล ไม่ใช่ error
ANCHOR_FAMILY = {"sustainable": "structure"}


def anchor_realistic(source: str, raw_pct: float, terminal_growth: float, years: int) -> float:
    """แปลง anchor ดิบเป็น realistic_growth ตามกติกาของครอบครัวตัวเอง — sustainable โดน cap
    ที่ SUSTAINABLE_GROWTH_CAP ส่วน anchor ฝั่งประวัติโดน fade ผ่าน growth_lens_realistic
    เหมือนที่ reverse_dcf ทำจริงถ้าเลือกตัวนั้น. ต้องผ่านกติกาเดียวกันถึงจะเทียบกันได้ —
    ไม่งั้นจะเทียบ 'ตัวที่ถูก fade แล้ว' กับ 'ตัวดิบ' ซึ่งคนละหน่วยความหมาย"""
    if source == "sustainable":
        return round(max(-100.0, min(SUSTAINABLE_GROWTH_CAP * 100, raw_pct)), 2)
    return growth_lens_realistic(raw_pct, terminal_growth, years)


def anchor_agreement(dcf: dict, market_cap: float | None, raw: dict[str, float | None],
                     used: str | None) -> dict | None:
    """"ถ้าเราเลือก anchor อีกตัวที่มีเหตุผลพอกัน ราคาที่คุ้มค่าจะเปลี่ยนไปแค่ไหน" — คืน None
    ถ้ามี anchor ที่คำนวณได้น้อยกว่าสองตัว (ไม่มีอะไรให้เทียบ = ไม่มีสิทธิ์พูดเรื่องความมั่นใจ).

    **มันไม่ใช่ช่วงความเชื่อมั่นทางสถิติ และไม่ใช่การบอกว่า anchor ที่เลือกผิด** — มันคือ
    "คำตอบนี้ขึ้นกับการเลือกของเรามากแค่ไหน". ช่วงแคบ = ทุกวิธีวัดการเติบโตเห็นตรงกัน คำตอบ
    ทนต่อการเปลี่ยนวิธี. ช่วงกว้าง = ยังไม่มีใครรู้ว่าบริษัทนี้โตเท่าไร รวมทั้งเราด้วย

    ค่าที่ได้เป็น **ขอบบน** ของความไม่แน่นอนโดยตั้งใจ: บาง anchor ในลิสต์คือตัวที่
    valuation_guard ปฏิเสธไปแล้วอย่างมีเหตุผล (DUOL: sustainable ติดลบเพราะ deferred revenue
    ทำให้ reinvestment ติดลบ ซึ่ง Phase 18 พิสูจน์แล้วว่าเป็นสูตรที่พังกับธุรกิจแบบนี้ ไม่ใช่
    ความจริงเรื่อง DUOL) — เก็บไว้ในลิสต์เพราะการซ่อนตัวที่ไม่ชอบใจออกคือการทำให้เลขดูมั่นคง
    กว่าที่เป็น แต่ติดธง `rejected` ไว้ให้อ่านออกว่าตัวไหนคือตัวที่โมเดลไม่เลือกและเพราะอะไร
    """
    if not dcf or market_cap is None or market_cap <= 0:
        return None
    tg, years = dcf.get("terminal_growth"), dcf.get("years")
    if tg is None or years is None:
        return None

    rejected = set(dcf.get("flags") or [])
    cands = []
    for source, raw_pct in raw.items():
        if raw_pct is None:
            continue
        family = ANCHOR_FAMILY.get(source, "history")
        growth = anchor_realistic(source, raw_pct, tg / 100.0, years)
        alt = fair_value({**dcf, "realistic_growth": growth}, market_cap)
        cands.append({
            "source": source,
            "label": ANCHOR_LABELS.get(source, source),
            "family": family,
            "raw_growth": round(raw_pct, 2),
            "growth": growth,
            "discount_pct": alt["discount_pct"] if alt else None,
            "used": source == used,
            # sustainable ถูกปฏิเสธก็ต่อเมื่อ guard ติดธง — ธงพวกนั้นพูดถึง sustainable ล้วน
            "rejected": source == "sustainable" and bool(rejected),
            # anchor ที่ค่าดิบชนเพดานก่อนเข้าโมเดล -> ค่าที่ออกมาคือ 'เพดาน' ไม่ใช่ 'ข้อมูล'
            "capped": (raw_pct > CAP_INITIAL_GROWTH * 100 if family == "history"
                       else raw_pct > SUSTAINABLE_GROWTH_CAP * 100),
        })
    discounts = [c["discount_pct"] for c in cands if c["discount_pct"] is not None]
    if len(discounts) < 2:
        return None

    lo, hi = min(discounts), max(discounts)
    spread = round(hi - lo, 1)
    growths = [c["growth"] for c in cands]
    level = ("narrow" if spread < _SPREAD_NARROW_PP
             else "wide" if spread > _SPREAD_WIDE_PP else "mixed")

    # ── ช่วงแคบเทียมจากเพดาน (เจอตอนวัด NVDA/DUOL จริง) ───────────────────────────
    # NVDA: anchor ฝั่งประวัติสามตัวคือ FCF CAGR 193.9%, รายได้ปีล่าสุด 65.5%, รายได้ CAGR
    # 100.1% — ต่างกันคนละโลก แต่ทั้งสามชนเพดาน CAP_INITIAL_GROWTH (35%) แล้ว fade ออกมาเป็น
    # 18.29% เท่ากันเป๊ะทั้งสามตัว ทำให้ช่วงแคบเหลือ 10.7pp และดูเหมือน "ทุกวิธีเห็นตรงกัน"
    # ทั้งที่ความจริงคือ **เพดานกลืนความไม่เห็นตรงกันไปหมด** — ความแคบนั้นเป็นสมบัติของกติกา
    # เรา ไม่ใช่หลักฐานเรื่องบริษัท. ถ้าไม่บอก มันจะเป็นตัวเลขที่ยิ่งมั่นใจตอนที่ยิ่งควรระวัง
    capped_history = [c for c in cands if c["capped"] and c["family"] == "history"]
    narrow_by_cap = level == "narrow" and len(capped_history) >= 2

    # ระยะห่างระหว่างสองครอบครัว — ต้นตอของช่วงกว้างเกือบทุกเคสที่วัดมา (AAPL/ADBE/DUOL/MSFT)
    st = [c["growth"] for c in cands if c["family"] == "structure"]
    hist = [c["growth"] for c in cands if c["family"] == "history"]
    structure_vs_history = (round(st[0] - sum(hist) / len(hist), 2) if st and hist else None)

    # anchor ที่เลือกไปให้ราคาที่คุ้มค่า "ใจกว้างที่สุด" ในบรรดาตัวเลือกหรือเปล่า — วัดจริงกับ
    # watchlist พบ 11/13 ตัวเป็นแบบนั้น (standard lens เลือก sustainable ซึ่งสูงกว่าประวัติเกือบ
    # ทุกครั้ง). ไม่ได้แปลว่าเลือกผิด — reinvestment × ROIC ควรสูงกว่า FCF CAGR ที่ถูกกด
    # ด้วย capex ของการเติบโตอยู่แล้วโดยนิยาม — แต่แปลว่าส่วนลดที่เห็นคือ **ขอบที่ดีที่สุด**
    # ของช่วง ไม่ใช่จุดกึ่งกลาง ซึ่งเป็นคนละเรื่องกันมากเวลาอ่าน
    used_row = next((c for c in cands if c["used"]), None)
    used_discount = used_row["discount_pct"] if used_row else None

    return {
        "candidates": sorted(cands, key=lambda c: (c["discount_pct"] is None, c["discount_pct"])),
        "used": used,
        "used_discount_pct": used_discount,
        "used_is_most_generous": used_discount is not None and used_discount >= hi,
        "growth_spread_pp": round(max(growths) - min(growths), 2),
        "discount_lo": lo,
        "discount_hi": hi,
        "discount_spread_pp": spread,
        "level": level,
        "capped_count": len(capped_history),
        "narrow_by_cap": narrow_by_cap,
        "structure_vs_history_pp": structure_vs_history,
    }


def implied_growth_rate(
    target_value: float,
    fcf_base: float,
    discount_rate: float,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> float | None:
    """หา growth g ที่ intrinsic_value(fcf_base, g, ...) == target_value พอดี (bisection).
    คืน None ถ้าแก้ไม่ได้จริงๆ: โมเดลไม่ valid (discount_rate <= terminal_growth) หรือ
    target_value อยู่นอกช่วง [_GROWTH_LO, _GROWTH_HI] ที่โมเดลนี้ตีความได้."""
    if discount_rate <= terminal_growth:
        return None

    lo, hi = _GROWTH_LO, _GROWTH_HI
    value_lo = intrinsic_value(fcf_base, lo, discount_rate, terminal_growth, years)
    value_hi = intrinsic_value(fcf_base, hi, discount_rate, terminal_growth, years)
    if target_value < value_lo or target_value > value_hi:
        return None  # นอกขอบเขตที่โมเดลตีความได้

    for _ in range(_MAX_ITER):
        mid = (lo + hi) / 2
        value_mid = intrinsic_value(fcf_base, mid, discount_rate, terminal_growth, years)
        if abs(value_mid - target_value) < max(1.0, target_value * _TOLERANCE):
            return round(mid * 100, 2)
        if value_mid < target_value:
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) * 100, 2)


def capm_wacc(beta: float | None, risk_free_pct: float, erp: float = DEFAULT_ERP) -> float:
    """WACC มาตรฐาน = Rf + β×ERP (CAPM). β clamp ไว้ [BETA_FLOOR, BETA_CAP] เสมอ — ตัวเดียวใน
    สูตรทั้งหมดที่ 'ต่างกันได้ตามหุ้น' ที่เหลือ (Rf ณ วันรัน, ERP) ล็อกเดียวกันทุกตัวเพื่อให้ gap
    เทียบข้ามหุ้นได้จริง. β ไม่มี (ข้อมูลขาด) -> ใช้ 1.0 (ความเสี่ยงเท่าตลาดเฉลี่ย, ค่ากลาง)."""
    b = 1.0 if beta is None else max(BETA_FLOOR, min(BETA_CAP, beta))
    return (risk_free_pct / 100.0) + b * erp


def reinvestment_rate(
    capex: float | None, da: float | None, nwc_change: float | None, nopat: float | None,
) -> float | None:
    """(Capex_จริง − D&A + ΔNWC_จริง) / NOPAT — สัดส่วนกำไรที่ลงทุนกลับเข้าธุรกิจ.
    capex/nwc_change เป็นเลขลบตามธรรมเนียม cash-flow statement ของ yfinance (เงินสดไหลออก),
    da เป็นเลขบวก (ธรรมเนียม add-back) — พลิกเครื่องหมาย capex/nwc_change ก่อนคำนวณ (ต้องการ
    'เงินลงทุนจริง'/'NWC ที่เพิ่มขึ้นจริง' เป็นบวก ไม่ใช่ทิศทางกระแสเงินสด). บริษัท deferred-
    revenue สูง (ลูกค้าจ่ายล่วงหน้า) จะได้ nwc_change เป็นบวกมาก (เงินสดไหลเข้าจาก NWC) ->
    real_nwc_increase ติดลบมาก -> reinvestment ติดลบได้ทั้งที่บริษัทโตจริง (ดู valuation_guard)."""
    if capex is None or da is None or nwc_change is None or not nopat:
        return None
    real_capex = -capex
    real_nwc_increase = -nwc_change
    return (real_capex - da + real_nwc_increase) / nopat


def sustainable_growth_rate(
    capex: float | None, da: float | None, nwc_change: float | None,
    nopat: float | None, roic_pct: float | None,
) -> float | None:
    """sustainable_growth = reinvestment_rate × ROIC (excess-returns growth model)."""
    rr = reinvestment_rate(capex, da, nwc_change, nopat)
    if rr is None or roic_pct is None:
        return None
    return rr * (roic_pct / 100.0)


# โหมดการตรวจ SUSTAINABLE_DIVERGES — ดู `_diverges` และ Phase 42 ใน AGENT_PROJECT.md
# ("revenue" = พฤติกรรมเดิมก่อน Phase 42 เก็บไว้ให้ A/B ย้อนได้ ไม่ใช่ตัวเลือกที่ใช้จริง)
DIVERGENCE_MODE = "either"


def _diverges(sustainable_pct: float, revenue_cagr: float | None,
              fcf_cagr: float | None, mode: str | None = None) -> bool:
    """sustainable_growth ขัดกับ 'สิ่งที่เกิดขึ้นจริง' มากพอจนไม่ควรเชื่อหรือยัง.

    **ทำไมต้องดูสองฝั่ง (Phase 42):** เดิมเทียบกับ revenue CAGR อย่างเดียว ทั้งที่ตั้งแต่ 19.4
    โมเดลตัดสินไปแล้วว่า **FCF CAGR คือหน่วยที่ถูกต้อง** ในการเทียบกับ implied_growth — ตัวตรวจ
    ความน่าเชื่อถือจึงทำงานกับปริมาณที่โมเดลเองบอกว่าใช้หน่วยผิด. MSFT คือหลักฐานสด: sustainable
    17.21 vs revenue CAGR 16.12 ห่างแค่ 1.1pp จึงไม่ติดธงเลย ขณะที่ FCF CAGR จริงบอก 4.04/7.43
    (FCF ลดลงสามปีติดขณะรายได้โต 35%) — ส่วนต่างที่ Phase 41 วัดได้ว่าทำให้ราคาที่คุ้มค่าวิ่ง 47pp

    แต่ **สลับไปใช้ FCF อย่างเดียวก็ผิดคนละทาง** — A/B แล้วพบว่า AAPL จะเลิกติดธง (sustainable
    19.07 vs FCF ยาว 6.67 = 12.4pp ลอดใต้เกณฑ์ 15pp) ทั้งที่รายได้โต 1.81%/ปี ซึ่งขัดกับ
    'ทบต้นได้ 19%/ปี' อย่างชัดเจน แล้วคะแนนขาราคาของ AAPL จะกระโดดจาก 0.0 เป็น ~2.9

    ข้อสรุปคือคำถามนี้ไม่มี 'ตัวเลขอ้างอิงตัวเดียวที่ถูก': **หลักฐานคัดค้านหนึ่งชิ้นก็พอ**
    ถ้าการวัดอดีตแบบใดแบบหนึ่งขัดกับ sustainable เกินเกณฑ์ = ไม่ควรเชื่อ sustainable
    ไม่ใช่ 'ต้องขัดทั้งคู่ถึงจะนับ' ซึ่งเป็นการให้ประโยชน์แห่งความสงสัยกับตัวเลขที่เราคำนวณเอง
    """
    refs = [r for r in (revenue_cagr, fcf_cagr) if r is not None]
    if not refs:
        return False
    if (mode or DIVERGENCE_MODE) == "revenue":
        refs = refs[:1] if revenue_cagr is not None else []
    elif (mode or DIVERGENCE_MODE) == "fcf":
        refs = [fcf_cagr] if fcf_cagr is not None else refs[:1]
    # ติดลบทั้งที่อดีตโตสองหลัก = ขัดแย้งเชิงทิศทาง ไม่ใช่แค่ห่างเป็นตัวเลข
    return any(
        (sustainable_pct < 0 and ref > 10.0)
        or abs(sustainable_pct - ref) > DIVERGENCE_TRIGGER_PP
        for ref in refs
    )


def valuation_guard(
    fcf_base: float | None, nopat: float | None, revenue: float | None,
    capex: float | None, da: float | None, nwc_change: float | None,
    roic_pct: float | None, historical_cagr: float | None,
    fcf_cagr: float | None = None,
) -> tuple[str, list[str], float | None]:
    """ตรวจว่า sustainable_growth เชื่อถือได้ไหมก่อนใช้เป็น realistic_growth หลัก (value lens)
    — คืน (route, flags, sustainable_pct). route: 'NA' (คำนวณ reverse-DCF ไม่ได้เลย) |
    'growth' (sustainable ไม่น่าเชื่อถือ -> ใช้ growth lens แทน) | 'standard' (ใช้ sustainable
    ตามปกติ). sustainable_pct เป็น % (เทียบหน่วยกับ historical_cagr ได้ตรงๆ).

    `fcf_cagr` (Phase 42) = การเติบโตของ **FCF** ที่วัดได้จริง (long-run ก่อน ไม่มีค่อยใช้
    หน้าต่าง yfinance) — ดู `_divergence_evidence` ว่าทำไมต้องดูทั้งสองฝั่ง ไม่ใช่เลือกข้าง"""
    if fcf_base is None or fcf_base <= 0:
        return "NA", ["FCF_NONPOSITIVE"], None

    flags: list[str] = []
    nopat_margin = (nopat / revenue) if (nopat and revenue) else None
    if nopat is None or nopat <= 0 or (nopat_margin is not None and nopat_margin < MIN_NOPAT_MARGIN):
        flags.append("NOPAT_UNSTABLE")

    rr = reinvestment_rate(capex, da, nwc_change, nopat)
    if rr is not None and rr < 0:
        flags.append("NEGATIVE_REINVESTMENT")

    sustainable_pct = round(rr * roic_pct, 2) if (rr is not None and roic_pct is not None) else None

    # ── fix 2026-08 (ต้นตอของ 'GOOGL realistic growth เด้ง 15.7 <-> 12.51' ที่ Phase 32 จับได้):
    # คำนวณ sustainable ไม่ได้เลย (input ตัวใดตัวหนึ่งขาด — เจอจริงคือ D&A หายจาก yfinance บางรอบ)
    # เดิมไม่ติดธงอะไรเลย -> flags ว่าง -> route = 'standard' -> แล้วโค้ดข้างล่างใน reverse_dcf
    # เจอ sustainable=None ก็ **เงียบๆ เปลี่ยนไปใช้ historical_cagr แทน** โดยยังปักป้าย lens
    # ว่า 'standard' เหมือนเดิม. ผลคือ anchor สลับไปมาระหว่างสองค่าตามความพร้อมของข้อมูล โดยไม่มี
    # ใครรู้ว่าคนละฐาน — ซึ่งคือนิยามของบั๊กที่ Phase 32 ถูกสร้างมาเพื่อจับ.
    #
    # ข้อมูลขาด = 'sustainable เชื่อไม่ได้' ซึ่งเป็นเงื่อนไขเดียวกับธงอื่นในฟังก์ชันนี้ทุกประการ
    # จึงต้องไป growth lens (anchor จาก FCF/revenue growth จริง ซึ่งไม่ต้องใช้ D&A) พร้อมติดธงให้
    # เห็น ไม่ใช่แอบเปลี่ยนไปใช้ CAGR ในอดีตแล้วบอกว่ายังเป็น lens เดิม
    if sustainable_pct is None:
        flags.append("SUSTAINABLE_UNCOMPUTABLE")

    if sustainable_pct is not None and _diverges(sustainable_pct, historical_cagr, fcf_cagr):
        flags.append("SUSTAINABLE_DIVERGES")

    route = "growth" if flags else "standard"
    return route, flags, sustainable_pct


def growth_lens_realistic(rev_growth_recent_pct: float, terminal_growth: float, years: int) -> float:
    """แทน sustainable_growth ด้วย 'growth จริงล่าสุดที่ fade ลงหา terminal' เมื่อ guard ไม่ไว้ใจ
    sustainable_growth — cap ปีแรกที่ CAP_INITIAL_GROWTH (ไม่เชื่อว่ายั่งยืนเกินนี้) แล้ว fade
    เชิงเส้นลงหา terminal ตลอด horizon คืนค่าเป็น CAGR-equivalent ของ path นั้น (%/ปี) เทียบกับ
    implied_growth ได้ตรงๆ — ไม่ 'โลกสวย' เชื่อว่า 40%+ จะคงอยู่ แต่ก็ไม่ติดลบมั่วเหมือน sustainable."""
    g0 = min(rev_growth_recent_pct / 100.0, CAP_INITIAL_GROWTH)
    factor = 1.0
    for t in range(years):
        g_t = g0 + (terminal_growth - g0) * (t / (years - 1)) if years > 1 else g0
        factor *= (1 + g_t)
    return round((factor ** (1 / years) - 1) * 100, 2)


def _rev_growth_recent(revenue_series: list[tuple[str, float]] | None) -> float | None:
    """% การเติบโตปีล่าสุด 'ปีเดียว' (ไม่ใช่ CAGR หลายปี) จาก revenue_series — sort ตาม period
    เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา). สำคัญ: StockFundamentals.revenue_series (จาก
    fundamentals.py) เรียงใหม่->เก่า แต่ health.py::_fy_series() (ที่ประกอบ duck object ตอน
    วิเคราะห์จริงผ่าน compute_health()) เรียงเก่า->ใหม่ — ถ้าไม่ sort เองตรงนี้จะหยิบผิดปี
    (เจอ bug จริง: DUOL ได้ realistic_growth ติดลบทั้งที่โต 41%/ปี เพราะหยิบ FY2022→FY2023
    แทนที่จะเป็น FY2024→FY2025)."""
    if not revenue_series or len(revenue_series) < 2:
        return None
    ordered = sorted(revenue_series, key=lambda p: p[0])   # เก่า -> ใหม่ (period string เรียงตรงตามเวลา)
    newest, prev = ordered[-1][1], ordered[-2][1]
    if prev <= 0:
        return None
    return round((newest / prev - 1) * 100, 2)


def _fcf_base_3yr(fcf_series: list[tuple[str, float]], fallback_fcf: float | None) -> float | None:
    """ค่าเฉลี่ย FCF 3 ปีล่าสุด — sort ตาม period เองเสมอ (ไม่พึ่ง order ที่ caller ส่งมา) กันปีที่
    ผิดปกติปีเดียวมาบิดผลทั้งโมเดล. ไม่มี series เลย (ข้อมูลขาด) -> fallback ไป TTM free_cash_flow
    ตัวเดียว (ดีกว่าคำนวณไม่ได้เลย).
    audit fix (2026-07, bug เดียวกับ _rev_growth_recent): เดิม assume fcf_series เรียงใหม่->เก่า
    เสมอ (ตามที่ fundamentals.py คืนมา) แล้วหยิบ [:3] ตรงๆ — แต่ health.py::_build_duck_fundamentals
    (ใช้ตอนคำนวณ valuation component ของ health score ผ่าน compute_health()) ประกอบ fcf_series
    ด้วย _fy_series() ซึ่งเรียงเก่า->ใหม่ (ตรงข้าม) ทำให้หยิบ 3 ปีเก่าสุดแทนที่จะเป็น 3 ปีล่าสุด —
    เจอบั๊กจริงกับ DUOL: fcf_base จากพาธ health.py ต่ำกว่าพาธจริง (loop.py) ถึง 71%
    (149M vs 255M) ทำให้ implied_growth ที่ใช้ตัดสิน valuation component ของ health score เพี้ยน
    (ฐานเล็กกว่าจริง -> ต้องการ growth สูงกว่าจริงถึงจะ justify EV เดียวกัน -> gap ดูแพงเกินจริง)."""
    if not fcf_series:
        return fallback_fcf
    ordered = sorted(fcf_series, key=lambda p: p[0])   # เก่า -> ใหม่ เสมอ ไม่พึ่ง order ที่ caller ส่งมา
    recent = ordered[-3:]
    return sum(v for _, v in recent) / len(recent)


def _fcf_growth_multiyear(fcf_series: list[tuple[str, float]] | None) -> float | None:
    """CAGR ของ FCF ตลอดช่วงที่มีข้อมูล (ล่าสุด vs เก่าสุด) — sort เองเสมอเหมือน _rev_growth_recent.
    None ถ้าข้อมูลไม่พอ หรือปลายทางฝั่งใดฝั่งหนึ่งไม่เป็นบวก (FCF ติดลบ/ศูนย์ช่วงต้น พบได้ทั่วไปกับ
    บริษัทโตเร็วที่ยัง burn cash อยู่ตอนเริ่ม — CAGR ไม่มีความหมายทางคณิตศาสตร์ ต้อง fallback ไป
    revenue growth แทน).

    audit fix 19.4 (2026-07, valuation unit mismatch): growth lens เดิมเทียบ implied_growth
    (FCF growth ที่ตลาด price ไว้ — มาจาก intrinsic_value ที่ compound fcf_base) กับ realistic_growth
    ที่ anchor จาก REVENUE growth (rev_growth_recent/historical_cagr) — apples-to-oranges เวลา
    margin กำลังขยายตัว (บริษัท asset-light ที่กำลัง scale, operating leverage สูง) FCF จะโตเร็วกว่า
    revenue เป็นปกติ (เช่น DUOL จริง: revenue CAGR 41.08%/ปี แต่ FCF CAGR ช่วงเดียวกัน 102.3%/ปี
    — margin ขยายจาก -17.64% เป็น 13.07% operating margin) ใช้ revenue growth มาเป็น proxy ของ
    FCF growth เลยประเมิน 'ความเร็วที่ยั่งยืนได้จริง' ต่ำกว่าความเป็นจริงไปมาก. ตอนนี้ใช้ FCF CAGR
    เป็น anchor หลักเมื่อคำนวณได้ (unit เดียวกับ implied_growth ตรงๆ) fallback ไป revenue growth
    เฉพาะตอน FCF history สั้นเกินไป/สลับเครื่องหมาย (CAGR ไร้ความหมาย) เท่านั้น."""
    if not fcf_series or len(fcf_series) < 2:
        return None
    ordered = sorted(fcf_series, key=lambda p: p[0])
    oldest, newest = ordered[0][1], ordered[-1][1]
    years = len(ordered) - 1
    if oldest <= 0 or newest <= 0:
        return None
    return round(((newest / oldest) ** (1 / years) - 1) * 100, 2)


# gap boundary ของ valuation /3 (เดิม hardcode 0/5/10 ใน step function ตรงๆ) — ยังเป็นจุดอ้างอิง
# เดิมทุกอย่าง (gap<0=ถูกมาก เต็ม 3, ทุก 5pp ถัดไปลดลง 1 แต้ม) แค่ตอนนี้ไล่ระดับรอบแต่ละจุดแทนที่
# จะพลิกเป๊ะ (audit fix 20.1 — ดู GAP_BAND_PP ด้านล่าง)
GAP_PP_FULL = 0.0    # ~gap นี้ (implied < realistic = ตลาดคาดต่ำกว่าที่ทำได้จริง) -> ~3 เต็ม
GAP_PP_GOOD = 5.0    # ~gap นี้ -> ~2
GAP_PP_FAIR = 10.0   # ~gap นี้ -> ~1, เกินไปมาก -> เข้าใกล้ 0 (แพงเกินกว่าจะ justify ด้วย growth ที่ทำได้จริง)

# audit fix 20.1 (2026-07, ต่อจาก 19.3/19.5): เดิม _gap_to_score เป็น step function ล้วน — 19.5
# sensitivity เจอว่านี่คือ threshold ที่เปราะที่สุดในทั้งระบบ (GAP_PP_FAIR=10pp พลิก tier ที่ 9.5,
# ห่างแค่ 0.5pp) เพราะฝั่ง fundamental ทำ graded ไปแล้ว (19.3) แต่ฝั่ง valuation ยังไม่ทำ. แก้แบบ
# เดียวกับ 19.3: รอบ boundary แต่ละจุด (0/5/10pp) ไล่ระดับอิสระต่อกัน (เหมือนแต่ละเกณฑ์ fundamental)
# แล้วรวมกัน — band แคบกว่า BAND_PCT ทั่วไปของ health.py (3pp) โดยตั้งใจ เพราะระยะห่างระหว่าง
# boundary เอง (5pp) แคบกว่าฝั่ง fundamental มาก ถ้าใช้ band 3pp เต็มจะ overlap กันจนจุดกึ่งกลาง
# ระหว่าง boundary ไม่มี 'จุดเต็ม/จุดศูนย์' ที่ชัดเจนเหลือเลย
GAP_BAND_PP = 2.0


def _gap_to_score(gap_pp: float) -> float:
    """gap = implied − realistic (จุดร้อยละ) -> คะแนน /3 แบบไล่ระดับ (audit fix 20.1). ผลรวมของ
    3 graded step อิสระต่อกัน รอบ boundary เดิม (GAP_PP_FULL/GOOD/FAIR) — gap ที่ห่างทุก boundary
    มากๆ (ส่วนใหญ่ของ watchlist) ยังได้ 3.0/0.0 เท่าเดิม กระทบเฉพาะเคสที่ใกล้ boundary จริง
    (เหมือนหลักการเดียวกับ health.py::_fundamental_score ที่ทำกับ /8 ตั้งแต่ 19.3)."""
    return round(
        graded_below(gap_pp, GAP_PP_FULL, GAP_BAND_PP)
        + graded_below(gap_pp, GAP_PP_GOOD, GAP_BAND_PP)
        + graded_below(gap_pp, GAP_PP_FAIR, GAP_BAND_PP),
        2,
    )


# หน้าต่างข้อมูลที่สั้นกว่านี้ = ยังไม่ครอบรอบวัฏจักรใดๆ (yfinance คืนมา 4 ปีเป็นปกติ)
SHORT_WINDOW_YEARS = 6


def _anchor_window(series: list[tuple[str, float]] | None, source: str) -> dict:
    """เมตาดาต้าของ 'หน้าต่างข้อมูล' ที่ anchor ถูกคำนวณมา — ไม่กระทบคะแนนใดๆ ทั้งสิ้น.

    ทำไมต้องมี (เจอจริงกับ CVX 2026-08): yfinance คืน series มา 4 ปี และบังเอิญปีแรกคือ
    FY2022 = ยอดพีคราคาน้ำมันรอบสิบปี ทุกปีหลังจากนั้นจึงเป็น 'ขาลง' โดยอัตโนมัติ -> FCF CAGR
    −23%/ปี -> realistic growth −11.09% -> ขาราคา 0/3. แต่ประวัติจริงจาก SEC XBRL 8 ปี
    (159/140/94/156/236/197/193/184) บอกว่านั่นคือ *รอบ* ไม่ใช่ธุรกิจถดถอย — รายได้วันนี้ยัง
    สูงกว่าปี 2018 ด้วยซ้ำ.

    ไม่ใช่ปัญหาของหุ้นน้ำมันโดยเฉพาะ: บริษัทไหนที่ปีแรกของหน้าต่างเป็นปีผิดปกติก็เพี้ยนทั้งคู่
    แค่คนละทิศ (เริ่มที่ก้นเหว = โตเกินจริง). ตัวนี้แค่ 'บอกให้รู้' ว่าเลขมาจากหน้าต่างแบบไหน —
    จะไม่เดาแทนว่าควรใช้กี่ปี เพราะการเปลี่ยน anchor เป็นการขยับคะแนนทั้งกระดาน ซึ่งเป็นคนละงาน
    """
    pts = sorted(series or [], key=lambda p: p[0])
    if len(pts) < 2:
        return {"source": source, "years": len(pts), "start": None, "end": None,
                "starts_at_max": False, "starts_at_min": False, "flags": []}

    values = [v for _, v in pts]
    first = values[0]
    starts_at_max = first == max(values)
    starts_at_min = first == min(values)

    flags = []
    if len(pts) < SHORT_WINDOW_YEARS:
        flags.append("SHORT_WINDOW")
    # ปีแรกเป็นจุดสูงสุด/ต่ำสุดของหน้าต่าง = เทรนด์ที่วัดได้เท่ากับ 'ระยะห่างจากปีนั้น' ไม่ใช่เทรนด์
    if starts_at_max:
        flags.append("STARTS_AT_WINDOW_HIGH")
    elif starts_at_min:
        flags.append("STARTS_AT_WINDOW_LOW")

    return {"source": source, "years": len(pts), "start": pts[0][0], "end": pts[-1][0],
            "starts_at_max": starts_at_max, "starts_at_min": starts_at_min, "flags": flags}


@dataclass
class ReverseDcfResult:
    implied_growth: float | None      # % ต่อปีที่ตลาด 'price ไว้' — None ถ้าคำนวณไม่ได้/นอกขอบเขต
    realistic_growth: float | None    # % ต่อปี — anchor ที่ใช้เทียบ gap จริง (มาจาก lens ไหนดู field lens)
    historical_cagr: float | None     # % ต่อปี — raw revenue CAGR (อ้างอิง/cross-check เท่านั้น)
    gap: float | None                 # implied − realistic (pp)
    score: float | None                # 0.0-3.0 (graded จาก gap, 20.1 — ปรับด้วย Rule of 40 ถ้า lens='growth')
    lens: str                         # "standard" | "growth" | "NA" — ใช้แยกกลุ่มตอน backtest ห้ามปนกัน
    flags: list[str]                  # เหตุผลที่ route (FCF_NONPOSITIVE/NOPAT_UNSTABLE/NEGATIVE_REINVESTMENT/SUSTAINABLE_DIVERGES)
    rule_of_40: float | None          # rev_growth_recent% + fcf_margin% (เฉพาะ lens='growth')
    wacc: float                       # % CAPM ที่ใช้จริง (หลัง clamp β)
    beta_used: float                  # β หลัง clamp [BETA_FLOOR, BETA_CAP]
    terminal_growth: float            # %
    years: int
    ev: float | None                  # Market Cap + Net Debt ที่ใช้เป็นเป้าหมายแก้สมการ
    fcf_base: float | None            # ค่าเฉลี่ย FCF 3 ปีที่ใช้เป็นฐานโมเดล
    note: str | None = None           # เหตุผลเวลาคำนวณไม่ได้ (fcf ติดลบ/นอกขอบเขต/ข้อมูลขาด)
    # หน้าต่างข้อมูลที่ anchor มาจาก — metadata ล้วน ไม่เข้าคะแนน (ดู _anchor_window)
    anchor_window: dict | None = None

    def to_dict(self) -> dict:
        return {
            "implied_growth": self.implied_growth,
            "realistic_growth": self.realistic_growth,
            "historical_cagr": self.historical_cagr,
            "gap": self.gap,
            "score": self.score,
            "lens": self.lens,
            "flags": self.flags,
            "rule_of_40": self.rule_of_40,
            "wacc": self.wacc,
            "beta_used": self.beta_used,
            "terminal_growth": self.terminal_growth,
            "years": self.years,
            "ev": self.ev,
            "fcf_base": self.fcf_base,
            "note": self.note,
            "anchor_window": self.anchor_window,
        }


def reverse_dcf(
    fundamentals,
    risk_free_pct: float = FALLBACK_RISK_FREE_PCT,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_YEARS,
) -> dict | None:
    """รับ StockFundamentals (หรือ duck-object แบบเดียวกัน — ต้องมี free_cash_flow, market_cap,
    revenue_cagr, revenue, fcf_series, revenue_series, net_debt, beta, capex,
    depreciation_amortization, nwc_change, nopat, roic, fcf_margin) -> dict (ผ่าน
    ReverseDcfResult.to_dict()). คืน None ถ้าข้อมูลพื้นฐาน (market_cap) ไม่มีเลย — คำนวณไม่ได้
    ตั้งแต่ต้น. risk_free_pct ควรมาจาก src.providers.stock.market.get_risk_free_rate_pct()."""
    # fix 2026-08: EV = market_cap + net_debt ซึ่งอยู่คนละสกุลได้ถ้าเป็น ADR ต่างชาติ (งบสกุล
    # บ้านเกิด ราคา USD) — เจอจริงทั้งคู่ใน watchlist: TSM ได้ ev = 3.93e11 จาก USD 2.10e12 +
    # TWD -1.70e12, ASML คำนวณ implied growth 31.4%/ปี จาก EV สกุล USD หารด้วย FCF สกุล EUR
    # แล้วให้คะแนนขาราคา 0.0/3 ไปเต็มๆ. TSM รอดมาได้เพราะผลลัพธ์บังเอิญหลุดช่วงที่โมเดลตีความ
    # ได้ (= รอดด้วยโชค ไม่ใช่ด้วยการออกแบบ). ตัวเลขที่คำนวณจากสองสกุลไม่ใช่ตัวเลขที่ผิดนิดหน่อย
    # — มันไม่มีความหมายเลย จึงต้องปฏิเสธ ไม่ใช่ปรับแก้
    if getattr(fundamentals, "currency_mismatch", False):
        return None

    market_cap = fundamentals.market_cap
    if market_cap is None or market_cap <= 0:
        return None

    fcf_base = _fcf_base_3yr(getattr(fundamentals, "fcf_series", None), fundamentals.free_cash_flow)

    net_debt = getattr(fundamentals, "net_debt", None) or 0.0
    ev = market_cap + net_debt

    beta = getattr(fundamentals, "beta", None)
    beta_used = 1.0 if beta is None else max(BETA_FLOOR, min(BETA_CAP, beta))
    wacc = capm_wacc(beta, risk_free_pct)

    historical_cagr = fundamentals.revenue_cagr
    nopat = getattr(fundamentals, "nopat", None)
    roic = getattr(fundamentals, "roic", None)
    capex = getattr(fundamentals, "capex", None)
    da = getattr(fundamentals, "depreciation_amortization", None)
    nwc_change = getattr(fundamentals, "nwc_change", None)
    revenue = getattr(fundamentals, "revenue", None)

    # Phase 42: anchor ฝั่งประวัติต้องคำนวณ **ก่อน** guard เพราะ guard ต้องใช้ FCF CAGR เป็น
    # หลักฐานด้วย ไม่ใช่ revenue CAGR อย่างเดียว (ดู _diverges)
    rev_growth_recent = _rev_growth_recent(getattr(fundamentals, "revenue_series", None))
    fcf_series = getattr(fundamentals, "fcf_series", None)
    revenue_series = getattr(fundamentals, "revenue_series", None)
    fcf_cagr_long = getattr(fundamentals, "fcf_cagr_long", None)
    fcf_cagr_short = _fcf_growth_multiyear(fcf_series)
    # long-run ก่อนเสมอ ลำดับเดียวกับตอนเลือก anchor จริง — ไม่งั้น guard กับ anchor จะมองคนละปี
    fcf_cagr_ref = fcf_cagr_long if fcf_cagr_long is not None else fcf_cagr_short

    route, flags, sustainable = valuation_guard(
        fcf_base, nopat, revenue, capex, da, nwc_change, roic, historical_cagr,
        fcf_cagr=fcf_cagr_ref,
    )

    base_result = dict(
        historical_cagr=historical_cagr, wacc=round(wacc * 100, 2), beta_used=round(beta_used, 2),
        terminal_growth=round(terminal_growth * 100, 2), years=years,
        ev=round(ev, 2), fcf_base=round(fcf_base, 2) if fcf_base is not None else None, flags=flags,
    )

    if route == "NA":
        return ReverseDcfResult(
            implied_growth=None, realistic_growth=None, gap=None, score=None,
            lens="NA", rule_of_40=None,
            note="FCF ฐาน (เฉลี่ย 3 ปี) ติดลบ/เป็นศูนย์ — reverse-DCF ใช้ไม่ได้กับบริษัทที่ยัง burn cash อยู่",
            **base_result,
        ).to_dict()

    fcf_margin = getattr(fundamentals, "fcf_margin", None)
    r40 = (
        round(rev_growth_recent + fcf_margin, 2)
        if rev_growth_recent is not None and fcf_margin is not None else None
    )

    # Phase 41: คำนวณ anchor "ทุกตัวที่คำนวณได้" ตรงนี้ที่เดียว แล้วให้ทั้งขาเลือก lens และขา
    # วัดความมั่นใจอ่านจากชุดเดียวกัน — เดิม fcf_growth/long_cagr ถูกคำนวณในกิ่ง growth เท่านั้น
    # ทำให้หุ้น standard lens (MSFT/GOOGL/META/...) ไม่เคยรู้ด้วยซ้ำว่า anchor ฝั่งประวัติของมัน
    # ตอบว่าเท่าไร ทั้งที่นั่นคือข้อมูลที่ชี้ขาดว่าควรเชื่อราคาที่คุ้มค่าแค่ไหน
    raw_anchors = {
        "sustainable": sustainable,
        "fcf_long": fcf_cagr_long,
        "fcf": fcf_cagr_short,
        "revenue_recent": rev_growth_recent,
        "revenue_cagr": historical_cagr,
    }

    if route == "growth":
        lens = "growth"
        # audit fix 19.4: anchor บน FCF growth ก่อนเสมอถ้าคำนวณได้ (unit เดียวกับ implied_growth
        # ตรงๆ — ดู docstring _fcf_growth_multiyear) revenue growth เป็นแค่ fallback ตอน FCF
        # history สั้นเกินไป/สลับเครื่องหมาย
        # Phase 36: ถ้ามีประวัติ FCF จากงบที่ยื่นจริง (ยาวกว่า 4 ปีของ yfinance มาก) ใช้ตัวนั้นก่อน
        # — หน้าต่าง 4 ปีที่บังเอิญเริ่มปีผิดปกติทำให้ 'เทรนด์' กลายเป็น 'ระยะห่างจากปีนั้น'
        # (CVX เริ่มที่ยอดพีคน้ำมัน FY2022). provider ตรวจแล้วว่าปีที่ทับกันตรงกับ yfinance
        # ถึงจะยอมส่งค่ามา ไม่งั้นส่ง None แล้วตรงนี้ทำงานเหมือนเดิมทุกประการ
        long_cagr = fcf_cagr_long
        long_window = getattr(fundamentals, "fcf_long_window", None)
        fcf_growth = fcf_cagr_short
        if long_cagr is not None:
            anchor_growth, used_anchor = long_cagr, "fcf_long"
            window = {"source": "fcf_long", "years": getattr(fundamentals, "fcf_long_years", None),
                      "start": (long_window or "-").split("-")[0],
                      "end": (long_window or "-").split("-")[-1],
                      "starts_at_max": False, "starts_at_min": False, "flags": []}
        elif fcf_growth is not None:
            anchor_growth, used_anchor = fcf_growth, "fcf"
            window = _anchor_window(fcf_series, "fcf")
        elif rev_growth_recent is not None:
            anchor_growth, used_anchor = rev_growth_recent, "revenue_recent"
            window = _anchor_window(revenue_series, "revenue")
        else:
            anchor_growth, used_anchor = historical_cagr, "revenue_cagr"
            window = _anchor_window(revenue_series, "revenue_cagr")
        realistic_growth = (
            growth_lens_realistic(anchor_growth, terminal_growth, years)
            if anchor_growth is not None else historical_cagr
        )
    else:
        lens = "standard"
        # sustainable growth คิดจากค่า ณ จุดเดียว (reinvestment × ROIC) ไม่ใช่หน้าต่างย้อนหลัง
        # -> ไม่มีประเด็นเรื่องหน้าต่าง ยกเว้นตอนตกไปใช้ historical_cagr เป็น fallback
        if sustainable is not None:
            realistic_growth = round(max(-100.0, min(SUSTAINABLE_GROWTH_CAP * 100, sustainable)), 2)
            used_anchor = "sustainable"
            window = {"source": "sustainable", "years": None, "start": None, "end": None,
                      "starts_at_max": False, "starts_at_min": False, "flags": []}
        else:
            realistic_growth = historical_cagr
            used_anchor = "revenue_cagr"
            window = _anchor_window(revenue_series, "revenue_cagr")

    implied = implied_growth_rate(ev, fcf_base, wacc, terminal_growth, years)
    note = None
    if implied is None:
        note = (
            f"ราคาปัจจุบันอยู่นอกช่วงที่โมเดลนี้ตีความได้ ({_GROWTH_LO*100:.0f}% ถึง "
            f"{_GROWTH_HI*100:.0f}% ต่อปี) — อาจกำลัง price ปัจจัยอื่นที่ไม่ใช่ FCF growth ธรรมดา"
        )
    gap = round(implied - realistic_growth, 2) if implied is not None and realistic_growth is not None else None
    score = _gap_to_score(gap) if gap is not None else None

    # Rule of 40: growth lens เท่านั้น — โตไม่จริง+เผาเงิน ห้ามตัดสินว่า "ถูก" (score เพดานที่ 1)
    # (เพดานนี้ยังเป็น hard cap ตั้งใจ ไม่ใช่ graded — sensitivity 19.5 เจอว่า RULE40_WEAK inert
    # สำหรับ watchlist ปัจจุบัน และเป็นคนละกลไกกับ gap->score curve ที่ 20.1 แก้ ไม่ได้อยู่ใน scope นี้)
    if lens == "growth" and score is not None and r40 is not None and r40 < RULE40_WEAK:
        score = min(score, 1.0)

    out = ReverseDcfResult(
        implied_growth=implied, realistic_growth=realistic_growth, gap=gap, score=score,
        lens=lens, rule_of_40=r40, note=note, anchor_window=window, **base_result,
    ).to_dict()
    # คำนวณที่นี่ที่เดียวแล้วติดไปกับผล เพื่อให้ทุกฝั่ง (คะแนน/หน้าเว็บ/ประวัติ) อ่านเลขตัวเดียวกัน
    # — บั๊กประจำของโปรเจกต์คือตรรกะเดียวกันถูกเขียนสองที่แล้วตอบไม่ตรงกัน (33.3, 34, 39)
    out["fair"] = fair_value(out, market_cap)
    # Phase 41: ราคาที่คุ้มค่าเปลี่ยนไปแค่ไหนถ้าเลือก anchor อีกตัว — ตัวเลขที่ `pct_per_pp`
    # ทำท่าจะบอกแต่บอกไม่ได้จริง (ดู block ความเห็นเหนือ anchor_agreement)
    out["agreement"] = anchor_agreement(out, market_cap, raw_anchors, used_anchor)
    return out


if __name__ == "__main__":
    # เครื่องมือ debug: python -m src.agent.valuation AAPL
    import sys
    from src.providers.stock.fundamentals import StockFundamentalsProvider
    from src.providers.stock.market import get_risk_free_rate_pct

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    f = StockFundamentalsProvider().get_fundamentals(ticker)
    rf = get_risk_free_rate_pct()
    result = reverse_dcf(f, risk_free_pct=rf)
    print(f"=== {ticker} reverse-DCF (Rf={rf:.2f}%) ===")
    print(f"Market Cap = {f.market_cap:,.0f}" if f.market_cap else "Market Cap = N/A")
    print(f"Beta       = {f.beta}")
    for k, v in (result or {}).items():
        print(f"  {k:18} = {v}")