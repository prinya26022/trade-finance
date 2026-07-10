"""สร้าง report จากผลที่เก็บไว้ แล้วส่งเข้า Discord — 4 โหมด ตามความถี่ที่เหมาะกับข้อมูลแต่ละแบบ.

- baseline (แทรกอัตโนมัติ) : ภาพเต็มของ ticker ที่เพิ่งวิเคราะห์ครั้งแรก (ยังไม่มีอะไรให้เทียบ)
- daily   : alert-first — เฉพาะสิ่งที่เปลี่ยนตั้งแต่ครั้งก่อน (ค่าเริ่มต้นของ scheduled run รายวัน)
- weekly  : สิ่งที่เปลี่ยนสะสม 7 วัน + สถานะย่อทุกตัว (ทุกวันจันทร์)
- monthly : ทบทวน thesis เต็มรูปแบบทุกตัว + สิ่งที่เปลี่ยนสะสม 30 วัน (วันที่ 1 ของเดือน)

หลักสำคัญ: การ 'วิเคราะห์' (เรียก Gemini) รันรายวันเท่านั้น — โหมดรายงานเป็นแค่มุมมองของ
ข้อมูลที่เก็บไว้แล้ว จึงไม่กินโควตาเพิ่มไม่ว่าจะเลือกโหมดไหน หรือส่งซ้ำกี่ครั้งก็ได้.
เรียก build_report(mode=...) ตรงๆ เพื่อทดสอบ/บังคับโหมด, หรือปล่อย None ให้ pick_mode()
เลือกจากวันที่ปัจจุบัน (ใช้ตอน scheduled run จริงผ่าน send_report()).

แยกอีก 2 ช่อง (คนละหัวข้อกับ report หลัก จึงส่งไปช่อง Discord อื่น):
- build_quality_report()/send_quality_report() — "ระบบคำนวณของเราเองยังแม่นอยู่ไหม"
  (DISCORD_WEBHOOK_URL_QUALITY)
- build_portfolio_alert()/send_portfolio_alert() — เงื่อนไขออกที่โดนแตะ 'เฉพาะโพซิชันที่ถือ
  อยู่จริง' (ไม่ใช่แค่จับตา) เป็นสัญญาณที่ต้องรู้ทันที ต่างจาก research feed ทั่วไปที่เช็ค
  วันละครั้งพอ จึงแยกช่อง (DISCORD_WEBHOOK_URL_PORTFOLIO) ให้ตั้ง push notification เฉพาะได้
"""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.history.store import latest_per_ticker, history
from src.agent.changes import detect_changes, changes_over_window
from src.agent.performance import portfolio_edge
from src.watchlist.store import list_all
from src.notify.discord import post_chunks

load_dotenv(Path(__file__).parents[2] / ".env")   # ให้ DISCORD_WEBHOOK_URL พร้อมใช้

STRENGTH_EMOJI = {"strong": "🟢", "mixed": "🟡", "weak": "🔴"}
SEVERITY_EMOJI = {"alert": "🔴", "warn": "🟠", "info": "🔵"}
WINDOW_DAYS = {"daily": None, "weekly": 7, "monthly": 30}   # None = เทียบแค่คู่ล่าสุด
EXTRACTION_WARN_THRESHOLD = 0.8   # ต่ำกว่านี้ = การคำนวณของเราเองน่าสงสัย ควรเปิดดู debug tool
TITLE = {
    "daily": "📊 Daily Watchlist Report",
    "weekly": "📅 Weekly Watchlist Report",
    "monthly": "🗓️ Monthly Thesis Review",
}


def pick_mode(today: date | None = None) -> str:
    """เลือกโหมดจากวันที่ (ใช้ตอน scheduled run รายวัน):
    วันที่ 1 ของเดือน -> monthly, วันจันทร์ -> weekly, วันอื่นๆ -> daily."""
    d = today or date.today()
    if d.day == 1:
        return "monthly"
    if d.weekday() == 0:   # Monday
        return "weekly"
    return "daily"


