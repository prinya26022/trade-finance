import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

from src.agent.llm import generate_with_fallback

# โหลด .env เข้าเป็น env var + อ่าน checklist — ครั้งเดียวตอน import (เทียบจากตำแหน่งไฟล์นี้ ไม่ใช่ cwd)
ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")
CHECKLIST = (ROOT / "stock_analysis_checklist.md").read_text(encoding="utf-8")

# ── ด่านตรวจ 'เนื้อ' ของ output (2026-07): DUOL รอบ 2026-07-14 ได้ beginner_summary กลับมาเป็น
#    U+0019 (control char) 593 ตัว ไทย 0 ตัว — JSON valid, schema ผ่าน, grounding ผ่าน แต่หน้าเว็บ
#    ขึ้นเป็นสี่เหลี่ยม □ ทั้งย่อหน่วย. ไม่มีชั้นไหนใน pipeline ตรวจ 'ตัวอักษร' ที่ LLM คายออกมาเลย
#    แถวเสียเลยไหลลง DB ตรงๆ. generate_with_fallback() retry เฉพาะ API error (5xx/429) — เคสนี้
#    API สำเร็จ 200 แต่เนื้อหาพัง จึงต้องตรวจ+เรียกใหม่เองตรงนี้ (generation เพี้ยนเป็นเรื่องสุ่ม
#    ของ sampling — เรียกใหม่มักได้ output ปกติ ticker อื่นในรอบเดียวกันไม่โดนเลย)
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")   # C0 ยกเว้น \t \n \r
THAI_RE = re.compile(r"[฀-๿]")
MAX_OUTPUT_ATTEMPTS = 3

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


def _text_fields(summary: Summary) -> list[str]:
    """ทุก free-text ที่ LLM เขียนเอง (ไม่รวม Literal/ตัวเลข ซึ่ง schema บังคับให้ถูกอยู่แล้ว)."""
    return [
        summary.beginner_summary,
        summary.thesis_assessment,
        *summary.strength_reasons,
        *summary.what_to_watch,
        *summary.key_news,
        *summary.thesis_relevant_news,
        *[w.area for w in summary.weak_points],
        *[w.detail for w in summary.weak_points],
    ]


def garbled_reason(summary: Summary) -> str | None:
    """None = output ใช้ได้; ไม่งั้นคืนเหตุผลสั้นๆ ว่าเพี้ยนยังไง (ไว้ print ตอน retry).
    เช็ค 2 อย่าง: (1) control char ปนในข้อความไหนก็ตาม = ตัวอักษรพัง (เคส DUOL),
    (2) beginner_summary ไม่มีอักษรไทยเลย = LLM ไม่ทำตาม prompt หรือคายอักขระเพี้ยน
    (field นี้ prompt บังคับให้เป็นไทย 2-4 ประโยคเสมอ ทั้งหุ้นและ crypto -> ว่าง/ไม่มีไทย = ผิด)."""
    for text in _text_fields(summary):
        if CONTROL_CHARS_RE.search(text):
            return "มี control character ปนในข้อความ (ตัวอักษรกลายเป็นสี่เหลี่ยม □)"
    if not THAI_RE.search(summary.beginner_summary):
        return "beginner_summary ไม่มีอักษรไทยเลย"
    return None


def _clean(text: str) -> str:
    return CONTROL_CHARS_RE.sub("", text).strip()


