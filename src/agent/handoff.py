"""ส่งงานวิเคราะห์ให้ 'LLM ที่ไม่มี API key' ทำแทน แล้วรับผลกลับเข้าระบบ (Phase 33).

ปัญหาที่แก้: pipeline รายวันเรียก Gemini ผ่าน API (ฟรีแต่โควตาจำกัด 20/วัน/โมเดล) — แต่ถ้าอยาก
ได้ความเห็นจากโมเดลอื่นที่ยังไม่มีงบซื้อ API key ก็ยังทำได้ ด้วยการ 'ยกข้อมูลออกมาเป็นไฟล์
ให้คนแปะในแชทเอง' แล้วนำคำตอบกลับเข้ามาบันทึก. เดือนละครั้งก็พอ (ดูรายเดือน ไม่ใช่รายวัน)
เพราะงานนี้ใช้แรงคน ไม่ใช่ cron.

หัวใจที่ทำให้ 'เทียบกันได้จริง' ไม่ใช่แค่ 'มีความเห็นสองอัน':
1) ข้อความที่อีกโมเดลอ่าน ประกอบจากชิ้นส่วน prompt ชุดเดียวกับที่ Gemini อ่าน (summarize.py)
   — ไม่ได้เขียน prompt ใหม่แยกไว้ที่นี่ ซึ่งจะ drift ทันทีที่แก้ฝั่งเดียว
2) คำตอบถูกบังคับให้อยู่ใน Summary schema เดิม แล้ววิ่งผ่าน eval ตัวเดียวกัน (check_grounding /
   check_facts_grounding) — 'ละเอียดกว่า' จึงพิสูจน์ได้ด้วยตัวเลข ไม่ใช่ความรู้สึก
3) snapshot ข้อมูลถูกเก็บเป็นไฟล์ .json คู่กับ .md — ตอนนำเข้าจึงเอา 'ข้อมูลชุดเดิม' มาตรวจ
   คำตอบได้ ไม่ใช่ข้อมูลวันที่นำเข้า (ซึ่งราคาขยับไปแล้ว -> price_ok จะเพี้ยนโดยไม่ใช่ความผิดโมเดล)
"""
import json
from datetime import datetime
from pathlib import Path

from src.agent.summarize import (
    FRAMEWORK_HEADER,
    framework_version,
    TASK_BLOCK,
    Summary,
    asset_profile,
    data_block,
    garbled_reason,
    scrub,
)
from src.domain.interfaces import Fact, NewsItem, PriceSnapshot
from src.evals.check_grounding import check_facts_grounding, check_grounding
from src.history.store import history as gemini_history
from src.providers.registry import get_providers
from src.thesis.store import get_thesis
from src.watchlist.store import list_all

ROOT = Path(__file__).parents[2]
PACK_DIR = ROOT / "data" / "claude_packs"


def current_period() -> str:
    return datetime.now().strftime("%Y-%m")


def pack_paths(period: str) -> dict[str, Path]:
    """.md = ไฟล์ที่คนเอาไปแปะ, .json = snapshot ข้อมูลดิบไว้ตรวจคำตอบตอนนำเข้า,
    .reply.json = ที่ให้เอาคำตอบมาวาง."""
    return {
        "markdown": PACK_DIR / f"{period}.md",
        "data": PACK_DIR / f"{period}.json",
        "reply": PACK_DIR / f"{period}.reply.json",
    }


# ---------------------------------------------------------------- export ----

def _collect(ticker: str, asset_type: str) -> dict | None:
    """ดึงข้อมูลดิบของ ticker เดียว — ไม่เรียก LLM เลย (yfinance/ข่าว/SEC ฟรีทั้งหมด) จึง
    export ได้บ่อยแค่ไหนก็ได้โดยไม่กินโควตา Gemini ของรอบวิเคราะห์รายวัน."""
    bundle = get_providers(asset_type)
    try:
        price = bundle.price.get_price(ticker)
    except Exception as e:
        print(f"[error] price failed for {ticker}: {e}")
        return None
    if price is None or price.price is None:
        print(f"[error] no price data for {ticker}")
        return None

    try:
        news = bundle.news.get_news(ticker, limit=5)
    except Exception as e:
        news = []
        print(f"[warn] {ticker}: news failed: {e}")
    try:
        facts = bundle.fundamentals.get_fundamentals(ticker).to_facts()
    except Exception as e:
        facts = []
        print(f"[warn] {ticker}: fundamentals failed: {e}")

    thesis = get_thesis(ticker)
    rows = gemini_history(ticker, limit=1)   # แถว Gemini ล่าสุด = คู่เทียบที่ข้อมูลใกล้กันที่สุด

    return {
        "ticker": ticker,
        "asset_type": asset_type,
        "price": {"ticker": price.ticker, "price": price.price,
                  "currency": price.currency, "as_of": price.as_of},
        "news": [n.__dict__ for n in news],
        "facts": [f.__dict__ for f in facts],
        "thesis": thesis["thesis"] if thesis else None,
        "gemini_analysis_id": rows[0]["id"] if rows else None,
        "gemini_run_at": rows[0]["run_at"] if rows else None,
    }


