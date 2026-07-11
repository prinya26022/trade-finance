from src.providers.registry import get_providers
from src.agent.summarize import summarize
from src.evals.check_grounding import check_grounding, check_facts_grounding
from src.evals.check_extraction_accuracy import check_extraction_accuracy
from src.evals.check_xbrl_accuracy import check_xbrl_accuracy
from src.watchlist.store import list_all
from src.history.store import init_db, save_analysis
from src.thesis.store import get_thesis
from src.agent.invalidation import current_breaches
from src.agent.health import compute_health
from src.agent.valuation import reverse_dcf

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

    thesis = get_thesis(ticker)                        # Phase 5: ถ้ามี thesis -> ให้ LLM รู้บริบท
    summary = summarize(price, news, facts, thesis=thesis["thesis"] if thesis else None,
                        asset_type=asset_type)          # crypto ใช้ framework/prompt คนละชุด
    grounding = check_grounding(summary, price, news)
    grounding["facts"] = check_facts_grounding(summary, facts)

    # Phase 4: เช็คว่า 'การคำนวณของเราเอง' แม่นไหม (ไม่เรียก LLM, ไม่กิน quota) — แยกจาก
    # facts grounding ข้างบนที่เช็คว่า LLM พูดตรงกับ Fact ของเราไหม (คนละชั้นของความถูกต้อง)
    # เฉพาะหุ้น: eval นี้เทียบกับ ROE/margin ที่ yfinance คำนวณเอง — crypto ไม่มีเมตริกพวกนี้
    extraction = None
    if asset_type == "stock" and fundamentals_obj is not None:
        try:
            extraction = check_extraction_accuracy(fundamentals_obj, ticker)
        except Exception as e:
            print(f"[warn] extraction accuracy eval failed: {e}")
    grounding["extraction"] = extraction

    # Phase 12: เช็คกับ SEC XBRL (บริษัทยื่นเองตามกฎหมาย) — ground truth ที่อิสระจาก yfinance
    # จริงๆ (ต่างจาก extraction ข้างบนที่เทียบ yfinance กับ yfinance เอง). ยิง EDGAR เพิ่ม (cache
    # 7 วัน) จึงห่อ try/except เหมือนกัน — ล้มแล้วไม่กระทบ pipeline หลัก
    xbrl = None
    if asset_type == "stock" and fundamentals_obj is not None:
        try:
            xbrl = check_xbrl_accuracy(fundamentals_obj, ticker)
        except Exception as e:
            print(f"[warn] xbrl accuracy eval failed: {e}")
    grounding["xbrl"] = xbrl

    # health score (deterministic, ไม่เรียก LLM): ใช้ breaches ของ 'รอบนี้' จาก facts ในมือ
    # ตรงๆ (ไม่ใช่ check_invalidation ที่อ่านจาก DB ซึ่งตอนนี้ยังเป็นแถวของรอบก่อนหน้า)
    breaches = current_breaches(facts, price.price, thesis)
    health = compute_health(summary, breaches)
    grounding["health"] = health

    # Phase 15: reverse-DCF (deterministic, ไม่เรียก LLM) — หุ้นเท่านั้น (ต้องมี FCF/market cap)
    valuation = None
    if asset_type == "stock" and fundamentals_obj is not None:
        try:
            valuation = reverse_dcf(fundamentals_obj)
        except Exception as e:
            print(f"[warn] reverse-dcf failed: {e}")
    grounding["valuation"] = valuation

    if persist:
        init_db()                                        # idempotent: สร้างตาราง/เพิ่มคอลัมน์ถ้ายังไม่มี
        save_analysis(summary, grounding, facts, extraction, health, xbrl, valuation)  # เก็บ Summary + facts + evals + health + valuation
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
        xbrl = grounding.get("xbrl") or {}
        xbrl_acc = xbrl.get("accuracy")
        xbrl_str = f"{xbrl_acc:.0%}" if xbrl_acc is not None else "N/A"
        health = grounding.get("health") or {}
        valuation = grounding.get("valuation") or {}
        implied = valuation.get("implied_growth")
        implied_str = f"{implied:.1f}%" if implied is not None else "N/A"
        print(
            f"{ticker:6} | {summary.fundamental_strength:6}/{summary.valuation_view:9} | "
            f"conf {summary.confidence} | price_ok={grounding['price_ok']} "
            f"news={grounding['news_grounded_ratio']:.0%} "
            f"facts={grounding['facts']['facts_grounded_ratio']:.0%} "
            f"extract={acc_str} xbrl={xbrl_str} health={health.get('score', 'N/A')} "
            f"implied_growth={implied_str}"
        )