def _status_line(a: dict) -> str:
    s = a["summary"]
    em = STRENGTH_EMOJI.get(s["fundamental_strength"], "⚪")
    return f"{em} `{a['ticker']:<5}` {s['fundamental_strength']} / {s['valuation_view']}"


def _full_picture(a: dict, header_prefix: str = "") -> list[str]:
    """ภาพเต็มของ ticker หนึ่ง: verdict + beginner_summary + จุดอ่อนเด่น 2 อันดับแรก.
    ใช้ทั้งกับ (ก) baseline ตอนวิเคราะห์ครั้งแรก และ (ข) monthly thesis review — โครงเดียวกัน
    เพราะทั้งคู่ต้องการ 'สรุปทั้งภาพ' ไม่ใช่แค่ diff."""
    s = a["summary"]
    em = STRENGTH_EMOJI.get(s["fundamental_strength"], "⚪")
    lines = [f"{header_prefix}**{a['ticker']}**  {em} {s['fundamental_strength']} / {s['valuation_view']}"]
    if s.get("beginner_summary"):
        lines.append(s["beginner_summary"])
    for w in s.get("weak_points", [])[:2]:
        lines.append(f"  ⚠️ [{w['area']}] {w['detail']}")
    return lines


def _is_first_run(ticker: str) -> bool:
    """True ถ้านี่คือผลวิเคราะห์ครั้งแรกของ ticker นี้ (ยังไม่มีของก่อนหน้าให้เทียบ)."""
    return len(history(ticker, limit=2)) == 1


def _holding_tickers() -> set[str]:
    """ticker ที่สถานะ 'holding' (ถืออยู่จริง) — ใช้แยกความด่วนของ breach จากของที่แค่จับตา."""
    return {r["ticker"] for r in list_all() if r["status"] == "holding"}


def _portfolio_section() -> list[str]:
    """P&L + edge เทียบ benchmark ของทุก holding — ตอบด่าน 182 (มี edge จริงไหม ไม่ใช่แค่โชค).
    ใช้ราคาจาก yfinance เท่านั้น (ไม่เรียก LLM); ว่างถ้าไม่มี holding เลย -> ไม่โชว์ section นี้."""
    try:
        result = portfolio_edge()
    except Exception as e:
        print(f"[warn] portfolio_edge failed: {e}")
        return []
    if not result["positions"]:
        return []

    lines = [f"📌 **พอร์ตของคุณ** (เทียบ {result['benchmark']})"]
    for p in result["positions"]:
        sign = "🟢" if p["edge"] >= 0 else "🔴"
        lines.append(
            f"  {sign} `{p['ticker']:<5}` you {p['your_return']:+.1f}% · {result['benchmark']} "
            f"{p['benchmark_return']:+.1f}% · edge {p['edge']:+.1f}% ({p['holding_days']}d)"
        )
    lines.append(f"  รวม: ชนะ {result['benchmark']} {result['beating_benchmark']}/{result['total_positions']} ตัว")
    lines.append("")
    return lines


BREACH_TYPES = {"invalidation", "no_margin_safety"}   # เงื่อนไขออก/มูลค่า ที่ผู้ใช้ตั้งเอง (ด่าน 4)


def _gather_changes(tickers: list[str], window_days: int | None) -> dict[str, list[dict]]:
    """คืน {ticker: [changes]} — window_days=None ใช้คู่ล่าสุด (daily), ใส่เลข = สะสมทั้งช่วง."""
    out: dict[str, list[dict]] = {}
    for tk in tickers:
        changes = (
            detect_changes(tk)["changes"] if window_days is None else changes_over_window(tk, window_days)
        )
        if changes:
            out[tk] = changes
    return out