def build_pack(tickers: list[str] | None = None, period: str | None = None,
               include_frozen: bool = False) -> dict:
    """รวบรวมข้อมูลทุกตัวที่จะให้วิเคราะห์. ปริยาย = watchlist ที่ยัง active (ข้าม frozen ซึ่ง
    ตั้งใจไม่วิเคราะห์ถี่อยู่แล้ว — ระบุชื่อเองได้ถ้าอยากได้)."""
    period = period or current_period()
    if tickers:
        wanted = {t.upper() for t in tickers}
        rows = [r for r in list_all() if r["ticker"] in wanted]
    else:
        rows = [r for r in list_all() if include_frozen or r["status"] != "frozen"]

    items = []
    for row in rows:
        item = _collect(row["ticker"], row["asset_type"])
        if item is None:
            continue
        item["status"] = row["status"]
        items.append(item)

    return {
        "period": period,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        # ติดฐานไปกับ snapshot: ถ้า checklist/TASK ถูกแก้ระหว่างงวด การเทียบข้ามงวดต้องรู้ตัว
        "framework_version": framework_version(),
        "items": items,
    }


def _to_objects(item: dict) -> tuple[PriceSnapshot, list[NewsItem], list[Fact]]:
    """dict จาก pack -> dataclass เดิม (ทั้ง render และ ingest ต้องใช้ 'ข้อมูลชุดเดียวกัน')."""
    price = PriceSnapshot(**item["price"])
    news = [NewsItem(**n) for n in item["news"]]
    facts = [Fact(**f) for f in item["facts"]]
    return price, news, facts


def _schema_block() -> str:
    """schema จริงจาก Pydantic (ไม่ได้พิมพ์มือ) — แก้ Summary เมื่อไหร่ ไฟล์ pack ตามทันทันที."""
    return json.dumps(Summary.model_json_schema(), ensure_ascii=False, indent=2)


def render_markdown(pack: dict) -> str:
    """ไฟล์ที่คนจะเปิดแล้ว copy ทั้งหมดไปแปะในแชท.

    เรียง framework/task ไว้ 'ครั้งเดียว' ด้านบน แล้วตามด้วย DATA ทีละ ticker — เพราะ checklist
    ก้อนเดียว ~20KB ถ้าแปะซ้ำทุกตัวแบบ prompt ของ API (ที่ยิงทีละ call) ไฟล์จะใหญ่เกินแปะไหว.
    เนื้อหาทุกชิ้นยังเป็นตัวเดียวกับที่ Gemini ได้รับ ต่างแค่ 'ลำดับการจัดวาง'.
    """
    items = pack["items"]
    kinds = {i["asset_type"] for i in items}
    reply_name = pack_paths(pack["period"])["reply"].name

    out = [
        f"# ชุดข้อมูลวิเคราะห์ งวด {pack['period']}",
        "",
        f"snapshot: {pack['created_at']} · {len(items)} รายการ",
        "",
        "## คำสั่ง (อ่านก่อนเริ่ม)",
        "",
        "คุณกำลังทำงานแทน pipeline วิเคราะห์หุ้นระยะยาวของผม ซึ่งปกติรันด้วยโมเดลอื่น",
        "ผลของคุณจะถูกบันทึกลง DB คนละตารางเพื่อ **เทียบกัน** จึงต้องอยู่ในรูปแบบเดียวกันเป๊ะ",
        "",
        f"1. วิเคราะห์ **ทุก ticker** ในหัวข้อ ITEMS ด้านล่าง ({len(items)} ตัว) ทีละตัว",
        "2. ใช้ framework + TASK ชุดเดียวกันด้านล่างนี้กับทุกตัว (ไม่ได้พิมพ์ซ้ำในแต่ละตัว)",
        "3. ห้ามใช้ความรู้นอกไฟล์นี้เป็น 'ตัวเลข' เด็ดขาด — ตัวเลขทุกตัวต้องมาจาก DATA ของ ticker นั้น",
        "   (ระบบมี eval ไล่เช็คว่าเลขที่อ้างตรงกับ Fact จริงไหม — เดาแล้วโดนจับได้)",
        f"4. ตอบกลับเป็น **JSON array ก้อนเดียว** เรียงตามลำดับ ticker ที่ให้มา แล้วให้ผมเซฟเป็น `{reply_name}`",
        "",
        "## OUTPUT FORMAT (strict)",
        "",
        "JSON array ของ object ตาม schema นี้ (1 object = 1 ticker):",
        "",
        "```json",
        _schema_block(),
        "```",
        "",
    ]

    for kind in ("stock", "crypto"):
        if kind not in kinds:
            continue
        profile = asset_profile(kind)
        label = "หุ้น" if kind == "stock" else "คริปโต"
        out += [
            f"## บทบาท + framework — {label} ({kind})",
            "",
            f"For every `{kind}` item below: You are {profile['role']}. Analyze ONLY the data "
            "provided — do not invent numbers you were not given. Research, not advice.",
        ]
        if profile["asset_note"]:
            out += ["", profile["asset_note"].strip()]
        out += ["", FRAMEWORK_HEADER, "", profile["framework"], ""]

    out += [
        "## TASK (ใช้กับทุก ticker)",
        "",
        TASK_BLOCK.strip(),
        "",
        "---",
        "",
        "# ITEMS",
        "",
    ]

    for idx, item in enumerate(pack["items"], 1):
        price, news, facts = _to_objects(item)
        out += [
            f"## [{idx}/{len(items)}] {item['ticker']} — {item['asset_type']} "
            f"(สถานะ: {item.get('status', '-')})",
            "",
            data_block(price, news, facts, thesis=item.get("thesis"),
                       asset_type=item["asset_type"]).strip(),
            "",
        ]

    return "\n".join(out) + "\n"


