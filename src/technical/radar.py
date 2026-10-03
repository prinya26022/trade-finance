"""รอบรายวัน: คิดคะแนนกราฟทั้ง watchlist แล้วบอกว่า **ตัวไหนเปลี่ยน tier** — ส่งภาพเฉพาะตัวนั้น.

กติกาการเปลี่ยน (เขียนเป็นโค้ดเพราะแต่ละข้อคือวิธีที่ alert จะกลายเป็นขยะถ้าไม่ระวัง):
- **รอบแรกของ ticker = บันทึกเงียบ** ไม่ใช่ "เปลี่ยน" — ไม่งั้นวันแรกที่ deploy จะส่งภาพทั้ง watchlist
- **"วัดไม่ได้" ไม่ทับ state** — yfinance สะดุดวันเดียวแล้วกลับมา จะได้ไม่กลายเป็น "เปลี่ยน" สองรอบ
  (ok -> วัดไม่ได้ -> ok) ที่ไม่มีอะไรเกิดขึ้นจริง. ยังบันทึกลงประวัติ จึงไม่หายไปเงียบๆ
- **ดึงราคาไม่ได้ ≠ วัดไม่ได้** — อันแรกคือปัญหาของเรา ไม่บันทึกเป็นผลของหุ้น แต่รายงานใน log
- **เกณฑ์เปลี่ยน (engine version ต่าง) ต้องบอกว่าเป็นเพราะเรา** — ไม่งั้นการแก้เส้น SMA วันไหน
  จะอ่านเหมือนตลาดพลิกทั้งกระดานวันนั้น (Phase 37)
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from src.agent.engine_version import parts_from, version_from
from src.technical import store
from src.technical.fetch import daily_closes
from src.technical.score import evaluate

BENCHMARK = "VT"
_ROOT = Path(__file__).parents[2]
# ไฟล์ที่ประกอบเป็น "กติกาให้คะแนนกราฟ" — แก้ไฟล์ไหนในนี้ = เกณฑ์เปลี่ยน
TECH_MODULES = ("src/technical/bars.py", "src/technical/indicators.py", "src/technical/score.py")


def tech_version() -> str:
    """ลายนิ้วมือของเกณฑ์กราฟ — ใช้ normalize แบบเดียวกับ engine_version (ตัดคอมเมนต์/docstring
    แก้คำอธิบายแล้วไม่นับว่าเกณฑ์เปลี่ยน)"""
    return version_from(parts_from({m: (_ROOT / m).read_text(encoding="utf-8") for m in TECH_MODULES}))


@dataclass
class Change:
    ticker: str
    before: dict          # แถว tech_state รอบก่อน
    result: dict          # ผลรอบนี้
    week: list
    month: list
    rule_change: bool     # tier เปลี่ยนในรอบที่เกณฑ์เปลี่ยนด้วย -> อาจเป็นเพราะเรา ไม่ใช่ราคา


@dataclass
class ScanReport:
    changes: list[Change] = field(default_factory=list)
    bootstrapped: list[str] = field(default_factory=list)
    unmeasurable: list[str] = field(default_factory=list)
    fetch_failed: list[str] = field(default_factory=list)
    aborted: str | None = None


def yahoo_symbol(ticker: str, asset_type: str) -> str:
    """ชื่อใน watchlist -> สัญลักษณ์ yfinance. crypto ต้องต่อ -USD: "BTC" เฉยๆ ใน yfinance คือ
    **กองทุน ETF ราคา $37** ไม่ใช่บิตคอยน์ — ดึงผิดตัวแล้วยังได้คะแนนหน้าตาปกติ (เจอจริงตอนรัน
    watchlist ครั้งแรก: ได้ 3/6 เท่ากับ BTC จริงโดยบังเอิญ จึงไม่มีอะไรดูผิด). ใช้กฎเดียวกับ
    provider ราคา crypto เพื่อไม่ให้สองที่แปลงชื่อคนละแบบ"""
    if asset_type != "crypto":
        return ticker
    from src.providers.crypto.price import yf_symbol
    return yf_symbol(ticker)


def _watchlist() -> list[tuple[str, str]]:
    from src.watchlist.store import list_all
    return [(r["ticker"], r["asset_type"]) for r in list_all()]


def scan(tickers: list[tuple[str, str]] | None = None, fetch=daily_closes, asof: date | None = None,
         version: str | None = None, db_path: Path | None = None) -> ScanReport:
    """ทุกตัวใน watchlist (ทุกสถานะ — ถูกพอจะไม่ต้องข้าม frozen). fetch/asof/version ใส่เองได้ = เทสต์ได้"""
    asof = asof or datetime.now(timezone.utc).date()
    version = version or tech_version()
    report = ScanReport()

    bench = fetch(BENCHMARK)
    if bench is None:
        # ไม่มี VT = ทุกตัวจะ "วัดไม่ได้" พร้อมกัน — นั่นคือปัญหาของเรา ไม่ใช่ข้อมูลของหุ้น
        report.aborted = f"ดึงราคา {BENCHMARK} ไม่ได้ — ข้ามทั้งรอบ ไม่บันทึกอะไร"
        return report

    prev = store.states(db_path)
    for ticker, asset_type in (tickers if tickers is not None else _watchlist()):
        daily = fetch(yahoo_symbol(ticker, asset_type))
        if daily is None:
            report.fetch_failed.append(ticker)
            continue
        week, month, r = evaluate(daily, bench, asof, asset_type, BENCHMARK)
        measured = r["score"] is not None
        store.record(ticker, r, version, update_state=measured, db_path=db_path)
        if not measured:
            report.unmeasurable.append(ticker)
            continue
        before = prev.get(ticker)
        if before is None or before["tier"] == "unmeasurable":
            report.bootstrapped.append(ticker)
        elif before["tier"] != r["tier"]:
            report.changes.append(Change(ticker, before, r, week, month,
                                         rule_change=before["version"] != version))
    return report


def run(send: bool = True) -> ScanReport:
    """ทางเข้าของ workflow: scan แล้วส่งภาพเฉพาะตัวที่เปลี่ยน."""
    from src.technical.notify import send as send_one

    report = scan()
    if report.aborted:
        print(f"[technical] {report.aborted}")
        return report
    print(f"[technical] เปลี่ยน {len(report.changes)} · บันทึกครั้งแรก {len(report.bootstrapped)} · "
          f"วัดไม่ได้ {report.unmeasurable or '-'} · ดึงไม่ได้ {report.fetch_failed or '-'}")
    for c in report.changes:
        print(f"[technical] {c.ticker}: {c.before['tier']} -> {c.result['tier']}"
              + (" (เกณฑ์เปลี่ยนรอบนี้)" if c.rule_change else ""))
        if send:
            send_one(c.ticker, c.week, c.month, c.result, before=c.before, rule_change=c.rule_change)
    return report
