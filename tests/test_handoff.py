"""Phase 33 — ยกงานให้โมเดลในแชททำแล้วนำผลกลับเข้าระบบ. Offline ล้วน (ไม่แตะ yfinance/Gemini).

สิ่งที่ test นี้คุ้มครองจริงๆ คือ 'ความแฟร์ของการเทียบ' ไม่ใช่แค่ว่าโค้ดไม่ crash:
- ไฟล์ที่คนแปะให้อีกโมเดล ต้องมีข้อมูล/framework/task ชุดเดียวกับที่ Gemini ได้รับ
- คำตอบต้องถูกตรวจกับ snapshot ตอน export (ไม่ใช่ราคาวันที่นำเข้า)
- นำเข้าซ้ำ = ทับ ไม่ใช่เพิ่มแถว (งานที่ทำด้วยมือ ทำซ้ำง่ายมาก)
"""
import json

import pytest

from src.agent import handoff
from src.agent.compare import compare_period
from src.agent.summarize import Summary, WeakPoint, build_prompt, data_block
from src.domain.interfaces import Fact, NewsItem, PriceSnapshot

PERIOD = "2026-08"

PRICE = {"ticker": "DUOL", "price": 100.0, "currency": "USD", "as_of": "2026-08-01"}
NEWS = [{"title": "Duolingo beats earnings estimates", "url": "u",
         "published_at": "2026-08-01", "source": "Reuters", "category": "", "material": False}]
FACTS = [{"label": "ROIC", "value": 76.1, "unit": "%", "period": "FY2025"},
         {"label": "Free Cash Flow", "value": 1200000000.0, "unit": "USD", "period": "FY2025"}]


def _pack(**over) -> dict:
    item = {"ticker": "DUOL", "asset_type": "stock", "price": PRICE, "news": NEWS,
            "facts": FACTS, "thesis": None, "status": "holding",
            "gemini_analysis_id": None, "gemini_run_at": None}
    item.update(over)
    return {"period": PERIOD, "created_at": "2026-08-01T09:00:00", "items": [item]}


def _reply_summary(**over) -> dict:
    base = dict(
        ticker="DUOL", price=100.0,
        fundamental_strength="strong",
        strength_reasons=["ROIC 76.1% สูงกว่าต้นทุนเงินทุนมาก"],
        weak_points=[{"area": "Valuation", "detail": "ราคาสะท้อนการเติบโตไปมากแล้ว"}],
        valuation_view="expensive",
        thesis_relevant_news=[],
        key_news=["Duolingo beats earnings estimates"],
        what_to_watch=["Gross Margin"],
        sentiment="neutral", confidence=0.8, thesis_assessment="",
        beginner_summary="ธุรกิจแข็งแรง แต่ราคาแพงแล้ว ระวังการเติบโตที่ชะลอ",
    )
    base.update(over)
    return base


@pytest.fixture
def pack_on_disk(tmp_path, monkeypatch):
    """ชี้ PACK_DIR ไป temp แล้ววาง snapshot ไว้ 1 งวด (เลี่ยงการดึงข้อมูลจริงตอน export)."""
    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    pack = _pack()
    (tmp_path / f"{PERIOD}.json").write_text(json.dumps(pack, ensure_ascii=False),
                                             encoding="utf-8")
    return pack


# ---------------------------------------------------------------- export ----

def test_markdown_contains_the_same_data_block_gemini_sees():
    """กันการ drift: ถ้าใครแก้ prompt ฝั่ง summarize แล้ว pack ไม่ตาม การเทียบจะไม่แฟร์ทันที."""
    md = handoff.render_markdown(_pack())
    expected = data_block(PriceSnapshot(**PRICE), [NewsItem(**n) for n in NEWS],
                          [Fact(**f) for f in FACTS], thesis=None, asset_type="stock").strip()
    assert expected in md


def test_markdown_has_framework_task_and_schema_once():
    md = handoff.render_markdown(_pack())
    assert "## HOW TO THINK (framework)" in md
    assert "## TASK" in md
    assert md.count("Judge, from ONLY the data above") == 1   # framework/task ไม่ซ้ำต่อ ticker
    assert "beginner_summary" in md                            # schema ถูกฝังมาให้ตอบตามได้


