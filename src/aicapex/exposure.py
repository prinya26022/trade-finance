"""Phase 50 — ผูกเรดาร์เข้ากับของที่ถือจริง.

เรดาร์ (Phase 49) ตอบว่า "ห่วงโซ่การเงิน AI ตึงแค่ไหน" ซึ่งเป็นคำถามเกี่ยวกับ**โลก**
ไฟล์นี้ตอบคำถามถัดไปที่เปลี่ยนการตัดสินใจจริง: **"แล้วมันเกี่ยวอะไรกับเงินของฉัน"**

──────────────────────────────────────────────────────────────────────────────
**คำเตือนที่ต้องอ่านก่อนใช้ตัวเลขในไฟล์นี้**

การจัดว่า ticker ไหนอยู่ตรงไหนของห่วงโซ่ **เป็นการตัดสินใจเชิงความเห็น ไม่ใช่ข้อเท็จจริง
ที่ดึงมาจากงบได้** ถ้าปล่อยให้มันซ่อนอยู่ในโค้ด ผลลัพธ์จะเป็นตารางที่ดูน่าเชื่อแต่เถียงไม่ได้
ซึ่งแย่กว่าไม่มีตาราง (หลักเดียวกับ Phase 48 ที่เอาเส้น 15pp ออกมาให้เห็น)

จึงแยกสองอย่างนี้ออกจากกันชัดๆ:
- `measured` = **ข้อเท็จจริง** ตรวจได้ด้วยการเช็คว่าอยู่ใน universe ของเรดาร์หรือไม่
  (งบของมันเป็นวัตถุดิบของสัญญาณจริงๆ) ไม่มีการตีความ
- ที่เหลือ = **ความเห็นของเรา** ทุกตัวต้องมีเหตุผลกำกับเป็นประโยค และเหตุผลนั้นเดินทาง
  ไปกับผลลัพธ์เสมอ เพื่อให้เถียงได้ทีละตัว
──────────────────────────────────────────────────────────────────────────────

**ทิศทางสำคัญกว่าขนาด:** ถ้า capex ของ hyperscaler หด ห่วงโซ่นี้ไม่ได้เจ็บทางเดียวกันหมด
ฝั่งที่ *ขายของให้* การก่อสร้างจะรายได้หาย ส่วนฝั่งที่ *จ่ายค่าคอมพิวต์* จะต้นทุนถูกลง
การนับรวมเป็น "% ที่เกี่ยวข้องกับ AI" ก้อนเดียวจึงกลบข้อมูลที่สำคัญที่สุดทิ้ง
"""
from src.aicapex.universe import ALL, BENCHMARKS, LAYER_LABEL, LAYER_OF

# ── ระดับความเกี่ยวข้อง เรียงตามทิศทางที่ได้รับผลเมื่อ capex หด ────────────────
MEASURED = "measured"          # งบของมันเป็นวัตถุดิบของสัญญาณเรดาร์โดยตรง (ข้อเท็จจริง)
SELLS_INTO = "sells_into"      # ขายของให้การก่อสร้าง — capex หด = รายได้หาย (ความเห็น)
BUYS_FROM = "buys_from"        # จ่ายค่าคอมพิวต์ — capex หด = ต้นทุนถูกลง (ความเห็น)
UNRELATED = "unrelated"        # ไม่มีกลไกเชื่อมที่ชัดเจน (ความเห็น)
UNCLASSIFIED = "unclassified"  # ยังไม่เคยจัด — **ห้ามตกไปเป็น UNRELATED เงียบๆ**

LEVEL_LABEL = {
    MEASURED: "เรดาร์วัดตัวนี้โดยตรง",
    SELLS_INTO: "ขายของให้การก่อสร้าง",
    BUYS_FROM: "เป็นผู้จ่ายค่าคอมพิวต์",
    UNRELATED: "ไม่มีกลไกเชื่อมชัดเจน",
    UNCLASSIFIED: "ยังไม่ได้จัดกลุ่ม",
}

# ทิศทางที่ได้รับผลถ้า capex ของ hyperscaler หดตัว
DIRECTION = {MEASURED: "hurt", SELLS_INTO: "hurt", BUYS_FROM: "helped",
             UNRELATED: "none", UNCLASSIFIED: "unknown"}

