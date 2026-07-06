import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

# โหลด .env เข้าเป็น env var + อ่าน checklist — ครั้งเดียวตอน import (เทียบจากตำแหน่งไฟล์นี้ ไม่ใช่ cwd)
ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")
CHECKLIST = (ROOT / "stock_analysis_checklist.md").read_text(encoding="utf-8")


class Summary(BaseModel):
    ticker: str
    price: float
    sentiment: Literal["bullish", "neutral", "bearish"]
    key_news: list[str]
    what_to_watch: list[str]
    confidence: float 

def summarize(price, news, facts) -> Summary:
    news_lines = "\n".join(f"- {n.title} ({n.source})" for n in news)     # ← คำนวณข้างบน
    fact_lines = "\n".join(f"- {f.label}: {f.value} {f.unit} ({f.period})" for f in facts)

    prompt = f"""
You are a fundamental equity analyst. Analyze ONLY the data provided below —
do not invent numbers you were not given. This is research, not investment advice.

## DATA
Ticker: {price.ticker}
Price: {price.price} {price.currency} (as of {price.as_of})

Recent news:
{news_lines}

Fundamentals:
{fact_lines}

## HOW TO THINK (framework)
{CHECKLIST}

## TASK
Judge whether this stock looks worth a closer look, based only on the data above.
- report the price and news exactly from the DATA (don't change them)
- if a metric needed by the framework is missing, say so — don't guess
- fill every field of the required output schema
"""

    # ---- เรียก Gemini แล้วบังคับ output ให้ตรง Summary schema ----
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",   # ขอผลลัพธ์เป็น JSON
            "response_schema": Summary,                 # บังคับ JSON ให้ตรง schema นี้เป๊ะ
        },
    )
    return response.parsed          # Gemini parse ให้แล้ว -> คืน Summary object เลย