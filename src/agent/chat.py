"""Portfolio chat (Phase 25) — "ถามพอร์ตได้เลย": ถามคำถามภาษาคนเกี่ยวกับ watchlist/portfolio ของ
ตัวเอง แล้วให้ agent ไปขุดข้อมูลจริงมาตอบ พร้อมอ้างอิงตัวเลข แทนที่จะต้องไล่อ่าน/ตีความหน้าเว็บเอง.

Reuse เต็มๆ จาก Phase 13 (agentic investigation loop, src/agent/investigate.py): loop เดิม
(run_investigation), GeminiPolicy เดิม (แค่ generalize prompt/system ให้ inject ได้ — ดู
investigate.py) — ต่างกันแค่ 2 อย่าง:
  1. Toolbox คนละชุด: investigate.py ขุดลึก "หุ้นตัวเดียว" (ต้องดึง facts/news/xbrl สดของ ticker
     นั้น), chat.py นี้ตอบคำถาม "ข้าม watchlist ทั้งก้อน" โดยอ่านจากผลวิเคราะห์ที่คำนวณเก็บไว้
     ใน DB อยู่แล้ว (latest_per_ticker/health/valuation/changes/performance) ไม่ fetch สดจาก
     yfinance เลย — เร็วกว่ามาก และคำตอบสะท้อน "สิ่งที่ระบบรู้ล่าสุด" ตรงกับที่ผู้ใช้เห็นบนเว็บ
  2. Prompt/system เป็น Q&A แบบสนทนา ไม่ใช่ "investigate แล้วสรุปจบ"

โควตา: endpoint เดียวในทั้ง API ที่ยิง Gemini จริง (ที่เหลือ deterministic ล้วน) — ใช้เมื่อผู้ใช้
กดถามเองเท่านั้น (ไม่มี auto-trigger ที่ไหนเรียกมันเลย) ผ่าน max_steps ที่จำกัดไว้ (MAX_CHAT_STEPS)
กัน 1 คำถามกิน tool-call เกินจำเป็น.
"""
from src.agent.investigate import GeminiPolicy, ToolSpec, run_investigation

MAX_CHAT_STEPS = 4   # คำถามพอร์ตปกติไม่ต้องขุดลึกเท่า investigate ตัวเดียว (MAX_STEPS=6 ที่นั่น)

_STATUS_TH = {"holding": "ถืออยู่", "watching": "จับตา", "frozen": "แช่แข็ง"}

_CHAT_SYSTEM = """You are a portfolio research assistant for a LONG-TERM investor who holds
through years, not days, and exits only when the investment thesis breaks (not on daily price
moves). The user is not a finance expert — answer in plain, concrete terms, not jargon.

You have tools to inspect the user's OWN watchlist/portfolio: health scores (Piotroski fundamentals
+ reverse-DCF valuation), what changed since the last analysis, the user's own written thesis (if
set), and realized performance vs their benchmark. ALWAYS use tools to ground your answer in the
user's actual data — never invent numbers or reason from general market knowledge alone. For
"which is better" questions use compare_tickers. For "what's concerning" questions check
get_ticker_changes across the relevant tickers, not just list_portfolio's snapshot.

Answer in THAI, concise (2-6 sentences), citing concrete tickers/numbers you found. This is
RESEARCH to help the investor think — never a buy/sell or timing instruction; say so plainly if
the question is asking for a direct buy/sell call."""


def _fmt_health(health: dict | None) -> str:
    if not health or health.get("score") is None:
        reason = (health or {}).get("reasons", [None])[0]
        return f"ประเมิน health ไม่ได้{f' ({reason})' if reason else ''}"
    return f"health {health['score']:.1f}/{health.get('max', 11):.0f} ({health.get('tier', '?')})"


