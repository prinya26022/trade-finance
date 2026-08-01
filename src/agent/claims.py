"""ตัวแปลข้ออ้าง (Phase 31) — วางบทวิเคราะห์ของคนอื่นเข้ามา แล้วแยกว่าอันไหน 'ผิดได้' บ้าง.

ทำไมต้องมี: Phase 30 ทำที่เก็บ+ตัวตรวจ 'เรื่องเล่าที่รอพิสูจน์' ไว้แล้ว แต่ผู้ใช้ต้องแปลเอง
จาก "Bedrock จะดัน AWS" -> metric + เป้า + เส้นตาย ซึ่ง**เป็นส่วนที่ยากที่สุดสำหรับคนที่ไม่ใช่
สายการเงิน** ถ้าไม่มีตัวช่วยตรงนี้ ช่อง expectations จะถูกทิ้งว่างเหมือนที่ thesis เคยว่างมา 22 เฟส.

หลักที่ยึด (สำคัญกว่าตัวโมเดล):
1. **LLM เสนอ เราไม่เชื่อทันที** — ทุกข้อเสนอผ่านด่านตรวจแบบ deterministic ก่อนถึงมือผู้ใช้:
   metric ต้องมีอยู่จริงใน facts ของ ticker นั้น (ไม่งั้นโดนลดชั้นเป็น needs_data), op ต้องอยู่ใน
   ชุดที่รองรับ, value ต้องเป็นตัวเลข, เส้นตายต้อง parse ได้. LLM แต่งชื่อเมตริกได้ง่ายมาก และ
   expectation ที่อ้างเมตริกไม่มีจริงจะขึ้น 'วัดไม่ได้' ตลอดกาล = ขยะที่ดูเหมือนใช้ได้
2. **จัดชั้นให้ครบ ไม่ใช่คัดเฉพาะที่ผ่าน** — ข้ออ้างที่ 'ผิดไม่ได้' ต้องถูกแสดงว่าตกด้วยเหตุผล
   อะไร นั่นคือคุณค่าหลักของฟีเจอร์นี้ (เห็นว่าบทวิเคราะห์ที่ฟังดูดี มีกี่ข้อที่วัดไม่ได้เลย)
3. ไม่ตัดสินว่า 'จริงหรือเท็จ' ตรงนี้ — แค่แปลงเป็นข้อความที่ตรวจได้ แล้วปล่อยให้ตัวเลขตัดสิน
   ทีหลังผ่าน check_expectations() (deterministic เหมือนเดิม)
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from src.agent.llm import INTERACTIVE_CHAIN, generate_with_fallback
from src.thesis.store import VALID_OPS

# ชั้นของข้ออ้าง — 3 ชั้นแรกคือ 'ใช้ไม่ได้' โดยธรรมชาติของมันเอง ไม่ใช่เพราะข้อมูลเราไม่พอ
ClaimKind = Literal["checkable", "needs_data", "unfalsifiable", "timing", "factual"]

KIND_LABEL = {
    "checkable": "ตรวจได้ด้วยตัวเลขที่เรามี",
    "needs_data": "ตรวจได้ในหลักการ แต่ไม่มีเมตริกนี้ในงบที่เราเก็บ",
    "unfalsifiable": "ผิดไม่ได้ — ไม่มีตัวเลขไหนที่จะพิสูจน์ว่าคิดผิด",
    "timing": "เป็นการเดาราคา/จังหวะ — นอกขอบเขตเครื่องมือนี้โดยตั้งใจ",
    "factual": "ข้อเท็จจริงเชิงคุณภาพ (ไม่ใช่ตัวเลขงบ) — เก็บเป็นบริบทได้ แต่ไม่ใช่ thesis",
}

DEFAULT_HORIZON_DAYS = 365


class ClaimProposal(BaseModel):
    """1 ข้ออ้างที่ LLM แยกออกมาได้ (ก่อนผ่านด่านตรวจของเรา)."""
    claim: str                       # ข้ออ้างที่เรียบเรียงเป็นประโยคเดียว
    kind: ClaimKind
    why: str                         # เหตุผลของการจัดชั้น (โชว์ให้ผู้ใช้เห็น)
    metric: str = ""                 # เฉพาะ checkable — ต้องมาจาก AVAILABLE METRICS เท่านั้น
    op: str = ""
    value: float | None = None
    by: str = ""                     # YYYY-MM-DD


class ClaimExtraction(BaseModel):
    proposals: list[ClaimProposal]


_SYSTEM = """You turn stock commentary into statements that CAN BE WRONG.

