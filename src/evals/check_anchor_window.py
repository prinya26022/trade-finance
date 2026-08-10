"""หน้าต่างข้อมูลที่ anchor ถูกคำนวณมา ครอบรอบวัฏจักรหรือยัง (Phase 35).

เจอจาก CVX (2026-08): yfinance คืน revenue/FCF มา 4 ปี และปีแรกคือ FY2022 = ยอดพีคราคาน้ำมัน
รอบสิบปีพอดี ทุกปีหลังจากนั้นจึงเป็น "ขาลง" โดยอัตโนมัติ -> FCF CAGR ติดลบหนัก -> realistic
growth −11.09%/ปี -> ขาราคา 0/3 -> health 3.2/11. ประวัติจริงจาก SEC XBRL 8 ปีบอกคนละเรื่อง:
159/140/94/156/236/197/193/184 = **รอบวัฏจักร** ไม่ใช่ธุรกิจถดถอย (รายได้วันนี้ยังสูงกว่าปี 2018)

eval นี้ไม่แก้คะแนนอะไรทั้งนั้น — หน้าที่เดียวคือบอกว่าหน้าต่างที่ใช้อยู่กว้างพอจะเรียกว่า
"เทรนด์" ไหม โดยเทียบกับประวัติยาวจาก SEC XBRL ที่เราดึงมาตรวจความแม่นอยู่แล้วตั้งแต่ Phase 12
(cache ดิสก์ 7 วัน ไม่ได้ยิงเพิ่มต่อรอบ) การเปลี่ยน anchor จริงเป็นคนละงาน เพราะขยับคะแนน
ทั้งกระดานและต้อง backfill — ตัวนี้มีไว้ให้ตัดสินใจเรื่องนั้นบนตัวเลข ไม่ใช่บนความรู้สึก

**บทเรียนจากรอบแรกของ eval นี้เอง (แก้แล้ว):** เวอร์ชันแรกเทียบ CAGR ของสองชุดตรงๆ โดยไม่เช็ค
ว่าช่วงเวลาทับกันไหม — NVDA มี XBRL ถึง FY2022 แต่ yfinance เริ่ม FY2023 = **ไม่ทับกันเลย**
แล้วมันรายงานว่า "4 ปี +100% เทียบ 6 ปี +31%" ราวกับเป็นเทรนด์เดียวกันวัดยาวขึ้น ทั้งที่เป็น
คนละยุค และตั้งธง "เริ่มที่ปีสูงสุดของรอบ" เพราะปีเริ่มของหน้าต่างสั้นมากกว่าทุกค่าในชุดเก่า
เครื่องมือที่เทียบของคนละชุดแล้วดูน่าเชื่อ คือสิ่งเดียวกับบั๊กที่มันถูกสร้างมาจับ

    python -m src.evals.check_anchor_window CVX XOM MSFT
"""
from src.domain.series import cagr_pct, missing_years
from src.providers.stock.xbrl import get_annual_series

# ต่ำกว่านี้ถือว่ายังไม่ครอบรอบ (yfinance คืน 4 ปีเป็นปกติ)
MIN_CYCLE_YEARS = 6
# ปีแรกของหน้าต่างอยู่ใน 25% บน/ล่างของประวัติยาว = หน้าต่างเริ่มที่ปีผิดปกติ
EXTREME_PERCENTILE = 0.25
# ส่วนต่าง CAGR สั้น-vs-ยาวที่ถือว่า "หน้าต่างเปลี่ยนคำตอบจริง" — ต่ำกว่านี้คือรายละเอียด
# (ถ้าตั้งธงกับทุกตัวที่หน้าต่างสั้น ธงจะติดทั้งกระดานทุกวันแล้วไม่มีความหมาย)
MATERIAL_GAP_PP = 10.0


def _percentile_of(value: float, values: list[float]) -> float:
    if len(values) < 2:
        return 0.5
    return round(sum(1 for v in values if v < value) / (len(values) - 1), 2)