def build_portfolio_toolbox() -> list[ToolSpec]:
    """สร้าง tool ทั้งชุดครั้งเดียว — closure ดึงข้อมูลจาก DB ตอนสร้าง (ไม่ใช่ตอนเรียกแต่ละ tool)
    เพื่อให้ agent เห็นภาพ 'ตอนเริ่มคำถามนี้' สอดคล้องกันทุก tool call ในสนทนาเดียวกัน."""
    from src.watchlist.store import list_all
    from src.history.store import latest_per_ticker
    from src.agent.changes import detect_changes
    from src.agent.performance import portfolio_edge
    from src.thesis.store import get_thesis

    watchlist = list_all()
    analyses = {a["ticker"]: a for a in latest_per_ticker()}

    def _list_portfolio(args: dict) -> str:
        if not watchlist:
            return "watchlist ว่าง — ยังไม่มี ticker ที่จับตา"
        lines = []
        for w in watchlist:
            t = w["ticker"]
            a = analyses.get(t)
            status = _STATUS_TH.get(w["status"], w["status"])
            health_str = _fmt_health(a.get("health") if a else None)
            lines.append(f"{t}: {status}, {health_str}" if a else f"{t}: {status}, ยังไม่เคยวิเคราะห์")
        return "\n".join(lines)

    def _get_ticker_summary(args: dict) -> str:
        ticker = (args.get("ticker") or "").strip().upper()
        a = analyses.get(ticker)
        if a is None:
            return f"ไม่มีผลวิเคราะห์ของ {ticker} (ไม่อยู่ใน watchlist หรือยังไม่เคยวิเคราะห์)"
        s = a["summary"]
        health, valuation = a.get("health") or {}, a.get("valuation") or {}
        parts = [
            f"{ticker} @ ${a['price']}",
            f"พื้นฐาน (LLM label): {s['fundamental_strength']}, ราคา: {s['valuation_view']}, ข่าว: {s['sentiment']}",
            _fmt_health(health),
        ]
        if health.get("reasons"):
            parts.append("เหตุผล health: " + "; ".join(health["reasons"]))
        if valuation.get("implied_growth") is not None:
            parts.append(
                f"Reverse-DCF: ตลาดคาด FCF โต {valuation['implied_growth']:.1f}%/ปี เทียบ realistic "
                f"{valuation['realistic_growth']:.1f}%/ปี (gap {valuation['gap']:+.1f}pp)"
            )
        thesis = get_thesis(ticker)
        if thesis:
            parts.append(f"Thesis ที่ผู้ใช้จดไว้เอง: {thesis['thesis']}")
        if s.get("beginner_summary"):
            parts.append(f"สรุปภาษาง่าย: {s['beginner_summary']}")
        return "\n".join(parts)

    def _get_ticker_changes(args: dict) -> str:
        ticker = (args.get("ticker") or "").strip().upper()
        report = detect_changes(ticker)
        changes = report.get("changes", [])
        if not changes:
            return f"{ticker}: ไม่มีอะไรสำคัญเปลี่ยนตั้งแต่ครั้งก่อน"
        return "\n".join(f"[{c['severity']}] {c['detail']}" for c in changes)

    def _compare_tickers(args: dict) -> str:
        tickers = [t.strip().upper() for t in (args.get("tickers") or "").split(",") if t.strip()]
        if len(tickers) < 2:
            return "ต้องระบุอย่างน้อย 2 ticker คั่นด้วย comma เช่น 'MSFT,GOOGL'"
        lines = []
        for t in tickers:
            a = analyses.get(t)
            if a is None:
                lines.append(f"{t}: ไม่มีข้อมูล")
                continue
            valuation = a.get("valuation") or {}
            gap = valuation.get("gap")
            gap_str = f", valuation gap {gap:+.1f}pp" if gap is not None else ""
            lines.append(f"{t}: {_fmt_health(a.get('health'))}{gap_str}")
        return "\n".join(lines)

    def _get_performance(args: dict) -> str:
        perf = portfolio_edge()
        if perf["total_positions"] == 0:
            return "ยังไม่มี holding ที่ถืออยู่จริง (มีแต่ ticker ที่จับตา)"
        lines = [f"พอร์ตรวม: ชนะ {perf['benchmark']} {perf['beating_benchmark']}/{perf['total_positions']} ตัว"]
        if perf.get("total_return") is not None:
            lines.append(f"ผลตอบแทนรวม: {perf['total_return']:+.1f}%")
        for p in perf["positions"]:
            lines.append(
                f"{p['ticker']}: คุณ {p['your_return']:+.1f}% vs {p['benchmark']} {p['benchmark_return']:+.1f}% "
                f"(edge {p['edge']:+.1f}pp), ถือมา {p['holding_days']} วัน"
            )
        return "\n".join(lines)

    return [
        ToolSpec("list_portfolio",
                 "List every ticker in the watchlist with status (holding/watching/frozen) and "
                 "current health score. Call this first for an overview before drilling into specifics.",
                 {}, _list_portfolio),
        ToolSpec("get_ticker_summary",
                 "Get the latest full analysis of ONE ticker: fundamental/valuation view, health "
                 "score + reasons, reverse-DCF, and the user's own written thesis if set.",
                 {"ticker": {"type": "STRING", "description": "ticker symbol", "required": True}},
                 _get_ticker_summary),
        ToolSpec("get_ticker_changes",
                 "Get what changed for one ticker since its last analysis run (strength/valuation "
                 "flips, thesis-relevant news, metric moves, health jumps). Use for 'what's concerning' questions.",
                 {"ticker": {"type": "STRING", "description": "ticker symbol", "required": True}},
                 _get_ticker_changes),
        ToolSpec("compare_tickers",
                 "Compare health score and valuation gap side-by-side for 2+ tickers. Use this "
                 "for 'which is better' questions instead of calling get_ticker_summary repeatedly.",
                 {"tickers": {"type": "STRING", "description": "comma-separated tickers, e.g. 'MSFT,GOOGL'", "required": True}},
                 _compare_tickers),
        ToolSpec("get_performance",
                 "Get realized return vs benchmark for every position actually held (not just watched), plus portfolio totals.",
                 {}, _get_performance),
    ]