def scrub(summary: Summary) -> Summary:
    """ด่านสุดท้าย: retry ครบแล้วยังเพี้ยน -> ตัด control char ทิ้ง (item ที่ว่างเปล่าก็ตัดทิ้ง)
    อย่างน้อยไม่มีสี่เหลี่ยมโผล่บน UI. ทิ้งแค่ 'ข้อความ' ไม่ทิ้งทั้งแถว — health/valuation
    คำนวณจากตัวเลขจริงล้วน (deterministic ไม่พึ่ง LLM) จึงยังใช้ได้เต็มๆ."""
    return summary.model_copy(update={
        "beginner_summary": _clean(summary.beginner_summary),
        "thesis_assessment": _clean(summary.thesis_assessment),
        "strength_reasons": [c for r in summary.strength_reasons if (c := _clean(r))],
        "what_to_watch": [c for w in summary.what_to_watch if (c := _clean(w))],
        "key_news": [c for n in summary.key_news if (c := _clean(n))],
        "thesis_relevant_news": [c for n in summary.thesis_relevant_news if (c := _clean(n))],
        "weak_points": [
            WeakPoint(area=_clean(w.area), detail=_clean(w.detail))
            for w in summary.weak_points
            if _clean(w.detail)
        ],
    })


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

### LANGUAGE (strict)
- Write ALL human-facing free text in THAI: `strength_reasons`, `weak_points.detail`,
  `what_to_watch`, `thesis_assessment`, `beginner_summary`. Keep finance terms in English
  inside the Thai sentence (ROIC, FCF, P/E, Operating Margin) — do not translate them.
- Keep these VERBATIM as given, do NOT translate: `key_news` and `thesis_relevant_news`
  (real headlines, copied exactly). `weak_points.area` stays a short English category label
  (e.g. "Valuation", "Growth", "Leverage").
- Output plain readable characters only — never emit control characters or placeholder glyphs.

- `fundamental_strength`: overall verdict (strong / mixed / weak).
- `strength_reasons` and `weak_points`: cite the ACTUAL metric values from DATA (e.g.
  "ROIC 82% สูงกว่าต้นทุนเงินทุนมาก"). For multi-year metrics, judge the trend across years.
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
- `thesis_assessment`: if a "MY THESIS" section is present above, write 1-3 Thai sentences
  judging whether TODAY's data still SUPPORTS that reason for holding, or challenges it
  (cite the metric/news that does). Be honest — if the data undercuts the thesis, say so. If
  there is NO thesis section, return an empty string "".
- `beginner_summary`: 2-4 short Thai sentences (NEVER empty), for a reader with NO finance
  background. Cover: is the business good or not, is the price cheap or expensive, and the
  main thing to watch out for. You may keep finance terms but add a 2-4 word Thai gloss in
  parentheses the first time (e.g. "ROIC (ผลตอบแทนต่อทุน) สูงมาก"). Plain and concrete, no
  jargon dumps, and still NOT a buy/sell recommendation.
- Fill every field of the required output schema.
"""

    # ---- เรียก Gemini (retry+backoff ต่อโมเดล + fallback ข้ามโมเดลถ้าโควตาเต็ม) แล้วบังคับ
    # output ให้ตรง Summary schema (ดู src/agent/llm.py — MODEL_CHAIN) ----
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = {
        "response_mime_type": "application/json",   # ขอผลลัพธ์เป็น JSON
        "response_schema": Summary,                 # บังคับ JSON ให้ตรง schema นี้เป๊ะ
    }

    # schema บังคับ 'รูปร่าง' ได้ แต่บังคับ 'ตัวอักษร' ไม่ได้ -> ตรวจเนื้อเองแล้วเรียกใหม่ถ้าเพี้ยน
    summary = None
    for attempt in range(1, MAX_OUTPUT_ATTEMPTS + 1):
        summary = generate_with_fallback(client, prompt, config=config).parsed
        reason = garbled_reason(summary) if summary is not None else "LLM ไม่คืน JSON ที่ parse ได้"
        if reason is None:
            return summary
        print(f"[retry] {price.ticker}: output เพี้ยน ({reason}) "
              f"attempt {attempt}/{MAX_OUTPUT_ATTEMPTS}")

    if summary is None:
        raise RuntimeError(f"{price.ticker}: LLM ไม่คืน JSON ที่ parse ได้ครบ {MAX_OUTPUT_ATTEMPTS} ครั้ง")
    print(f"[warn] {price.ticker}: output ยังเพี้ยนหลัง retry ครบ -> ตัดตัวอักษรเสียทิ้งแล้วเก็บต่อ")
    return scrub(summary)