def _merge(long: list[tuple[str, float]],
           short: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """ประวัติยาว + ปีใหม่ที่ XBRL ยังไม่มี — งวดที่ซ้ำเอาของ short (สดกว่า/ผ่าน restatement แล้ว).

    ต้องรวมก่อนเทียบเสมอ ไม่งั้นจะเทียบ 'คนละยุค' แล้วสรุปว่าเป็นเทรนด์เดียวกันวัดยาวขึ้น
    """
    merged = dict(long)
    merged.update(dict(short))
    return sorted(merged.items(), key=lambda p: p[0])


def check_one(ticker: str, short_series: list[tuple[str, float]] | None = None,
              long_series: list[tuple[str, float]] | None = None,
              concept: str = "FCF") -> dict:
    """เทียบหน้าต่างสั้น (ที่ระบบใช้จริง) กับประวัติยาวที่รวมแล้ว. คืน dict เสมอ ไม่ raise.

    ปริยายเป็น **FCF** เพราะนั่นคือสิ่งที่ growth lens ใช้เป็น anchor จริง (ตั้งแต่ 19.4) —
    เครื่องมือที่วัดคนละตัวกับที่ระบบใช้ตัดสิน ก็ตอบคำถามที่ไม่มีใครถาม. `concept="Revenues"`
    ยังเรียกได้ไว้ดูฝั่งรายได้ประกอบ
    """
    out = {"ticker": ticker, "concept": concept, "short": None, "long": None,
           "cagr_gap_pp": None, "flags": [], "note": None}

    if short_series is None:
        try:
            from src.providers.stock.fundamentals import StockFundamentalsProvider
            obj = StockFundamentalsProvider().get_fundamentals(ticker)
            short_series = obj.fcf_series if concept == "FCF" else obj.revenue_series
        except Exception as e:                          # noqa: BLE001
            out["note"] = f"ดึงข้อมูลฝั่ง provider ไม่ได้: {e}"
            return out

    short = sorted(short_series or [], key=lambda p: p[0])
    if long_series is None:
        if concept == "FCF":
            from src.providers.stock.xbrl import annual_fcf_series
            long_series = annual_fcf_series(ticker)
        else:
            long_series = (get_annual_series(ticker) or {}).get(concept) or []
    long = sorted(long_series, key=lambda p: p[0])

    out["short"] = {"years": len(short), "start": short[0][0] if short else None,
                    "end": short[-1][0] if short else None, "cagr": cagr_pct(short)}

    if not long:
        # XOM เจอเคสนี้จริง ทั้งที่เป็นผู้ยื่น 10-K อเมริกันปกติ = ช่องโหว่ชื่อ concept ไม่ใช่ข้อสรุป
        out["flags"].append("NO_LONG_HISTORY")
        out["note"] = "ไม่มีประวัติยาวจาก SEC XBRL ให้เทียบ (ชื่อ concept ที่รองรับยังไม่ครอบ)"
        return out

    if not short:
        out["note"] = "ไม่มี series ฝั่ง provider ให้เทียบ"
        return out

    # ประวัติยาวต้อง 'ย้อนก่อน' หน้าต่างสั้นจริงๆ ถึงจะเรียกว่าขยายหน้าต่างได้
    if not any(p < short[0][0] for p, _ in long):
        out["flags"].append("LONG_HISTORY_TOO_OLD")
        out["note"] = (f"XBRL มีถึง {long[-1][0]} แต่หน้าต่างที่ใช้เริ่ม {short[0][0]} — "
                       "ไม่ทับกัน เทียบเป็นเทรนด์เดียวกันไม่ได้")
        return out

    # ...และต้องมีปีที่ **ทับกัน** อย่างน้อยหนึ่งปี ไม่งั้นพิสูจน์ไม่ได้เลยว่าสองแหล่งพูดถึง
    # อนุกรมเดียวกัน (NVDA: XBRL ถึง FY2022, provider เริ่ม FY2023 — ต่อกันพอดีแต่ไม่เคยทับ).
    # กติกาเดียวกับที่ฝั่ง anchor ใช้ก่อนยอมเปลี่ยนแหล่งข้อมูล (fundamentals._long_fcf_growth)
    if not (set(dict(long)) & set(dict(short))):
        out["flags"].append("NO_OVERLAP_TO_VERIFY")
        out["note"] = (f"ไม่มีปีที่ทับกันเลย (XBRL {long[0][0]}-{long[-1][0]} vs "
                       f"{short[0][0]}-{short[-1][0]}) — ยืนยันไม่ได้ว่าเป็นอนุกรมเดียวกัน")
        return out

    merged = _merge(long, short)

    # ปีที่ขาดกลางไม่ทำให้ CAGR ผิด (cagr_pct คิดจากช่วงปีจริง ไม่ใช่จำนวนจุด — ดู
    # domain/series.py) แต่ยังต้องรายงาน เพราะมันแปลว่าแท็กบัญชีเปลี่ยนกลางทาง = สัญญาณว่า
    # นิยามอาจไม่ต่อเนื่องตลอดเส้น
    missing = missing_years(merged)
    if missing:
        out["flags"].append("HISTORY_HAS_GAP")
        out["note"] = f"ประวัติขาดช่วง {', '.join(missing)} (แท็กบัญชีน่าจะเปลี่ยนปีนั้น)"
    out["long"] = {"years": len(merged), "start": merged[0][0], "end": merged[-1][0],
                   "cagr": cagr_pct(merged)}

    pct = _percentile_of(short[0][1], [v for _, v in merged])
    out["short"]["start_percentile"] = pct

    if len(short) < MIN_CYCLE_YEARS <= len(merged):
        out["flags"].append("SHORT_WINDOW")
    if pct >= 1 - EXTREME_PERCENTILE:
        out["flags"].append("WINDOW_STARTS_AT_CYCLE_HIGH")
    elif pct <= EXTREME_PERCENTILE:
        out["flags"].append("WINDOW_STARTS_AT_CYCLE_LOW")

    s, l = out["short"]["cagr"], out["long"]["cagr"]
    if s is not None and l is not None:
        out["cagr_gap_pp"] = round(s - l, 2)
        # เทรนด์กลับทิศเมื่อมองยาวขึ้น = หน้าต่างวัด 'ระยะห่างจากปีเริ่ม' อยู่ ไม่ใช่วัดเทรนด์
        if (s < 0) != (l < 0):
            out["flags"].append("TREND_SIGN_FLIPS_ON_LONGER_WINDOW")
        elif abs(out["cagr_gap_pp"]) >= MATERIAL_GAP_PP:
            out["flags"].append("TREND_DIFFERS_MATERIALLY")

    return out


def check_many(tickers: list[str]) -> list[dict]:
    return [check_one(t) for t in tickers]


def concerning(row: dict) -> bool:
    """SHORT_WINDOW ติดกับทุกตัวเสมอ (yfinance ให้ 4 ปีเท่ากันหมด) จึงไม่ใช่สัญญาณอะไร —
    ที่ต้องดูจริงคือหน้าต่างสั้นแล้ว **ให้คำตอบต่างจากประวัติยาว**"""
    return any(f in row["flags"] for f in (
        "TREND_SIGN_FLIPS_ON_LONGER_WINDOW", "TREND_DIFFERS_MATERIALLY",
        "WINDOW_STARTS_AT_CYCLE_HIGH", "WINDOW_STARTS_AT_CYCLE_LOW"))


_FLAG_TH = {
    "SHORT_WINDOW": "หน้าต่างสั้นกว่ารอบ",
    # เกณฑ์คือ 'อยู่ใน 25% บน/ล่างของประวัติเต็ม' ไม่ใช่ 'เป็นจุดสูงสุด/ต่ำสุด' พอดี — ป้ายต้องพูด
    # เท่าที่วัดจริง ไม่งั้นก็เป็นการอ้างเกินตัวเลขแบบเดียวกับที่ eval นี้มีไว้จับ
    "WINDOW_STARTS_AT_CYCLE_HIGH": "เริ่มที่ช่วงสูงของรอบ",
    "WINDOW_STARTS_AT_CYCLE_LOW": "เริ่มที่ช่วงต่ำของรอบ",
    "TREND_SIGN_FLIPS_ON_LONGER_WINDOW": "มองยาวแล้วเทรนด์กลับทิศ",
    "TREND_DIFFERS_MATERIALLY": "มองยาวแล้วเทรนด์ต่างมาก",
    "NO_LONG_HISTORY": "ไม่มีประวัติยาวให้เทียบ",
    "LONG_HISTORY_TOO_OLD": "ประวัติยาวไม่ทับหน้าต่างที่ใช้",
    "NO_OVERLAP_TO_VERIFY": "ไม่มีปีทับกันให้ยืนยัน",
    "HISTORY_HAS_GAP": "ประวัติขาดบางปี",
}


def render_text(rows: list[dict]) -> str:
    lines = [f'{"ticker":8} {"ที่ระบบใช้":>20} {"ประวัติเต็ม":>22}  ธง', "-" * 86]
    for r in rows:
        s, l = r["short"] or {}, r["long"] or {}
        short = f'{s.get("start")}+ {s.get("years", 0)}ปี {s.get("cagr")}%' if s else "-"
        long = f'{l.get("start")}+ {l.get("years", 0)}ปี {l.get("cagr")}%' if l else "-"
        flags = ", ".join(_FLAG_TH.get(f, f) for f in r["flags"]) or "ไม่มี"
        mark = "!" if concerning(r) else " "
        lines.append(f'{mark}{r["ticker"]:7} {short:>20} {long:>22}  {flags}')
    return "\n".join(lines)


if __name__ == "__main__":   # python -m src.evals.check_anchor_window CVX XOM
    import sys

    names = sys.argv[1:] or ["CVX", "XOM", "MSFT"]
    rows = check_many(names)
    print(render_text(rows))
    for r in rows:
        if r["note"]:
            print(f'  {r["ticker"]}: {r["note"]}')
