import os
import random
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import errors
from pydantic import BaseModel

# error ที่ "ชั่วคราว" — retry ได้ (server ล้น/rate limit). ที่ไม่อยู่ในนี้ (400 prompt ผิด,
# 401 key ผิด) = ถาวร ยิงซ้ำก็ผิด จึงโยน error ทันทีไม่ retry
RETRYABLE_CODES = {429, 500, 502, 503, 504}

# โหลด .env เข้าเป็น env var + อ่าน checklist — ครั้งเดียวตอน import (เทียบจากตำแหน่งไฟล์นี้ ไม่ใช่ cwd)
ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")
CHECKLIST = (ROOT / "stock_analysis_checklist.md").read_text(encoding="utf-8")

# framework สำหรับ crypto (คนละโลกกับหุ้น: ไม่มีงบ/กำไร — ดู tokenomics + สภาพคล่อง + adoption)
CRYPTO_FRAMEWORK = """\
Judge a crypto asset for a LONG-TERM holder using ONLY the data given:
1) Supply & dilution: hard cap (scarce) or uncapped (inflationary)? How much supply is
   already issued vs still to come ('Dilution Ahead')? High remaining dilution = future
   selling pressure / value dilution. Fully Diluted Valuation far above Market Cap = big
   unissued-supply overhang.
2) Liquidity: 'Volume / Market Cap' — higher = easier to enter/exit, more real trading;
   very low = illiquid and risky to hold in size.
3) Network / adoption (from NEWS only): real usage, integrations, upgrades — or serious
   risks (hacks/exploits, regulatory action, delistings, chain halts). Ignore price hype.
4) Risk flags: large token unlocks, centralization/governance concerns, security incidents.
5) Guardrails: research, NOT advice. No buy/sell/timing calls, never extrapolate price. If
   data is too thin to judge a dimension, say so — never invent numbers.
"""


class WeakPoint(BaseModel):
    area: str            # หมวดที่อ่อน เช่น "Valuation", "Growth", "Leverage", "Cash Flow"
    detail: str          # อ่อนยังไง อ้างเมตริกจริงจาก DATA (เช่น "PEG 2.5 = ตลาดคาดหวังสูง")


class Summary(BaseModel):
    ticker: str
    price: float

    # --- แก่น Phase 2: พื้นฐานแข็งหรืออ่อน และอ่อน "ตรงไหน" ---
    fundamental_strength: Literal["strong", "mixed", "weak"]
    strength_reasons: list[str]      # จุดแข็ง อ้างเมตริกจริง
    weak_points: list[WeakPoint]     # จุดอ่อนแยกเป็นหมวด อ้างเมตริกจริง
    valuation_view: Literal["cheap", "fair", "expensive", "unclear"]

    # --- ข่าว: กรอบลงทุนระยะยาว (แยก thesis ออกจาก noise) ---
    thesis_relevant_news: list[str]  # เฉพาะข่าวที่แตะ thesis/invalidation/พื้นฐาน; ถ้าเป็น noise หมด = []
    key_news: list[str]              # คงไว้ให้ grounding eval ตรวจ (ข่าวจริงที่หยิบมา)

    what_to_watch: list[str]
    sentiment: Literal["bullish", "neutral", "bearish"]
    confidence: float

    # Phase 5: ถ้าผู้ใช้เขียน thesis ไว้ -> LLM ตอบว่าข้อมูลวันนี้ยัง 'สนับสนุน' เหตุผลถือไหม
    # (ว่างถ้ายังไม่มี thesis) — คนละชั้นกับ invalidation ที่เป็น rule เช็คด้วยเครื่อง
    thesis_assessment: str

    # สรุปไทยง่ายๆ สำหรับคนไม่มีพื้นการเงิน (อยู่ท้ายสุด -> LLM เขียนหลังคิดครบทุกอย่างแล้ว)
    beginner_summary: str


