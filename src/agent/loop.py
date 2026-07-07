from src.providers.registry import get_providers
from src.agent.summarize import summarize
from src.evals.check_grounding import check_grounding, check_facts_grounding
from src.evals.check_extraction_accuracy import check_extraction_accuracy
from src.watchlist.store import list_all
from src.history.store import init_db, save_analysis

def analyze(ticker: str, asset_type: str = "stock", persist: bool = True):
    bundle = get_providers(asset_type)

    try:
        price = bundle.price.get_price(ticker)
    except Exception as e:
        print(f"[error] price failed for {ticker}: {e}")
        return None
    if price is None or price.price is None:   # ticker ไม่ถูกต้อง/delisted -> yfinance คืน None ไม่ raise
        print(f"[error] no price data for {ticker} (invalid or delisted ticker?)")
        return None                            # ตกที่ stop condition -> ไม่ไปเปลือง Gemini
    try:
        news = bundle.news.get_news(ticker, limit=5)
    except Exception as e:
        news = []
        print(f"[warn] news failed: {e}")
    try:
        fundamentals_obj = bundle.fundamentals.get_fundamentals(ticker)
        facts = fundamentals_obj.to_facts()
    except Exception as e:
        fundamentals_obj = None
        facts = []
        print(f"[warn] fundamentals failed: {e}")

    summary = summarize(price, news, facts)
    grounding = check_grounding(summary, price, news)
    grounding["facts"] = check_facts_grounding(summary, facts)

    # Phase 4: เช็คว่า 'การคำนวณของเราเอง' แม่นไหม (ไม่เรียก LLM, ไม่กิน quota) — แยกจาก
    # facts grounding ข้างบนที่เช็คว่า LLM พูดตรงกับ Fact ของเราไหม (คนละชั้นของความถูกต้อง)
    extraction = None
    if fundamentals_obj is not None:
        try:
            extraction = check_extraction_accuracy(fundamentals_obj, ticker)
        except Exception as e:
            print(f"[warn] extraction accuracy eval failed: {e}")
    grounding["extraction"] = extraction

    if persist:
        init_db()                                        # idempotent: สร้างตาราง/เพิ่มคอลัมน์ถ้ายังไม่มี
        save_analysis(summary, grounding, facts, extraction)  # เก็บ Summary + facts + extraction eval
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
        extraction = grounding.get("extraction") or {}
        acc = extraction.get("accuracy")
        acc_str = f"{acc:.0%}" if acc is not None else "N/A"
        print(
            f"{ticker:6} | {summary.fundamental_strength:6}/{summary.valuation_view:9} | "
            f"conf {summary.confidence} | price_ok={grounding['price_ok']} "
            f"news={grounding['news_grounded_ratio']:.0%} "
            f"facts={grounding['facts']['facts_grounded_ratio']:.0%} "
            f"extract={acc_str}"
        )