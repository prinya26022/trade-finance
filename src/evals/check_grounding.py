import re


def _extract_numbers(text: str) -> list[float]:
    """ดึงตัวเลขที่ LLM อ้างจากข้อความ (รองรับคอมมา/ทศนิยม), ตัดปีงบ FYxxxx ทิ้งก่อน."""
    text = re.sub(r"FY\d{4}", " ", text)         # 'FY2025' ไม่ใช่เมตริก
    out = []
    for token in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return out


def check_facts_grounding(summary, facts, rel_tol: float = 0.02) -> dict:
    """แก่น Phase 2: ตัวเลขที่ LLM อ้างในคำวินิจฉัยพื้นฐาน ตรงกับ Fact จริงไหม (กันมั่วตัวเลขงบ).
    เทียบทุกตัวเลขที่อ้าง กับค่าของ Fact จริง (relative tolerance).
    ตัวที่ไม่ match มักเป็น 'เกณฑ์เทียบ' (เช่น 1.0, 3x) ไม่ใช่การมั่ว — จึงคืน list มาให้คนดูเอง."""
    real_values = [f.value for f in facts]

    cited_texts = list(summary.strength_reasons) + [w.detail for w in summary.weak_points]
    cited_numbers = [n for t in cited_texts for n in _extract_numbers(t)]

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= rel_tol * abs(b) if b else a == 0

    def matches_a_fact(n: float) -> bool:
        # เทียบตรง ๆ และเผื่อ LLM เขียนแบบย่อหน่วย ("16.33 billion" = 16.33e9)
        candidates = [n, n * 1e3, n * 1e6, n * 1e9]
        return any(close(c, v) for c in candidates for v in real_values)

    grounded = [n for n in cited_numbers if matches_a_fact(n)]
    unmatched = [n for n in cited_numbers if not matches_a_fact(n)]
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