def build_report(mode: str | None = None, dashboard_url: str = "http://localhost:3000") -> str:
    mode = mode or pick_mode()
    analyses = latest_per_ticker()
    analyzed = {a["ticker"] for a in analyses}
    newcomers = [a for a in analyses if _is_first_run(a["ticker"])]
    veterans = [a for a in analyses if a["ticker"] not in {n["ticker"] for n in newcomers}]

    lines = [f"**{TITLE[mode]} — {date.today().isoformat()}**", ""]

    # (0) ตัวที่เพิ่งวิเคราะห์ครั้งแรก -> baseline เต็ม (ทุกโหมด เพราะยังไม่มีอะไรให้เทียบ)
    if newcomers:
        lines.append("🆕 **เริ่มติดตามใหม่**")
        for a in newcomers:
            lines += _full_picture(a)
        lines.append("")

    # (1) พอร์ตของคุณ — P&L/edge เทียบ benchmark (ไม่ผูกกับ veterans เพราะไม่ต้องมีผลวิเคราะห์
    # LLM ก็คำนวณได้ ราคาล้วนๆ) แสดงทุกโหมด เพราะเป็นสถานะเงินจริง ไม่ใช่แค่ข้อมูลวิเคราะห์
    lines += _portfolio_section()

    # (2) สิ่งที่เปลี่ยน — เฉพาะตัวที่มีประวัติให้เทียบ (veterans)
    if veterans:
        changes_by_ticker = _gather_changes([a["ticker"] for a in veterans], WINDOW_DAYS[mode])
        assessment_by_ticker = {a["ticker"]: a["summary"].get("thesis_assessment", "") for a in veterans}
        holdings = _holding_tickers()

        # (2a) THESIS พัง — แยก 'ถืออยู่จริง' (ต้องตัดสินใจด่วน) กับ 'แค่จับตา' (ข้อมูลประกอบ)
        # เพราะ breach ของโพซิชันจริงกับของที่ยังไม่ซื้อ มีน้ำหนักต่างกันมาก (ด่าน 4/7)
        def _breach_block(tk: str, breaches: list[dict], emoji: str) -> list[str]:
            block = [f"{emoji} **{tk}**"]
            for c in breaches:
                block.append(f"   • {c['detail']}")
            if assessment_by_ticker.get(tk):
                block.append(f"   🤖 {assessment_by_ticker[tk]}")
            return block

        breach_by_ticker = {
            tk: [c for c in changes if c["type"] in BREACH_TYPES]
            for tk, changes in changes_by_ticker.items()
        }
        breach_by_ticker = {tk: b for tk, b in breach_by_ticker.items() if b}
        holding_breaches = {tk: b for tk, b in breach_by_ticker.items() if tk in holdings}
        watching_breaches = {tk: b for tk, b in breach_by_ticker.items() if tk not in holdings}

        # holding breach เต็มรูปแบบไปช่อง Portfolio Alert แยกแล้ว (ต้องรู้ทันที) — ในนี้แค่
        # เตือนสั้นๆ ว่ามีอยู่ กันไม่ให้คนอ่านแค่ report หลักพลาดไปเลยว่ามีเรื่องด่วนรออยู่
        if holding_breaches:
            lines.append(f"🚨 มีเงื่อนไขออกโดนแตะ {len(holding_breaches)} โพซิชันที่ถืออยู่ — ดูช่อง Portfolio Alert")
            lines.append("")
        if watching_breaches:
            lines.append("👀 **เงื่อนไขออกโดนแตะ — แค่จับตาอยู่ (ยังไม่ถือ)**")
            for tk, b in watching_breaches.items():
                lines += _breach_block(tk, b, "🟡")
            lines.append("")

        # (2b) การเปลี่ยนแปลงอื่น ๆ (ไม่ใช่ breach)
        other_lines: list[str] = []
        for tk, changes in changes_by_ticker.items():
            for c in changes:
                if c["type"] in BREACH_TYPES:
                    continue
                em = SEVERITY_EMOJI.get(c["severity"], "•")
                other_lines.append(f"{em} **{tk}** — {c['detail']}")
        if other_lines:
            lines.append("⚠️ **เปลี่ยนแปลงที่ต้องดู**")
            lines += other_lines
            lines.append("")
        elif not holding_breaches and not watching_breaches:
            lines.append("✅ ไม่มีการเปลี่ยนแปลงที่แตะ thesis ในช่วงนี้")
            lines.append("")

    # (2) เนื้อหาหลักตามโหมด
    if mode == "monthly":
        lines.append("**ทบทวน Thesis รายตัว**")   # monthly = ภาพเต็มทุกตัว ไม่ใช่แค่บรรทัดเดียว
        for a in veterans:
            lines += _full_picture(a)
    else:
        lines.append("**สถานะพื้นฐาน**")           # daily/weekly = สถานะย่อพอ
        for a in veterans:
            lines.append(_status_line(a))

    # (3) ตัวที่ยังไม่เคยถูกวิเคราะห์เลย (เพิ่งเพิ่มผ่าน UI แต่ยัง pending)
    pending = [r["ticker"] for r in list_all() if r["ticker"] not in analyzed]
    if pending:
        lines.append("")
        lines.append("⏳ รอวิเคราะห์: " + ", ".join(pending))

    lines.append("")
    lines.append(f"🔎 รายละเอียด/tooltip: {dashboard_url}")
    return "\n".join(lines)