def _render_history(chat_history: list[dict]) -> str:
    if not chat_history:
        return ""
    lines = [f"{'คุณ' if t.get('role') == 'user' else 'ผู้ช่วย'}: {t.get('text', '')}" for t in chat_history]
    return "บทสนทนาก่อนหน้า:\n" + "\n".join(lines) + "\n\n"


def ask(question: str, chat_history: list[dict] | None = None, max_steps: int = MAX_CHAT_STEPS) -> dict:
    """ถามคำถามเกี่ยวกับ watchlist/portfolio ของตัวเอง -> Investigation dict (conclusion + steps
    ที่ agent เดิน ให้เห็นว่ามันไปดึงอะไรมาตอบ). ยิง Gemini จริงทุกครั้งที่เรียก (มีโควตา).

    chat_history = [{"role": "user"|"assistant", "text": ...}, ...] จากรอบก่อนหน้าในสนทนาเดียวกัน
    — ส่งเป็นข้อความล้วนแทรกใน prompt (ไม่ได้ต่อ Gemini contents ข้าม HTTP request จริงๆ) แต่ละ
    คำถามจึงเป็น tool-calling loop ใหม่ของตัวเอง ใช้ history แค่ให้ 'จำบริบท' การสนทนาก่อนหน้า."""
    tools = build_portfolio_toolbox()
    prompt = _render_history(chat_history or []) + f"คำถาม: {question}"
    policy = GeminiPolicy(prompt, tools, system=_CHAT_SYSTEM)
    inv = run_investigation(policy, tools, max_steps=max_steps, ticker="")
    return inv.to_dict()


if __name__ == "__main__":
    # python -m src.agent.chat "ตอนนี้ตัวไหนน่าห่วงสุด"
    import sys

    q = " ".join(sys.argv[1:]) or "สรุปภาพรวม watchlist ตอนนี้หน่อย"
    result = ask(q)
    print(f"=== ถาม: {q} ===\n")
    for i, s in enumerate(result["steps"], 1):
        print(f"[{i}] 🔧 {s['tool']}({s['args']})")
        obs = s["observation"] if len(s["observation"]) < 300 else s["observation"][:300] + "..."
        print(f"    → {obs}\n")
    print("🧠 คำตอบ:")
    print(result["conclusion"])