def export(tickers: list[str] | None = None, period: str | None = None,
           include_frozen: bool = False) -> dict:
    """สร้าง pack แล้วเขียนลงดิสก์; คืน path ที่เขียน + pack."""
    pack = build_pack(tickers, period, include_frozen)
    paths = pack_paths(pack["period"])
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    paths["data"].write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["markdown"].write_text(render_markdown(pack), encoding="utf-8")
    return {"pack": pack, "paths": paths}


# ---------------------------------------------------------------- import ----

def load_pack(period: str) -> dict:
    path = pack_paths(period)["data"]
    if not path.exists():
        raise FileNotFoundError(
            f"ไม่พบ snapshot ของงวด {period} ({path}) — ต้อง export ก่อนถึงจะนำเข้าได้ "
            "(คำตอบต้องถูกตรวจกับข้อมูลชุดที่ส่งออกไป ไม่ใช่ข้อมูลวันนี้)"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_reply(raw: str) -> list[dict]:
    """รับได้ทั้ง JSON array ล้วน และข้อความที่มี ```json ... ``` ครอบ (คนก๊อปมาจากแชทตรงๆ)."""
    text = raw.strip()
    if "```" in text:
        blocks = text.split("```")
        for block in blocks[1::2]:                      # เนื้อใน fence เท่านั้น
            body = block.split("\n", 1)[-1] if block[:20].lower().startswith("json") else block
            body = body.strip()
            if body.startswith("["):
                text = body
                break
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]                                    # ตอบมาตัวเดียวก็รับ
    if not isinstance(data, list):
        raise ValueError("คำตอบต้องเป็น JSON array ของ Summary")
    return data


def ingest(period: str, reply_text: str, model: str, persist: bool = True) -> list[dict]:
    """แปลงคำตอบ -> Summary, ตรวจด้วย eval ชุดเดียวกับฝั่ง Gemini, แล้วบันทึก.

    คืน list ของผลรายตัว (ใช้ทั้ง CLI และ test) — แต่ละตัวมี ok/error เพื่อให้ ticker เดียวพัง
    ไม่ล้มการนำเข้าทั้งงวด (หลักเดียวกับ run_watchlist ที่กัน 1 ตัวพังแล้วทั้ง loop ตาย).
    """
    from src.history import claude_store          # import ตรงนี้ให้ test monkeypatch DB_PATH ทัน

    pack = load_pack(period)
    by_ticker = {i["ticker"].upper(): i for i in pack["items"]}
    results = []

    for raw in _parse_reply(reply_text):
        ticker = str(raw.get("ticker", "")).upper()
        item = by_ticker.get(ticker)
        if item is None:
            results.append({"ticker": ticker or "?", "ok": False,
                            "error": f"ไม่มี {ticker!r} อยู่ใน pack งวด {period}"})
            continue
        try:
            summary = Summary.model_validate(raw)
        except Exception as e:
            results.append({"ticker": ticker, "ok": False, "error": f"schema ไม่ผ่าน: {e}"})
            continue

        warning = garbled_reason(summary)
        if warning:
            summary = scrub(summary)                 # ด่านเดียวกับฝั่ง Gemini (ดู summarize.py)

        price, news, facts = _to_objects(item)
        grounding = check_grounding(summary, price, news)
        grounding["facts"] = check_facts_grounding(summary, facts)

        row_id = None
        if persist:
            row_id = claude_store.save(
                summary, grounding, period=period, model=model,
                pack_created_at=pack["created_at"],
                analysis_id=item.get("gemini_analysis_id"),
                # เวอร์ชันของ 'ตอนที่ export' ไม่ใช่ตอนนำเข้า — คำตอบถูกเขียนจากกรอบชุดนั้น
                framework_version=pack.get("framework_version"),
            )
        results.append({"ticker": ticker, "ok": True, "id": row_id, "summary": summary,
                        "grounding": grounding, "warning": warning})

    missing = sorted(by_ticker.keys() - {r["ticker"] for r in results})
    for ticker in missing:
        results.append({"ticker": ticker, "ok": False, "error": "ไม่มีในคำตอบ (ยังไม่ได้วิเคราะห์)"})
    return results
