"""Read-only API over the analysis history (FastAPI).

ส่วนใหญ่แค่ "อ่าน" — การวิเคราะห์รายวัน (เรียก Gemini) เกิดใน agent loop แยกต่างหาก endpoint พวกนี้
ไม่แตะ LLM เลย จึงไม่กิน quota. ข้อยกเว้นเดียวคือ POST /api/chat (Phase 25) ซึ่งยิง Gemini จริงตาม
ที่ผู้ใช้กดถามเอง (ไม่มี auto-trigger ที่ไหนเรียกมัน) — ดู docstring ของ endpoint นั้นโดยเฉพาะ.
Next.js dashboard จะ fetch จากที่นี่.

รัน:  uvicorn src.api.main:app --reload
ดู docs อัตโนมัติที่  http://localhost:8000/docs
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.history.store import init_db, latest_per_ticker, history, health_trends
from src.watchlist.store import (
    list_all, add as add_ticker, remove as remove_ticker,
    set_holding, add_shares, set_watching, set_frozen,
)
from src.agent.changes import detect_changes
from src.agent.performance import portfolio_edge
from src.agent.investigate_store import latest_investigation
from src.agent import investigate_runner
from src.agent.timeline import build_timeline
from src.agent.timeline_store import get_narrative
from src.agent.screener import screen
from src.agent.chat import ask as ask_chat
from src.agent.invalidation import check_invalidation
from src.macro.radar import dashboard as macro_dashboard
from src.macro.geonews import fetch_geopolitical
from src.macro.altseason import eth_btc_momentum
from src.thesis.store import get_thesis, set_thesis, delete_thesis
from src.decisions.store import log_decision, list_decisions

app = FastAPI(title="Investment Research Agent API")

# อนุญาตให้ Next.js dev server เรียกข้าม origin ได้ — ใช้ regex แทนพอร์ตตายตัว 3000 เพราะ
# `next dev` auto-bump ไปพอร์ตอื่น (3001, 3002, ...) เองถ้า 3000 ถูกใช้อยู่แล้ว (เช่น เครื่องที่มี
# dev server อื่นค้างอยู่) — เจอจริง: origin ไม่ตรง allow_origins แบบเป๊ะๆ ทำให้ preflight (OPTIONS)
# โดน Starlette ตอบ 400 "Disallowed CORS origin" ก่อนคำขอจริงจะถูกส่งไปด้วยซ้ำ
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


class WatchlistAdd(BaseModel):
    ticker: str
    asset_type: str = "stock"


class HoldingSet(BaseModel):
    entry_price: float
    entry_date: str | None = None   # ISO YYYY-MM-DD; None -> วันนี้
    shares: float | None = None


class SharesAdd(BaseModel):
    price: float
    shares: float


class ChatTurn(BaseModel):
    role: str    # "user" | "assistant"
    text: str


class ChatAsk(BaseModel):
    question: str
    history: list[ChatTurn] = []   # เทิร์นก่อนหน้าในสนทนาเดียวกัน (session ฝั่ง frontend เก็บไว้)


class InvalidationRule(BaseModel):
    metric: str
    op: str
    value: float
    note: str = ""


class ThesisSet(BaseModel):
    thesis: str
    invalidation: list[InvalidationRule] = []
    fair_value: float | None = None


class InvestigateStart(BaseModel):
    focus: str = ""   # โจทย์เพิ่มเติมจากผู้ใช้ เช่น "ทำไม margin ตก" -> ต่อท้ายเป็น context ของ prompt


class DecisionCreate(BaseModel):
    action: str          # buy | pass | wait | sell | trim
    gate2: str = "n/a"   # ready | not_ready | n/a  -- ผลเช็คกราฟ/EW ณ ตอนตัดสินใจ (นอกระบบนี้)
    gate2_note: str = ""
    reason: str = ""
    conviction: int | None = None   # 1-5


@app.on_event("startup")
def _startup() -> None:
    init_db()   # กัน error ถ้ายังไม่เคยรัน agent (ตารางยังไม่ถูกสร้าง)


@app.get("/api/watchlist")
def get_watchlist():
    """รายการ ticker ที่จับตา (ticker + asset_type)."""
    return [dict(row) for row in list_all()]


@app.post("/api/watchlist", status_code=201)
def post_watchlist(item: WatchlistAdd):
    """เพิ่ม ticker เข้า watchlist — ตั้งใจไม่วิเคราะห์ทันที (ไม่กินโควตา LLM);
    ปล่อยให้ daily run (Phase 3) หรือ run_watchlist วิเคราะห์ให้เอง."""
    ticker = item.ticker.strip().upper()
    if not ticker.isalnum():                       # กันช่องว่าง/อักขระแปลก (เบื้องต้น)
        raise HTTPException(status_code=400, detail="ticker must be alphanumeric")
    add_ticker(ticker, item.asset_type)            # INSERT OR IGNORE -> เพิ่มซ้ำไม่ error
    return {"ticker": ticker, "asset_type": item.asset_type}


@app.delete("/api/watchlist/{ticker}")
def delete_watchlist(ticker: str):
    """เอา ticker ออกจาก watchlist (ประวัติ analyses เดิมยังอยู่)."""
    remove_ticker(ticker)
    return {"removed": ticker.upper()}


# ---- holding management (แทน CLI: hold / add / watch) — ไม่เรียก LLM ----

@app.put("/api/watchlist/{ticker}/holding")
def put_holding(ticker: str, body: HoldingSet):
    """ตั้ง/แก้ position ที่ถืออยู่ (entry_price/date/shares) — upsert เข้า watchlist ให้ถ้ายังไม่มี."""
    set_holding(ticker.upper(), body.entry_price, body.entry_date, body.shares)
    return dict(next(r for r in list_all() if r["ticker"] == ticker.upper()))


@app.post("/api/watchlist/{ticker}/holding/add")
def post_add_shares(ticker: str, body: SharesAdd):
    """ซื้อเพิ่ม -> เฉลี่ย entry_price อัตโนมัติ (weighted average). 400 ถ้ายังไม่ใช่ holding."""
    try:
        return add_shares(ticker.upper(), body.price, body.shares)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/watchlist/{ticker}/holding")
def delete_holding(ticker: str):
    """ขายออก/เลิกถือ -> กลับเป็น 'watching' (เก็บ entry เดิมไว้ดูประวัติ, ยังอยู่ใน watchlist)."""
    set_watching(ticker.upper())
    return {"ticker": ticker.upper(), "status": "watching"}


@app.put("/api/watchlist/{ticker}/freeze")
def put_freeze(ticker: str):
    """แช่แข็ง — ขายหมดแล้วแต่อยากดูว่าฟื้นไหม โดยไม่เปลืองโควตา Gemini รายวัน (analyze() จะ
    ข้าม ticker นี้เว้นแต่เกิน 30 วันนับจากวิเคราะห์ครั้งล่าสุด ดู src/agent/loop.py)."""
    set_frozen(ticker.upper())
    return {"ticker": ticker.upper(), "status": "frozen"}


@app.delete("/api/watchlist/{ticker}/freeze")
def delete_freeze(ticker: str):
    """ยกเลิกแช่แข็ง -> กลับเป็น 'watching' (วิเคราะห์รายวันเหมือนเดิม)."""
    set_watching(ticker.upper())
    return {"ticker": ticker.upper(), "status": "watching"}


@app.get("/api/analyses")
def get_analyses():
    """ผลวิเคราะห์ล่าสุดของแต่ละ ticker — มุมมองหลักของ dashboard."""
    return latest_per_ticker()


@app.get("/api/analyses/{ticker}")
def get_ticker_history(ticker: str, limit: int = 50):
    """ประวัติการวิเคราะห์ของ ticker เดียว (ไว้ทำ timeline/trend)."""
    rows = history(ticker, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no analyses for {ticker}")
    return rows


@app.get("/api/health-trends")
def get_health_trends(limit: int = 20):
    """Phase 23 — แนวโน้ม health score N จุดล่าสุด/ticker (เบากว่า /api/analyses/{ticker} มาก
    เพราะไม่ parse summary/facts) ไว้วาด sparkline ในการ์ด/ตาราง. ticker ที่ไม่มี key เลย = ยังไม่มี
    รอบวิเคราะห์ที่คำนวณ health ได้ (แถวเก่า/excluded) — frontend แสดงไม่ได้ก็แค่ไม่วาด sparkline."""
    return health_trends(limit_per_ticker=limit)


@app.get("/api/portfolio")
def get_portfolio():
    """สรุปเฉพาะโพซิชันที่ 'ถืออยู่จริง' — ผลตอบแทน vs benchmark ตั้งแต่วันซื้อ (Phase 5.5).
    ไม่เรียก LLM (ใช้แค่ราคาย้อนหลัง yfinance). positions ว่าง = ยังไม่มี holding."""
    return portfolio_edge()


@app.get("/api/changes")
def get_changes():
    """สิ่งที่เปลี่ยนตั้งแต่ครั้งก่อนของแต่ละ ticker (Phase 3 — ไม่เรียก LLM)."""
    tickers = [row["ticker"] for row in latest_per_ticker()]
    return [detect_changes(t) for t in tickers]


@app.get("/api/changes/{ticker}")
def get_ticker_changes(ticker: str):
    return detect_changes(ticker.upper())


@app.get("/api/timeline/{ticker}")
def get_timeline(ticker: str):
    """Phase 14 — ชีวประวัติบริษัท: เหตุการณ์ material หลายปี (deterministic, ไม่เรียก LLM จึง
    คำนวณสดตอน render ได้) + 'เรื่องเล่า' ที่ narrate ไว้ (ถ้ามี — null ถ้ายังไม่เคย narrate)."""
    events = build_timeline(ticker.upper())
    narrative = get_narrative(ticker.upper())
    return {"ticker": ticker.upper(), "events": events,
            "narrative": narrative["narrative"] if narrative else None}


@app.get("/api/investigation/{ticker}")
def get_investigation(ticker: str):
    """transcript การสืบล่าสุดของ agent (Phase 13) — 404 ถ้ายังไม่เคยสืบ ticker นี้.
    read-only: ไม่ trigger การสืบใหม่ (นั่นยิง Gemini — ต้องกดสั่งเองผ่าน POST ข้างล่าง)."""
    inv = latest_investigation(ticker.upper())
    if inv is None:
        raise HTTPException(status_code=404, detail=f"no investigation for {ticker}")
    return inv


# ---- Phase 28: สั่งสืบจากหน้าเว็บ ----
# agentic loop (Phase 13) เขียนเสร็จมานาน แต่ยิงได้จาก CLI อย่างเดียว (`python -m src.agent.investigate`)
# หน้าเว็บอ่านได้แค่ transcript เก่า -> "agent จริง" ของโปรเจกต์ใช้งานไม่ได้จากตัวโปรดักต์เอง.
# แยกเป็น POST (สั่ง, คืน 202 ทันที) + GET status (poll) เพราะการสืบกินเวลาระดับสิบวินาที-นาที
# ยาวเกินกว่าจะให้ browser ค้างรอ — ดู docstring ของ investigate_runner.py สำหรับเหตุผลเต็ม.
# เป็น endpoint ที่ 2 ในไฟล์นี้ที่แตะ LLM (คู่กับ /api/chat) — ยิงเฉพาะตอนผู้ใช้กดปุ่มเอง.

@app.post("/api/investigation/{ticker}", status_code=202)
def post_investigation(ticker: str, body: InvestigateStart | None = None):
    """สั่ง agent สืบ ticker นี้ใหม่ (เบื้องหลัง). 409 ถ้าของเดิมยังวิ่งอยู่ — กันกดรัวๆ เผาโควตา."""
    ticker = ticker.upper()
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=503, detail="ไม่มี GEMINI_API_KEY — สืบไม่ได้")

    # toolbox ของ investigate() เป็น stock-only (yfinance fundamentals + SEC XBRL/EDGAR) — ยิงกับ
    # crypto ได้ transcript ที่ tool คืน 'ไม่มีข้อมูล' ทุกอันแล้วเปลืองโควตาเปล่า จึงกันตั้งแต่ต้นทาง
    item = next((w for w in list_all() if w["ticker"] == ticker), None)
    if item is not None and item["asset_type"] != "stock":
        raise HTTPException(status_code=400, detail=f"{ticker} เป็น {item['asset_type']} — การสืบรองรับเฉพาะหุ้น")

    try:
        job = investigate_runner.start(ticker, focus=(body.focus if body else "").strip())
    except investigate_runner.AlreadyRunning:
        raise HTTPException(status_code=409, detail=f"{ticker} กำลังถูกสืบอยู่แล้ว")
    return job.as_dict()


@app.get("/api/investigation/{ticker}/status")
def get_investigation_status(ticker: str):
    """ความคืบหน้าของการสืบที่สั่งไว้ — steps โตขึ้นทีละสเต็ประหว่าง status='running'.
    404 = ยังไม่เคยสั่งสืบ ticker นี้ใน process ปัจจุบัน (state อยู่ในหน่วยความจำ ไม่ใช่ DB;
    transcript ที่จบแล้วอ่านจาก GET /api/investigation/{ticker} ได้ตามปกติ)."""
    job = investigate_runner.get(ticker.upper())
    if job is None:
        raise HTTPException(status_code=404, detail=f"no investigation job for {ticker}")
    return job.as_dict()


@app.get("/api/screener")
def get_screener(force: bool = False):
    """Phase 21 — สแกน UNIVERSE คัดมือหาหุ้นพื้นฐานแข็ง+ราคาถูก (Piotroski + reverse-DCF,
    ไม่เรียก LLM). อ่าน cache ดิสก์ปกติ (เร็ว) — force=true สแกนใหม่ทั้งก้อน (ช้า, นาทีระดับ,
    ยิง yfinance ~4 request/ticker) ใช้ตอนกดปุ่ม 'รีเฟรช' เองเท่านั้น ไม่ auto-refresh ทุก request.
    เติม already_watching ให้แต่ละแถวไว้ disable ปุ่ม '+เพิ่ม' ของ ticker ที่จับตาอยู่แล้ว."""
    data = screen(force=force)
    watching = {row["ticker"] for row in list_all()}
    for r in data["results"]:
        r["already_watching"] = r["ticker"] in watching
    return data


@app.post("/api/chat")
def post_chat(body: ChatAsk):
    """Phase 25 — "ถามพอร์ตได้เลย": ยิง Gemini จริงทุกครั้งที่เรียก (มีโควตา — endpoint เดียวใน
    ไฟล์นี้ที่แตะ LLM, ไม่มี auto-trigger ที่ไหนเรียกมัน นอกจากผู้ใช้กดถามเอง). Agent ไปดึงข้อมูล
    watchlist/health/valuation/changes/performance ที่คำนวณเก็บไว้ใน DB อยู่แล้วมาตอบ (ไม่ fetch
    yfinance สด) พร้อม step trace ให้เห็นว่าไปดึงอะไรมาอ้างอิงบ้าง (โปร่งใส เหมือน investigation
    panel เดิม). history = เทิร์นก่อนหน้าในสนทนาเดียวกัน (session ฝั่ง frontend เก็บไว้เอง ไม่มี
    persistence ฝั่ง backend — รีเฟรชหน้าเว็บ = เริ่มสนทนาใหม่)."""
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question ว่างเปล่า")
    history = [{"role": t.role, "text": t.text} for t in body.history]
    return ask_chat(body.question, chat_history=history)


@app.get("/api/macro")
def get_macro(horizon_days: int = 1):
    """Phase 26 — Macro Event Radar (แยกขาดจากแอประยะยาว, สำหรับเทรดสั้น): ตัวเลข macro ล่าสุด
    (CPI/PPI/ว่างงาน/NFP) + base-rate ผลตอบสนองย้อนหลังพร้อม 'ช่วงเหวี่ยง' + ธงข่าวภูมิรัฐศาสตร์.
    ดึงสด (FRED CSV คีย์ฟรี + yfinance + Google News RSS) ไม่เรียก LLM. ช้ากว่า endpoint อื่น
    (~ไม่กี่วินาที) เพราะดึงนอกหลายแหล่ง — จงใจ 'ไม่ฟันธงทิศทาง' บอกแค่ข้อเท็จจริง+การกระจาย."""
    alt = eth_btc_momentum()
    return {
        "releases": [v.as_dict() for v in macro_dashboard(horizon_days=horizon_days)],
        "geopolitical": [it.as_dict() for it in fetch_geopolitical()],
        "altseason": alt.as_dict() if alt else None,
    }


# ---- thesis / invalidation (Phase 5, ต่อสายเข้า UI ครั้งแรกที่ Phase 27) ----
# thesis เขียนเสร็จมาตั้งแต่ Phase 5 แต่ไม่เคยมี endpoint ให้ frontend เรียกได้ -> theses ว่างเปล่า
# มาตลอด (invalidation checker เลยไม่เคยมีอะไรให้เช็ค). อุดช่องนี้ก่อนอย่างอื่นเพราะเป็นระบบ
# "เตือนขาย" — ปล่อยว่างไว้ต่อ = ถือของจริงโดยไม่มีเงื่อนไขออกที่เช็คได้.

@app.get("/api/thesis/{ticker}")
def get_ticker_thesis(ticker: str):
    """thesis + invalidation rules ของ ticker — null ถ้ายังไม่เคยตั้ง (ไม่ error, หน้า UI แสดง
    ฟอร์มเปล่าให้กรอกแทน)."""
    return get_thesis(ticker.upper())


@app.put("/api/thesis/{ticker}")
def put_ticker_thesis(ticker: str, body: ThesisSet):
    """ตั้ง/แก้ thesis (upsert) — invalidation rules ตรวจรูปแบบด้วย thesis/store.py::_validate_rules
    อยู่แล้ว (metric ต้องมีค่า, op ต้องอยู่ในชุดที่รองรับ, value ต้องเป็นตัวเลข) โยน 400 ถ้าผิดรูป."""
    try:
        set_thesis(
            ticker.upper(),
            body.thesis,
            invalidation=[r.model_dump() for r in body.invalidation],
            fair_value=body.fair_value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return get_thesis(ticker.upper())


@app.delete("/api/thesis/{ticker}")
def delete_ticker_thesis(ticker: str):
    delete_thesis(ticker.upper())
    return {"ticker": ticker.upper(), "deleted": True}


@app.get("/api/invalidation/{ticker}")
def get_ticker_invalidation(ticker: str):
    """เทียบ invalidation rules ของ ticker กับตัวเลขงบล่าสุดที่บันทึกแล้ว (deterministic ไม่เรียก
    LLM) -> breaches ว่าง = thesis ยังอยู่ครบ. ดู src/agent/invalidation.py สำหรับตรรกะเต็ม."""
    return check_invalidation(ticker.upper())


# ---- decision journal (Phase 27) ----
# บันทึกทุกครั้งที่ตัดสินใจ "ซื้อ/ผ่าน/รอ/ขาย" รวมถึงตอน "ผ่าน" (สำคัญที่สุดแต่เดิมไม่เคยถูกจด
# เลย) พร้อม gate2 = ผลเช็คกราฟ/EW ณ ตอนนั้น (เก็บเป็น note อิสระ ไม่ผูกกับระบบ EW ที่แยกไปทำ
# ต่างหาก) เพื่อย้อนกลับมาวัดทีหลังว่า gate ที่สองนี้ช่วยจริงไหม เทียบกับซื้อทันทีที่ health ถึงเกณฑ์.
# health_score/price ดึงจากรอบวิเคราะห์ล่าสุด ณ ตอน log (point-in-time ของ "วันนี้" อยู่แล้ว
# เพราะบันทึกตอนตัดสินใจจริง ไม่ใช่ backfill ย้อนหลัง) -- ผู้ใช้กรอกแค่ action/gate2/reason.

@app.post("/api/decisions/{ticker}", status_code=201)
def post_decision(ticker: str, body: DecisionCreate):
    ticker = ticker.upper()
    rows = history(ticker, limit=1)
    health_score = rows[0]["health_score"] if rows else None
    price = rows[0]["price"] if rows else None
    return log_decision(
        ticker, action=body.action, health_score=health_score, price=price,
        gate2=body.gate2, gate2_note=body.gate2_note,
        reason=body.reason, conviction=body.conviction,
    )


@app.get("/api/decisions/{ticker}")
def get_decisions(ticker: str, limit: int = 50):
    return list_decisions(ticker.upper(), limit=limit)