def summarize(price, news, facts, thesis: str | None = None, asset_type: str = "stock") -> Summary:
    # material (8-K ที่บริษัทถูกกฎหมายบังคับให้ยื่น) ทำ marker ให้เด่น เพื่อให้ LLM ถ่วงน้ำหนักสูงกว่าข่าว aggregator
    news_lines = "\n".join(
        (f"- ⚑ [SEC 8-K, company-filed material event] {n.title}"
         if n.material else f"- {n.title} ({n.source})")
        for n in news
    )
    fact_lines = "\n".join(f"- {f.label}: {f.value} {f.unit} ({f.period})" for f in facts)
    thesis_block = f"\n## MY THESIS (why I hold/watch this)\n{thesis}\n" if thesis else ""

    # ต่างกันแค่ 3 จุด (role / data header / framework) + note เตือนว่าเป็น crypto —
    # ที่เหลือ (schema, grounding, guardrails) reuse ทั้งหมด นี่คือจุดที่ asset-agnostic คุ้ม
    if asset_type == "crypto":
        role = ("a crypto asset analyst serving a LONG-TERM investor (holds through cycles, "
                "exits only when the thesis breaks — not on daily price/news moves)")
        data_header = "Tokenomics & market metrics (point-in-time snapshot — NOT fiscal-year statements):"
        framework = CRYPTO_FRAMEWORK
        asset_note = (
            "\nNOTE: This is a CRYPTO asset — there are NO earnings, margins, P/E or cash flows. "
            "Judge `fundamental_strength` from tokenomics (supply schedule, dilution ahead, "
            "scarcity/hard cap) and liquidity (24h volume vs market cap), plus adoption/network "
            "signals in the news. `valuation_view` is a ROUGH relative read (market cap vs supply "
            "dynamics, liquidity, adoption) — use 'unclear' if the data can't support a view.\n"
        )
    else:
        role = ("a fundamental equity analyst serving a LONG-TERM investor (holds for years, "
                "exits only when the thesis breaks — not on daily price/news moves)")
        data_header = "Fundamentals (some metrics span multiple fiscal years — read them as a TREND):"
        framework = CHECKLIST
        asset_note = ""

    prompt = f"""
You are {role}. Analyze ONLY the
data provided below — do not invent numbers you were not given. Research, not advice.
{asset_note}
## DATA
Ticker: {price.ticker}
Price: {price.price} {price.currency} (as of {price.as_of})

Recent news:
{news_lines}

{data_header}
{fact_lines}
{thesis_block}
## HOW TO THINK (framework)
{framework}

## TASK
Judge, from ONLY the data above, whether the fundamentals look STRONG or WEAK and WHERE.
- `fundamental_strength`: overall verdict (strong / mixed / weak).
- `strength_reasons` and `weak_points`: cite the ACTUAL metric values from DATA (e.g.
  "ROIC 82% >> cost of capital"). For multi-year metrics, judge the trend across years.
- `valuation_view`: cheap / fair / expensive / unclear, from the valuation multiples.
- If a metric the framework needs is MISSING from DATA, say so — never guess a number.
- NEWS (long-term lens): put an item in `thesis_relevant_news` ONLY if it could touch the
  thesis, the invalidation point, the moat, or the fundamentals. Daily price/noise items do
  NOT belong there — if all news is noise, return []. `key_news` still lists the real
  headlines you were given, verbatim. Items marked "⚑ [SEC 8-K ...]" are material events the
  company was LEGALLY REQUIRED to file (leadership change, M&A, restructuring, restatement,
  earnings) — weight these ABOVE aggregator headlines, and treat a thesis-relevant 8-K
  (e.g. layoffs/restructuring, CEO/CFO change, restatement) as a signal worth surfacing.
- Do NOT give a buy/sell or timing call. Report price exactly from DATA.
- `confidence`: a number 0.0-1.0 (how sure you are given the data completeness).
- `thesis_assessment`: if a "MY THESIS" section is present above, write 1-3 sentences in
  THAI judging whether TODAY's data still SUPPORTS that reason for holding, or challenges it
  (cite the metric/news that does). Be honest — if the data undercuts the thesis, say so. If
  there is NO thesis section, return an empty string "".
- `beginner_summary`: write in THAI, 2-4 short sentences, for a reader with NO finance
  background. Cover: is the business good or not, is the price cheap or expensive, and the
  main thing to watch out for. You may keep finance terms but add a 2-4 word Thai gloss in
  parentheses the first time (e.g. "ROIC (ผลตอบแทนต่อทุน) สูงมาก"). Plain and concrete, no
  jargon dumps, and still NOT a buy/sell recommendation.
- Fill every field of the required output schema.
"""

    # ---- เรียก Gemini (มี retry+backoff) แล้วบังคับ output ให้ตรง Summary schema ----
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = _generate_with_retry(client, prompt)
    return response.parsed          # Gemini parse ให้แล้ว -> คืน Summary object เลย


def _generate_with_retry(client, prompt, *, max_attempts: int = 4, base_delay: float = 1.0):
    """เรียก Gemini พร้อม exponential backoff — retry เฉพาะ error ชั่วคราว (5xx/429).
    ดีเลย์ถ่างขึ้น 1s→2s→4s + jitter สุ่มเล็กน้อย (กันหลาย request เด้งพร้อมกันตอน batch)."""
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",   # ขอผลลัพธ์เป็น JSON
                    "response_schema": Summary,                 # บังคับ JSON ให้ตรง schema นี้เป๊ะ
                },
            )
        except errors.APIError as e:
            # error ถาวร (ไม่อยู่ใน RETRYABLE) หรือ attempt สุดท้ายแล้ว -> โยนต่อ ไม่กลืน
            if e.code not in RETRYABLE_CODES or attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            print(f"[retry] Gemini {e.code}, attempt {attempt}/{max_attempts}, waiting {delay:.1f}s")
            time.sleep(delay)