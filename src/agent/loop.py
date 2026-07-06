from src.providers.registry import get_providers
from src.agent.summarize import summarize
from src.evals.check_grounding import check_grounding
from src.watchlist.store import list_all

def analyze(ticker: str, asset_type: str = "stock"):
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
            f"{ticker:6} | {summary.sentiment:8} | conf {summary.confidence} | "
            f"price_ok={grounding['price_ok']} news={grounding['news_grounded_ratio']:.0%}"
        )