def test_markdown_uses_crypto_framework_for_crypto_items():
    md = handoff.render_markdown(_pack(ticker="BTC", asset_type="crypto"))
    assert "Supply & dilution" in md
    assert "This is a CRYPTO asset" in md


def test_full_prompt_still_identical_shape():
    """build_prompt (ทางที่ Gemini ใช้) ต้องยังประกอบจากชิ้นเดียวกันครบ."""
    prompt = build_prompt(PriceSnapshot(**PRICE), [NewsItem(**n) for n in NEWS],
                          [Fact(**f) for f in FACTS])
    assert "## DATA" in prompt and "## HOW TO THINK (framework)" in prompt and "## TASK" in prompt


# ---------------------------------------------------------------- import ----

def test_ingest_saves_and_runs_the_same_evals(tmp_db, pack_on_disk):
    from src.history import claude_store

    reply = json.dumps([_reply_summary()], ensure_ascii=False)
    results = handoff.ingest(PERIOD, reply, model="claude-test")

    assert [r["ok"] for r in results] == [True]
    saved = claude_store.for_period(PERIOD)
    assert len(saved) == 1
    row = saved[0]
    assert row["ticker"] == "DUOL"
    assert row["price_ok"] is True                       # ราคาเทียบกับ snapshot ตอน export
    assert row["news_grounded_ratio"] == 1.0             # พาดหัวตรงกับข่าวที่ให้ไป
    assert row["facts_grounded_ratio"] == 1.0            # 76.1 ตรงกับ Fact จริง
    assert row["summary"]["beginner_summary"].startswith("ธุรกิจแข็งแรง")


def test_ingest_catches_invented_numbers(tmp_db, pack_on_disk):
    """แก่นของการเทียบ: อ้างเลขที่ไม่มีใน DATA ต้องถูกจับได้ ไม่ใช่ผ่านเพราะข้อความดูดี."""
    reply = json.dumps([_reply_summary(strength_reasons=["ROIC 99.9% สูงมาก"])],
                       ensure_ascii=False)
    handoff.ingest(PERIOD, reply, model="claude-test")

    from src.history import claude_store
    row = claude_store.for_period(PERIOD)[0]
    assert row["facts_grounded_ratio"] == 0.0
    assert 99.9 in row["grounding"]["facts"]["unmatched_numbers"]


def test_ingest_accepts_reply_wrapped_in_code_fence(tmp_db, pack_on_disk):
    reply = "นี่คือผลวิเคราะห์ครับ\n\n```json\n" + json.dumps([_reply_summary()],
                                                              ensure_ascii=False) + "\n```\n"
    results = handoff.ingest(PERIOD, reply, model="claude-test")
    assert results[0]["ok"] is True


def test_reimport_overwrites_instead_of_duplicating(tmp_db, pack_on_disk):
    from src.history import claude_store

    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")
    handoff.ingest(PERIOD, json.dumps([_reply_summary(valuation_view="fair")]),
                   model="claude-test")

    rows = claude_store.for_period(PERIOD)
    assert len(rows) == 1
    assert rows[0]["valuation_view"] == "fair"


def test_ingest_reports_bad_and_missing_rows_without_failing_the_batch(tmp_db, pack_on_disk):
    reply = json.dumps([
        _reply_summary(ticker="NVDA"),                       # ไม่ได้อยู่ใน pack
        {"ticker": "DUOL", "price": 100.0},                  # schema ไม่ครบ
    ])
    results = handoff.ingest(PERIOD, reply, model="claude-test")

    by_ticker = {r["ticker"]: r for r in results}
    assert by_ticker["NVDA"]["ok"] is False and "pack" in by_ticker["NVDA"]["error"]
    assert by_ticker["DUOL"]["ok"] is False and "schema" in by_ticker["DUOL"]["error"]


def test_ingest_scrubs_garbled_text_like_the_gemini_path(tmp_db, pack_on_disk):
    reply = json.dumps([_reply_summary(beginner_summary="ธุรกิจดี\x19\x19 ราคาแพง")])
    results = handoff.ingest(PERIOD, reply, model="claude-test")

    assert results[0]["warning"] is not None
    assert "\x19" not in results[0]["summary"].beginner_summary


