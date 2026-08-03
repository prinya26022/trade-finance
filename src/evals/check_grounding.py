import re

# ── fix 2026-08: eval นี้ถูกใช้เป็น 'คะแนนความแม่น' ในการเทียบสองโมเดล แล้วพบว่ามันวัด
# **สไตล์การเขียนตัวเลข** ปนเข้ามาด้วย ซึ่งทำให้ข้อสรุปว่า 'ใครแม่นกว่า' เชื่อไม่ได้เต็มปาก:
#
#   (1) หน่วยไทย — โมเดลเขียน "2.69 หมื่นล้าน USD" ซึ่งตรงกับ Fact 26,974,000,000 เป๊ะ
#       แต่เดิมนับเป็น 'ไม่ตรง' เพราะ matches_a_fact ลองคูณแค่ 1e3/1e6/1e9 (ไม่มี 1e10)
#       -> NVDA รอบ 2026-08-02 ได้ 50% ทั้งที่ทุกตัวเลขถูกต้อง
#   (2) วันที่/ชื่อแบบฟอร์ม — "8-K วันที่ 2026-06-10" กลายเป็นเลข 8, 2026, -6, -10 ที่ไม่ตรง
#       กับ Fact ไหนเลย ทั้งที่ไม่ใช่การอ้างเมตริก (หลักเดียวกับที่ตัด FY2025 ทิ้งอยู่แล้ว)
#
# ทั้งสองข้อทำให้ ratio ต่ำกว่าความจริงแบบไม่สมมาตร (ลงโทษคนเขียนเลขแบบอ่านง่าย) — เครื่องวัด
# ต้องเที่ยงก่อนถึงจะเอาไปตัดสินว่าใครแม่นกว่าได้
_NOISE_RE = re.compile(
    r"FY\d{4}"                  # ปีงบ 'FY2025'
    r"|\d{4}-\d{2}-\d{2}"       # วันที่ ISO '2026-06-10' (ในพาดหัว 8-K)
    r"|\b\d{1,2}-[KQ]\b"        # ชื่อแบบฟอร์ม SEC '8-K', '10-K', '10-Q'
)

# เรียงยาว -> สั้นตอนประกอบ regex สำคัญมาก: ถ้า 'ล้าน' มาก่อน 'พันล้าน' คำว่า "3.8 พันล้าน"
# จะจับได้แค่ 'พัน' แล้วคูณผิดหลักไปพันเท่า
_SCALES = {
    "ล้านล้าน": 1e12, "แสนล้าน": 1e11, "หมื่นล้าน": 1e10, "พันล้าน": 1e9,
    "ล้าน": 1e6, "แสน": 1e5, "หมื่น": 1e4, "พัน": 1e3,
    "trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
}
_NUMBER_RE = re.compile(
    r"(-?\d[\d,]*\.?\d*)\s*(" + "|".join(sorted(_SCALES, key=len, reverse=True)) + r")?",
    re.IGNORECASE,
)

# ตัวคูณที่ลองให้กับเลข 'เปล่าๆ' (ไม่มีหน่วยกำกับ) — เผื่อโมเดลเขียนย่อหน่วยโดยไม่บอกหน่วย
_BARE_MULTIPLIERS = (1.0, 1e3, 1e6, 1e9)


def _extract_numbers(text: str) -> list[float]:
    """ตัวเลขที่ LLM อ้าง (คืนค่าที่คูณหน่วยแล้ว) — ใช้ในเทสต์/ตรวจสอบด้วยมือ."""
    return [value for value, _ in _cited_values(text)]


def _cited_values(text: str) -> list[tuple[float, bool]]:
    """(ค่า, มีหน่วยกำกับชัดเจนไหม) — ตัวที่ระบุหน่วยมาแล้วไม่ต้องเดาหลักซ้ำอีก
    (ไม่งั้น '2.69 หมื่นล้าน' จะไปแมตช์ Fact ที่ห่างกันพันเท่าได้ฟรีๆ = ตรวจหลวมเกิน)."""
    text = _NOISE_RE.sub(" ", text)
    out: list[tuple[float, bool]] = []
    for token, scale_word in _NUMBER_RE.findall(text):
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        if scale_word:
            out.append((value * _SCALES[scale_word.lower()], True))
        else:
            out.append((value, False))
    return out


def check_facts_grounding(summary, facts, rel_tol: float = 0.02) -> dict:
    """แก่น Phase 2: ตัวเลขที่ LLM อ้างในคำวินิจฉัยพื้นฐาน ตรงกับ Fact จริงไหม (กันมั่วตัวเลขงบ).
    เทียบทุกตัวเลขที่อ้าง กับค่าของ Fact จริง (relative tolerance).
    ตัวที่ไม่ match มักเป็น 'เกณฑ์เทียบ' (เช่น 1.0, 3x) ไม่ใช่การมั่ว — จึงคืน list มาให้คนดูเอง."""
    real_values = [f.value for f in facts]

    cited_texts = list(summary.strength_reasons) + [w.detail for w in summary.weak_points]
    cited = [pair for t in cited_texts for pair in _cited_values(t)]

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= rel_tol * abs(b) if b else a == 0

    def matches_a_fact(n: float, has_scale: bool) -> bool:
        # มีหน่วยกำกับแล้ว (เช่น "2.69 หมื่นล้าน") = รู้หลักแน่นอน เทียบตรงๆ พอ
        # ไม่มีหน่วย = เผื่อ LLM เขียนย่อหน่วยโดยไม่บอก ("16.33" ที่หมายถึง 16.33e9)
        candidates = [n] if has_scale else [n * m for m in _BARE_MULTIPLIERS]
        return any(close(c, v) for c in candidates for v in real_values)

    grounded = [n for n, s in cited if matches_a_fact(n, s)]
    unmatched = [n for n, s in cited if not matches_a_fact(n, s)]
    cited_numbers = [n for n, _ in cited]
    ratio = len(grounded) / len(cited_numbers) if cited_numbers else 1.0

    return {
        "facts_grounded_ratio": ratio,     # สัดส่วนตัวเลขที่อ้างแล้วเจอใน Fact จริง
        "cited_count": len(cited_numbers),
        "unmatched_numbers": unmatched,    # ตรวจตาเอง: benchmark หรือมั่ว?
    }


def check_grounding(summary, price, news) -> dict:
    # เช็ค 1: ราคา
    price_ok = abs(summary.price - price.price) / price.price < 0.01

    # เช็ค 2: ข่าว — key_news กี่อันที่ match ข่าวจริง
    real_titles = [n.title for n in news]
    grounded = sum(
    any(t.lower() in kn.lower() or kn.lower() in t.lower() for t in real_titles)
    for kn in summary.key_news
    )
    news_score = grounded / len(summary.key_news) if summary.key_news else 0.0

    return {
        "price_ok": price_ok,
        "news_grounded_ratio": news_score,
        "price_reported": summary.price,
        "price_real": price.price,
        "key_news_count": len(summary.key_news),
    }