For each distinct claim in the text, classify it:
- "checkable": provable/disprovable with a company financial metric FROM THE PROVIDED LIST.
  Fill metric (EXACT string from the list), op, value, and a deadline `by` (YYYY-MM-DD).
- "needs_data": measurable in principle, but no metric in the provided list can measure it
  (e.g. a business-segment number we do not have).
- "unfalsifiable": no number could ever prove the speaker wrong ("it can't lose money",
  "the new product should help", "X is the best"). This is the most important category to
  catch honestly -- do NOT force such a claim into "checkable".
- "timing": a call about price direction or short-term moves.
- "factual": a real-world/qualitative fact, not a financial metric (e.g. a technology monopoly).

Rules:
- NEVER invent a metric name. Use only the exact strings given in AVAILABLE METRICS.
- Prefer fewer, sharper claims over splitting one idea into many.
- The threshold must be a number the claim actually implies; if the text implies "keeps growing
  fast", pick a concrete number consistent with the text and say so in `why`.
- `claim` and `why` in THAI. Be blunt in `why` when a claim is unfalsifiable.
- Judge nothing as true or false. You only translate."""


def _labels(metrics: list) -> list[str]:
    """รับได้ทั้ง list[str] และ list[dict] (label+value+unit) -> คืนเฉพาะ label."""
    return [m["label"] if isinstance(m, dict) else str(m) for m in metrics]


def _render_metrics(metrics: list) -> str:
    """แสดงเมตริกพร้อม **ค่าปัจจุบันและหน่วย** ให้ LLM เห็น.

    เจอจริงตอน verify Phase 31: ถ้าให้แค่ชื่อเมตริก โมเดลตั้งเป้าผิดสเกลทันที — เคสจริงคือ
    'Revenue > 700000' สำหรับ AMZN (คิดเป็นหน่วยล้าน) ทั้งที่ fact เก็บเป็นดอลลาร์เต็ม 6.4e11
    เป้าแบบนั้นจะขึ้น 'เข้าเป้าแล้ว' ตลอดกาล = expectation ที่ดูใช้งานได้แต่ไม่มีวันผิด ซึ่งตรงข้าม
    กับจุดประสงค์ทั้งหมดของฟีเจอร์นี้. การโชว์ค่าปัจจุบันยังช่วยให้เป้าที่ตั้งสมเหตุสมผลขึ้นด้วย
    (เห็นว่าตอนนี้อยู่ตรงไหน)."""
    out = []
    for m in metrics:
        if isinstance(m, dict):
            v = m["value"]
            # เลขใหญ่เขียนเต็มพร้อม comma ไม่ใช่ 6.37959e+11 — สัญกรณ์วิทยาศาสตร์คือต้นเหตุที่ทำให้
            # โมเดลไพล่ไปคิดเป็น 'หน่วยล้าน' ตั้งแต่แรก
            shown = f"{v:,.0f}" if abs(v) >= 1e6 else f"{v:g}"
            unit = f" {m['unit']}" if m.get("unit") else ""
            period = f" ({m['period']})" if m.get("period") else ""
            out.append(f"- {m['label']} = ตอนนี้ {shown}{unit}{period}")
        else:
            out.append(f"- {m}")
    return "\n".join(out)


def _prompt(text: str, ticker: str, metrics: list) -> str:
    horizon = (date.today() + timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat()
    return (
        f"TICKER: {ticker}\nTODAY: {date.today().isoformat()}\n"
        f"(if a claim has no explicit deadline, use {horizon})\n\n"
        f"AVAILABLE METRICS (exact strings, nothing else is allowed). The CURRENT value is shown so\n"
        f"your threshold uses the SAME UNIT AND SCALE -- never restate a figure in millions/billions:\n"
        + _render_metrics(metrics)
        + f"\n\nCOMMENTARY TO ANALYSE:\n{text}\n"
    )


def available_metrics(ticker: str) -> list[dict]:
    """เมตริกที่ 'มีจริง' ในงบล่าสุดของ ticker นี้ พร้อมค่าปัจจุบัน/หน่วย — เป็นทั้ง input ให้ LLM
    (เพื่อไม่ให้ตั้งเป้าผิดหน่วย) และไม้บรรทัดตรวจข้อเสนอทีหลัง (metric ที่ไม่อยู่ในนี้ = วัดไม่ได้
    จริง ไม่ว่าจะฟังดูดีแค่ไหน). ค่าที่หยิบคือค่าล่าสุดต่อ label."""
    from src.history.store import history

    rows = history(ticker.upper(), limit=1)
    if not rows:
        return []
    latest: dict[str, dict] = {}
    for f in (rows[0].get("facts") or []):
        if f.get("value") is None:
            continue
        cur = latest.get(f["label"])
        if cur is None or str(f.get("period", "")) >= str(cur.get("period", "")):
            latest[f["label"]] = {"label": f["label"], "value": float(f["value"]),
                                  "unit": f.get("unit", ""), "period": f.get("period", "")}
    return [latest[k] for k in sorted(latest)]


def _vet(p: ClaimProposal, metrics: set[str]) -> dict:
    """ด่านตรวจ deterministic — ลดชั้นข้อเสนอที่ตรวจจริงไม่ได้ ไม่ว่าที่ LLM บอกว่าอะไร."""
    out = {"claim": p.claim.strip(), "kind": p.kind, "why": p.why.strip(),
           "metric": p.metric.strip(), "op": p.op.strip(), "value": p.value,
           "by": p.by.strip(), "deadline_defaulted": False}

    if p.kind != "checkable":
        return out

    if out["metric"] not in metrics:
        # เมตริกที่ LLM แต่งขึ้น/ไม่มีในงบชุดนี้ -> ไม่ใช่ข้ออ้างที่ตรวจได้ (นี่คือกับดักหลัก)
        out.update(kind="needs_data", metric="", op="", value=None, by="",
                   why=(out["why"] + f" · เราไม่มีเมตริก '{p.metric}' ในงบที่เก็บไว้").strip(" ·"))
        return out
    if out["op"] not in VALID_OPS or out["value"] is None:
        out.update(kind="needs_data", why=(out["why"] + " · แปลงเป็นเงื่อนไขตัวเลขที่ชัดเจนไม่ได้").strip(" ·"))
        return out
    try:
        date.fromisoformat(out["by"])
    except ValueError:
        # ไม่มีเส้นตาย = ไม่มีวันผิด -> ไม่ปล่อยผ่าน แต่ยังไม่ทิ้ง: เติมค่าเริ่มต้นแล้วบอกให้ผู้ใช้ยืนยัน
        out["by"] = (date.today() + timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat()
        out["deadline_defaulted"] = True
    return out


def extract_claims(text: str, ticker: str, metrics: list[str] | None = None,
                   generate=None) -> dict:
    """แยกข้ออ้างจากข้อความดิบ -> ข้อเสนอที่ผ่านด่านตรวจแล้ว (ยังไม่บันทึกลง thesis).
    generate = ฉีดฟังก์ชันเรียก LLM ได้เพื่อเทสต์ออฟไลน์ (โปรดักชันปล่อย None)."""
    ticker = ticker.upper()
    metrics = available_metrics(ticker) if metrics is None else metrics
    if not text.strip():
        raise ValueError("ไม่มีข้อความให้วิเคราะห์")

    if generate is None:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        def generate(prompt: str):
            return generate_with_fallback(
                client, prompt, models=INTERACTIVE_CHAIN,   # เลนโควตาของงานที่ผู้ใช้กดเอง
                config={"response_mime_type": "application/json",
                        "response_schema": ClaimExtraction,
                        "system_instruction": _SYSTEM},
            ).parsed

    parsed = generate(_prompt(text, ticker, metrics))
    if parsed is None:
        raise RuntimeError("LLM ไม่คืน JSON ที่ parse ได้")

    metric_set = set(_labels(metrics))
    proposals = [_vet(p, metric_set) for p in parsed.proposals]
    counts: dict[str, int] = {}
    for p in proposals:
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    return {
        "ticker": ticker,
        "proposals": proposals,
        "counts": counts,
        "kind_labels": KIND_LABEL,
        "n_metrics_available": len(metrics),
    }


def extract_claims_with_context(text: str, ticker: str) -> dict:
    """เวอร์ชันที่ดึงเมตริก+ค่าปัจจุบันจาก DB ให้เอง (ใช้จาก API)."""
    return extract_claims(text, ticker, available_metrics(ticker))