def test_ingest_without_pack_refuses_rather_than_using_todays_data(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        handoff.ingest("1999-01", json.dumps([_reply_summary()]), model="claude-test")


# --------------------------------------------------------------- compare ----

def test_compare_pairs_with_the_linked_gemini_row(tmp_db, tmp_path, monkeypatch):
    """คู่เทียบต้องเป็นแถวที่ผูกไว้ตอน export (ข้อมูลชุดเดียวกัน) — ไม่ใช่แถวไหนก็ได้ในเดือนนั้น."""
    from src.history.store import save_analysis

    gemini = Summary(**_reply_summary(valuation_view="fair",
                                      strength_reasons=["ROIC 76.1% แข็งแรง"]))
    analysis_id = save_analysis(
        gemini,
        {"price_ok": True, "news_grounded_ratio": 1.0, "facts": {"facts_grounded_ratio": 1.0}},
        [Fact(**f) for f in FACTS],
    )

    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    (tmp_path / f"{PERIOD}.json").write_text(
        json.dumps(_pack(gemini_analysis_id=analysis_id), ensure_ascii=False), encoding="utf-8")
    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")

    result = compare_period(PERIOD, model="claude-test")
    row = result["rows"][0]

    assert row["linked"] is True                             # จับคู่กับแถวที่ผูกไว้ตอน export
    assert row["data_gap_days"] is not None                  # แต่ยังต้องบอกว่าข้อมูลห่างกันกี่วัน
    assert row["agree"]["fundamental_strength"] is True      # strong ทั้งคู่
    assert row["agree"]["valuation_view"] is False           # expensive vs fair
    assert result["disagreements"][0]["field"] == "valuation_view"
    # ความละเอียดของฝั่ง Gemini ต้องนับได้ด้วย (คำนวณสดจาก summary+facts ที่เก็บไว้)
    assert result["totals"]["detail_avg"]["gemini"]["cited_numbers"] is not None


def test_compare_reports_the_data_gap_when_not_linked(tmp_db, tmp_path, monkeypatch):
    """pack เก่าที่ไม่ได้ผูก analyses.id ไว้ -> ถอยไปหาแถวในงวดเดียวกันได้ แต่ต้องยอมรับตรงๆ ว่า
    ไม่ใช่คู่ที่ผูกไว้ และข้อมูลห่างกันกี่วัน — ไม่ใช่เงียบแล้วให้คนเข้าใจว่าเทียบข้อมูลชุดเดียวกัน."""
    from src.history.store import save_analysis

    save_analysis(Summary(**_reply_summary()),
                  {"price_ok": True, "news_grounded_ratio": 1.0,
                   "facts": {"facts_grounded_ratio": 1.0}},
                  [Fact(**f) for f in FACTS])

    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    (tmp_path / f"{PERIOD}.json").write_text(json.dumps(_pack(), ensure_ascii=False),
                                             encoding="utf-8")
    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")

    row = compare_period(PERIOD, model="claude-test")["rows"][0]
    assert row["gemini"] is not None        # ยังเทียบได้
    assert row["linked"] is False           # แต่ไม่ใช่คู่ที่ผูกไว้ตอน export
    assert isinstance(row["data_gap_days"], int)


def test_compare_is_empty_when_nothing_imported(tmp_db):
    assert compare_period("1999-01")["rows"] == []


def test_derived_facts_put_the_two_line_comparisons_into_data():
    """ข้อ 1 ของแผน 2026-08: สิ่งที่ต้องเอาสองบรรทัดมาชนกันถึงจะเห็น ต้องถูกคำนวณมาเป็น Fact
    ไม่ใช่ฝากไว้กับการที่ LLM จะสังเกตเอง (เคส DUOL: NM 39.91% vs OM 13.07%)."""
    from src.providers.stock.fundamentals import StockFundamentals

    f = StockFundamentals(
        period="FY2025",
        net_margin_series=[("FY2025", 39.91), ("FY2024", 11.84)],
        operating_margin_series=[("FY2025", 13.07), ("FY2024", 8.37)],
        cfo=387_823_000.0, net_income=414_065_000.0, pe=15.42, forward_pe=17.18,
    )
    by_label = {x.label: x for x in f.to_facts()}

    assert round(by_label["Earnings Quality Gap"].value, 2) == 26.84
    assert by_label["Earnings Quality Gap"].period == "FY2025"
    assert round(by_label["CFO / Net Income"].value, 3) == 0.937
    assert round(by_label["Forward P/E - P/E"].value, 2) == 1.76   # บวก = ตลาดคาดกำไรลด


def test_derived_facts_skip_what_cannot_be_compared():
    """ขาดทุน -> CFO/NI ไร้ความหมาย, งวดไม่ตรงกัน -> เทียบ margin ไม่ได้: ต้องไม่ใส่ค่ามั่ว."""
    from src.providers.stock.fundamentals import StockFundamentals

    f = StockFundamentals(
        period="FY2025",
        net_margin_series=[("FY2025", 30.0)],
        operating_margin_series=[("FY2023", 5.0)],
        cfo=100.0, net_income=-50.0,
    )
    labels = {x.label for x in f.to_facts()}
    assert "Earnings Quality Gap" not in labels
    assert "CFO / Net Income" not in labels


# ── Phase 33.2: ติดเวอร์ชันของ 'กรอบที่ใช้ตัดสิน' ไปกับทุกแถว ────────────────
# ถ้าไม่มี การเทียบข้ามงวดจะปนกันระหว่าง 'โมเดลเปลี่ยน' กับ 'เราแก้ checklist'

def test_framework_version_changes_when_the_framework_changes(monkeypatch):
    from src.agent import summarize

    before = summarize.framework_version()
    assert before == summarize.framework_version()          # เสถียร ไม่สุ่มทุกครั้งที่เรียก
    monkeypatch.setattr(summarize, "CHECKLIST", summarize.CHECKLIST + "\n- เกณฑ์ใหม่")
    assert summarize.framework_version() != before          # แก้แม้บรรทัดเดียวต้องเปลี่ยน


def test_pack_and_imported_rows_carry_the_framework_version(tmp_db, tmp_path, monkeypatch):
    from src.agent.summarize import framework_version
    from src.history import claude_store

    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    pack = _pack()
    pack["framework_version"] = "abc123"
    (tmp_path / f"{PERIOD}.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")

    # เวอร์ชันที่บันทึกต้องเป็นของ 'ตอน export' ไม่ใช่ของตอนนำเข้า (คำตอบเขียนจากกรอบชุดนั้น)
    assert claude_store.for_period(PERIOD)[0]["framework_version"] == "abc123"
    assert framework_version() != "abc123"


def test_compare_flags_when_the_two_sides_used_different_frameworks(tmp_db, tmp_path, monkeypatch):
    from src.history.store import save_analysis

    analysis_id = save_analysis(
        Summary(**_reply_summary()),
        {"price_ok": True, "news_grounded_ratio": 1.0, "facts": {"facts_grounded_ratio": 1.0}},
        [Fact(**f) for f in FACTS],
    )
    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    pack = _pack(gemini_analysis_id=analysis_id)
    pack["framework_version"] = "OLD-VERSION"
    (tmp_path / f"{PERIOD}.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")

    row = compare_period(PERIOD, model="claude-test")["rows"][0]
    assert row["same_framework"] is False      # ฝั่ง Gemini บันทึกเวอร์ชันปัจจุบันไว้ตอน save


def test_compare_says_unknown_not_same_for_rows_without_a_version(tmp_db, tmp_path, monkeypatch):
    """แถวเก่าก่อนมีคอลัมน์นี้ = 'ไม่รู้' ห้ามแสดงเป็น 'กรอบเดียวกัน'."""
    monkeypatch.setattr(handoff, "PACK_DIR", tmp_path)
    (tmp_path / f"{PERIOD}.json").write_text(json.dumps(_pack(), ensure_ascii=False),
                                             encoding="utf-8")
    handoff.ingest(PERIOD, json.dumps([_reply_summary()]), model="claude-test")

    row = compare_period(PERIOD, model="claude-test")["rows"][0]
    assert row["same_framework"] is None