def send_report(mode: str | None = None) -> bool:
    """สร้าง report (auto เลือกโหมดจากวันที่ถ้าไม่ระบุ mode) แล้วส่งเข้า Discord.
    ใช้ post_chunks กัน monthly report ยาวเกิน 2000 ตัวอักษรแล้วโดนตัดทอนเงียบๆ."""
    return post_chunks(build_report(mode))


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio alert (Phase 5.5) — เงื่อนไขออกที่โดนแตะเฉพาะโพซิชันที่ถืออยู่จริง (ไม่ใช่แค่
# จับตา) แยกช่องจาก report หลักเพราะเป็นสัญญาณที่ต้องรู้ทันที ต่างจาก research feed ทั่วไป
# ที่เช็ควันละครั้งพอ — ตั้ง push notification เฉพาะช่องนี้ได้ (DISCORD_WEBHOOK_URL_PORTFOLIO)
# ─────────────────────────────────────────────────────────────────────────────
def build_portfolio_alert() -> str | None:
    """แจ้งเตือนเงื่อนไขออกที่โดนแตะของ 'โพซิชันที่ถืออยู่จริง' เท่านั้น — alert-only:
    คืน None ถ้าไม่มี holding เลย หรือไม่มีตัวไหน breach (เงียบไว้ ไม่ใช่ error)."""
    holdings = _holding_tickers()
    if not holdings:
        return None

    assessment_by_ticker = {
        a["ticker"]: a["summary"].get("thesis_assessment", "")
        for a in latest_per_ticker() if a["ticker"] in holdings
    }

    breach_lines: list[str] = []
    for tk in sorted(holdings):
        breaches = [c for c in detect_changes(tk)["changes"] if c["type"] in BREACH_TYPES]
        if not breaches:
            continue
        breach_lines.append(f"🔴 **{tk}**")
        for c in breaches:
            breach_lines.append(f"   • {c['detail']}")
        if assessment_by_ticker.get(tk):
            breach_lines.append(f"   🤖 {assessment_by_ticker[tk]}")

    if not breach_lines:
        return None   # ไม่มี holding ไหน breach = ไม่ต้องแจ้ง (เงียบตามหลัก alert-only)

    lines = [f"🚨 **Portfolio Alert — ต้องตัดสินใจ ({date.today().isoformat()})**", ""]
    lines += breach_lines
    lines.append("")
    lines.append("🔎 ดู P&L เต็ม: `python -m src.agent.performance`")
    return "\n".join(lines)


def send_portfolio_alert() -> bool:
    """ส่ง portfolio alert เข้าช่อง Discord แยก (DISCORD_WEBHOOK_URL_PORTFOLIO).
    ไม่มี breach หรือไม่ได้ตั้ง webhook นี้ไว้ -> ข้ามเงียบๆ (ไม่ถือว่า fail)."""
    report = build_portfolio_alert()
    if report is None:
        return True
    webhook = os.environ.get("DISCORD_WEBHOOK_URL_PORTFOLIO")
    if not webhook:
        print("[portfolio-alert] ไม่มี DISCORD_WEBHOOK_URL_PORTFOLIO — ข้ามการส่ง")
        return False
    return post_chunks(report, webhook_url=webhook)


# ─────────────────────────────────────────────────────────────────────────────
# Quality report (Phase 4) — คนละหัวข้อกับ daily/weekly/monthly ข้างบน (นั่นคือ
# "หุ้นตัวนี้น่าสนใจไหม", อันนี้คือ "ระบบคำนวณของเราเองยังทำงานถูกไหม") จึงแยกส่งไปช่อง
# Discord อื่น (DISCORD_WEBHOOK_URL_QUALITY) ไม่ปนกับ report หลัก
# ─────────────────────────────────────────────────────────────────────────────
def _flag_mismatches(a: dict, key: str, source_label: str, ref_label: str, threshold: float) -> str | None:
    """ตรวจ eval หนึ่งชั้น (extraction หรือ xbrl) ของ ticker เดียว -> 1 บรรทัด flag ถ้าต่ำกว่าเกณฑ์."""
    result = a.get(key)
    if not result or result.get("accuracy") is None:
        return None
    acc = result["accuracy"]
    if acc >= threshold:
        return None
    mismatches = [c for c in result["checks"] if not c["within_tolerance"]]
    detail = "; ".join(f"{c['metric']} ours={c['ours']:.2f} vs {ref_label}={c['reference']:.2f}" for c in mismatches)
    return f"🔴 **{a['ticker']}** — {source_label} accuracy {acc:.0%} ({detail})"


def build_quality_report(threshold: float = EXTRACTION_WARN_THRESHOLD) -> str | None:
    """สรุป ticker ที่ accuracy ต่ำกว่าเกณฑ์ — ทั้ง extraction (Phase 4, เทียบ yfinance เอง) และ
    xbrl (Phase 12, เทียบ SEC XBRL จริง — ground truth ที่อิสระกว่า) — alert-only เหมือน daily
    report: คืน None ถ้าทุกตัวปกติ (เงียบไว้ ไม่ใช่ error ไม่ต้องส่งอะไร)."""
    flagged = []
    for a in latest_per_ticker():
        f1 = _flag_mismatches(a, "extraction", "extraction", "yfinance", threshold)
        f2 = _flag_mismatches(a, "xbrl", "xbrl (SEC ground truth)", "xbrl", threshold)
        flagged += [f for f in (f1, f2) if f]

    if not flagged:
        return None   # ไม่มีอะไรผิดปกติ = ไม่ต้องส่ง (เงียบตามหลัก alert-only)

    lines = [f"🔬 **Extraction Accuracy Alert — {date.today().isoformat()}**", ""]
    lines += flagged
    lines.append("")
    lines.append("ตรวจสอบเพิ่ม: `python -m src.providers.stock.fundamentals <TICKER>` หรือ `python -m src.evals.check_xbrl_accuracy`")
    return "\n".join(lines)


def send_quality_report() -> bool:
    """ส่ง quality alert เข้าช่อง Discord แยก (DISCORD_WEBHOOK_URL_QUALITY).
    ไม่มีอะไรผิดปกติ หรือไม่ได้ตั้ง webhook นี้ไว้ -> ข้ามเงียบๆ (ไม่ถือว่า fail)."""
    report = build_quality_report()
    if report is None:
        return True
    webhook = os.environ.get("DISCORD_WEBHOOK_URL_QUALITY")
    if not webhook:
        print("[quality-report] ไม่มี DISCORD_WEBHOOK_URL_QUALITY — ข้ามการส่ง")
        return False
    return post_chunks(report, webhook_url=webhook)


if __name__ == "__main__":
    # ทดสอบ:  python -m src.agent.report --mode weekly
    #         python -m src.agent.report --quality
    #         python -m src.agent.report --portfolio
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--quality":
        ok = send_quality_report()
        print("quality report:", "sent" if ok else "skipped/failed")
    elif len(sys.argv) > 1 and sys.argv[1] == "--portfolio":
        ok = send_portfolio_alert()
        print("portfolio alert:", "sent" if ok else "skipped/failed")
    else:
        forced_mode = sys.argv[2] if len(sys.argv) > 1 and sys.argv[1] == "--mode" else None
        send_report(forced_mode)
