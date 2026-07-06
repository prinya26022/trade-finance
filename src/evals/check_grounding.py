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