# ── ความเห็นของเรา เขียนไว้ให้เถียงได้ ─────────────────────────────────────────
#
# ticker ที่อยู่ใน universe ของเรดาร์อยู่แล้วไม่ต้องมีในนี้ — มันเป็น `measured` โดยอัตโนมัติ
# จากการเช็คสมาชิก ไม่ใช่จากการตัดสินใจของเรา
JUDGEMENTS: dict[str, tuple[str, str]] = {
    "ASML": (SELLS_INTO,
             "ขายเครื่องพิมพ์ลายวงจรให้โรงงานที่ผลิตชิป AI — capex หดจะมาถึงช้ากว่าคนอื่น "
             "เพราะคำสั่งซื้อเครื่องจองล่วงหน้าหลายไตรมาส แต่มาถึงแน่"),
    "ADBE": (BUYS_FROM,
             "ซื้อกำลังประมวลผลไปรันฟีเจอร์ AI ของตัวเอง ไม่ได้ขายให้ใคร — คอมพิวต์ถูกลง "
             "คือต้นทุนถูกลง. ความเสี่ยง AI ของมันคือ 'ถูกแทนที่' ไม่ใช่ 'capex หด'"),
    "DUOL": (BUYS_FROM,
             "เหมือน ADBE: เป็นลูกค้าของคอมพิวต์ ไม่ใช่ผู้ขาย — ราคา GPU ถูกลงช่วยอัตรากำไร"),
    "TSLA": (BUYS_FROM,
             "สร้างคลัสเตอร์เทรนของตัวเองด้วยการ *ซื้อ* ชิป — เป็นผู้จ่าย ไม่ใช่ผู้รับเงิน "
             "(ราคาหุ้นมักวิ่งตามธีม AI ซึ่งเป็นอารมณ์ตลาด ไม่ใช่กลไกรายได้)"),
    "AAPL": (UNRELATED,
             "รายได้มาจากฮาร์ดแวร์ผู้บริโภค — ไม่ได้ขายกำลังประมวลผล และ capex ด้าน AI "
             "ยังเล็กเทียบขนาดบริษัทจนไม่ขยับงบ"),
    "MA": (UNRELATED, "รายได้ผูกกับปริมาณการใช้จ่ายของผู้บริโภค ไม่ใช่การสร้าง datacenter"),
    "JPM": (UNRELATED,
            "ถ้าสินเชื่อที่ค้ำด้วย GPU พังจริง ธนาคารจะโดนผ่านตลาดเครดิต — แต่เป็นผลทางอ้อม "
            "ที่ประเมินขนาดไม่ได้จากข้อมูลที่เรามี จึงไม่นับเป็นความเกี่ยวข้องโดยตรง"),
    "CVX": (UNRELATED, "น้ำมันและก๊าซ — ความต้องการไฟของ datacenter กระทบผ่านราคาก๊าซได้ "
                       "แต่เล็กมากเทียบกับตัวขับหลักคือราคาน้ำมันโลก"),
    "SBUX": (UNRELATED, "ร้านกาแฟ"),
    "BTC": (UNRELATED,
            "เคยแชร์ห่วงโซ่ GPU สมัยขุดด้วยการ์ดจอ แต่ตอนนี้ขุดด้วย ASIC คนละสายการผลิต"),
}


def classify(ticker: str) -> dict:
    """คืนระดับความเกี่ยวข้อง + เหตุผล + ว่าเป็นข้อเท็จจริงหรือความเห็น.

    ticker ที่ไม่เคยจัด -> UNCLASSIFIED **ไม่ใช่ UNRELATED** เพราะ 'ยังไม่ได้ดู' กับ
    'ดูแล้วไม่เกี่ยว' เป็นคนละคำกล่าวอ้าง — ถ้าปนกัน วันที่เพิ่ม ticker ใหม่เข้า watchlist
    แล้วลืมจัดกลุ่ม มันจะขึ้นว่า 'ปลอดภัย' เงียบๆ ซึ่งเป็นโหมดพังที่มองไม่เห็น
    """
    t = ticker.upper()
    if t in ALL and t not in BENCHMARKS:
        layer = LAYER_OF[t]
        return {"ticker": t, "level": MEASURED, "objective": True, "layer": layer,
                "reason": f"อยู่ใน universe ของเรดาร์ กลุ่ม “{LAYER_LABEL[layer]}” — "
                          f"งบของมันเป็นวัตถุดิบของสัญญาณโดยตรง",
                "direction": DIRECTION[MEASURED]}
    if t in JUDGEMENTS:
        level, reason = JUDGEMENTS[t]
        return {"ticker": t, "level": level, "objective": False, "layer": None,
                "reason": reason, "direction": DIRECTION[level]}
    return {"ticker": t, "level": UNCLASSIFIED, "objective": False, "layer": None,
            "reason": "ยังไม่เคยจัดกลุ่มตัวนี้ — ไม่ใช่ว่าไม่เกี่ยว แต่คือยังไม่ได้ดู",
            "direction": DIRECTION[UNCLASSIFIED]}


