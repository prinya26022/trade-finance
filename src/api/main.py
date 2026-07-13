"""Read-only API over the analysis history (FastAPI).

แค่ "อ่าน" อย่างเดียว — การวิเคราะห์ (เรียก Gemini) เกิดใน agent loop แยกต่างหาก
API นี้ไม่แตะ LLM เลย จึงไม่กิน quota. Next.js dashboard จะ fetch จากที่นี่.

รัน:  uvicorn src.api.main:app --reload
ดู docs อัตโนมัติที่  http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.history.store import init_db, latest_per_ticker, history
from src.watchlist.store import (
    list_all, add as add_ticker, remove as remove_ticker,
    set_holding, add_shares, set_watching, set_frozen,
)
from src.agent.changes import detect_changes
from src.agent.performance import portfolio_edge
from src.agent.investigate_store import latest_investigation
from src.agent.timeline import build_timeline
from src.agent.timeline_store import get_narrative

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
    """transcript การสืบล่าสุดของ agent (Phase 13) — 204 ถ้ายังไม่เคยสืบ ticker นี้.
    read-only: ไม่ trigger การสืบใหม่ (นั่นยิง Gemini — ทำผ่าน CLI/ปุ่มแยก ไม่ใช่ตอน render)."""
    inv = latest_investigation(ticker.upper())
    if inv is None:
        raise HTTPException(status_code=404, detail=f"no investigation for {ticker}")
    return inv
