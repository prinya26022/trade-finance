"""Read-only API over the analysis history (FastAPI).

แค่ "อ่าน" อย่างเดียว — การวิเคราะห์ (เรียก Gemini) เกิดใน agent loop แยกต่างหาก
API นี้ไม่แตะ LLM เลย จึงไม่กิน quota. Next.js dashboard จะ fetch จากที่นี่.

รัน:  uvicorn src.api.main:app --reload
ดู docs อัตโนมัติที่  http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.history.store import init_db, latest_per_ticker, history
from src.watchlist.store import list_all

app = FastAPI(title="Investment Research Agent API")

# อนุญาตให้ Next.js dev server (localhost:3000) เรียกข้าม origin ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()   # กัน error ถ้ายังไม่เคยรัน agent (ตารางยังไม่ถูกสร้าง)


@app.get("/api/watchlist")
def get_watchlist():
    """รายการ ticker ที่จับตา (ticker + asset_type)."""
    return [dict(row) for row in list_all()]


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