def _bucket(rows: list[dict], key: str = "weight") -> dict[str, float]:
    """รวมน้ำหนักตามระดับ — ตัวที่ไม่รู้น้ำหนัก (ไม่ได้ใส่จำนวนหุ้น) ไม่ถูกนับเป็น 0
    แต่ถูกนับแยกไว้ใน unknown_weight เพราะ 'ไม่รู้' ไม่เท่ากับ 'ไม่มี'"""
    out: dict[str, float] = {}
    for r in rows:
        w = r.get(key)
        if w is None:
            continue
        out[r["level"]] = round(out.get(r["level"], 0.0) + w, 1)
    return out


def build_exposure(portfolio: dict, watchlist: list[dict]) -> dict:
    """ผูกเรดาร์เข้ากับพอร์ต. `portfolio` = ผลจาก performance.portfolio_edge(),
    `watchlist` = แถวจาก watchlist.store.list_all(). ไม่แตะเน็ต ไม่แตะ DB เอง
    (ฉีดเข้ามาทั้งคู่ เพื่อให้เทสต์ออฟไลน์ได้ — แพตเทิร์นเดียวกับ build_board(rows=...))"""
    positions = portfolio.get("positions") or []
    total_value = portfolio.get("total_value")

    held = []
    for p in positions:
        c = classify(p["ticker"])
        held.append({**c, "weight": p.get("weight"), "market_value": p.get("market_value")})

    watched = []
    for w in watchlist:
        if w.get("status") == "holding":
            continue      # อยู่ในฝั่งถือแล้ว ไม่นับซ้ำ
        c = classify(w["ticker"])
        watched.append({**c, "status": w.get("status")})

    held_buckets = _bucket(held)
    hurt = round(held_buckets.get(MEASURED, 0.0) + held_buckets.get(SELLS_INTO, 0.0), 1)
    helped = round(held_buckets.get(BUYS_FROM, 0.0), 1)
    unknown_weight = round(held_buckets.get(UNCLASSIFIED, 0.0), 1)
    no_weight = [r["ticker"] for r in held if r.get("weight") is None]

    counts: dict[str, int] = {}
    for r in held + watched:
        counts[r["level"]] = counts.get(r["level"], 0) + 1

    return {
        "holdings": {
            "total_value": total_value,
            # % ของพอร์ตที่ **เสียหาย** ถ้า capex หด — ไม่ใช่ "% ที่เกี่ยวกับ AI"
            # เพราะการรวมสองทิศทางเข้าด้วยกันกลบข้อมูลที่สำคัญที่สุดทิ้ง
            "hurt_pct": hurt,
            "helped_pct": helped,
            "unclassified_pct": unknown_weight,
            "positions_without_weight": no_weight,
            "rows": sorted(held, key=lambda r: -(r.get("weight") or 0)),
        },
        "watchlist": {"rows": watched},
        "counts": counts,
        "caveats": [
            "ระดับความเกี่ยวข้องของทุกตัวที่ไม่ใช่ “เรดาร์วัดตัวนี้โดยตรง” เป็นความเห็นของเรา "
            "ไม่ใช่ตัวเลขจากงบ — เหตุผลกำกับไว้ทุกตัวเพื่อให้เถียงได้ทีละตัว",
            "นี่คือ “ทิศทางที่จะได้รับผล” ไม่ใช่ “จะเสียเงินเท่าไร” — ขนาดของผลกระทบต้องใช้ "
            "สัดส่วนรายได้ที่มาจากลูกค้ากลุ่ม hyperscaler ซึ่งอยู่ใน 10-K ไม่ใช่ yfinance",
            "ฝั่งที่ได้ประโยชน์ได้ประโยชน์ทาง **ต้นทุน** เท่านั้น — ราคาหุ้นอาจลงตามอารมณ์ "
            "ตลาดพร้อมกันหมดอยู่ดี ซึ่งเป็นคนละเรื่องกับกลไกรายได้",
        ],
    }
