from src.providers.registry import get_providers
from src.agent.summarize import summarize
from src.evals.check_grounding import check_grounding, check_facts_grounding
from src.watchlist.store import list_all
from src.history.store import init_db, save_analysis

def analyze(ticker: str, asset_type: str = "stock", persist: bool = True):
    bundle = get_providers(asset_type)

    try:
        price = bundle.price.get_price(ticker)
    except Exception as e:
        print(f"[error] price failed for {ticker}: {e}")
        return None
    try:
        news = bundle.news.get_news(ticker, limit=5)
    except Exception as e:
        news = []
        print(f"[warn] news failed: {e}")
    try:
        facts = bundle.fundamentals.get_fundamentals(ticker).to_facts()
    except Exception as e:
        facts = []
        print(f"[warn] fundamentals failed: {e}")

    summary = summarize(price, news, facts)
    grounding = check_grounding(summary, price, news)
    grounding["facts"] = check_facts_grounding(summary, facts)

    if persist:
        init_db()                              # idempotent: สร้างตารางถ้ายังไม่มี
        save_analysis(summary, grounding)      # เก็บลง history เพื่อให้ UI/Phase 3 ใช้
    return summary, grounding

def run_watchlist():
    for row in list_all():
        ticker, asset_type = row["ticker"], row["asset_type"]
        try:
            result = analyze(ticker, asset_type)
        except Exception as e:            # ← กันไว้: 1 ตัวพัง อย่าให้ทั้ง loop ตาย
            print(f"{ticker}: error - {e}")
            continue
        if result is None:                # price ล้ม (fatal)
            print(f"{ticker}: skipped (no price)")
            continue
        summary, grounding = result
        print(
            f"{ticker:6} | {summary.fundamental_strength:6}/{summary.valuation_view:9} | "
            f"conf {summary.confidence} | price_ok={grounding['price_ok']} "
            f"news={grounding['news_grounded_ratio']:.0%} "
            f"facts={grounding['facts']['facts_grounded_ratio']:.0%}"
        )