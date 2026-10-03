"""วาดภาพกราฟ Week/Month เป็น PNG (bytes) — ไม่แตะเน็ต ไม่เขียนไฟล์ เทสต์ได้ออฟไลน์.

**ข้อความในภาพเป็นอังกฤษ/ตัวเลขล้วนโดยตั้งใจ**: ฟอนต์ default ของ matplotlib (DejaVu) ไม่มี
อักษรไทย — บนเครื่อง CI (ubuntu) ภาษาไทยจะกลายเป็นกล่องสี่เหลี่ยมแบบเงียบๆ ทั้งที่บนเครื่องเรา
ดูปกติ. คำอธิบายภาษาไทยอยู่ในข้อความ Discord ที่ส่งคู่กับภาพแทน (notify.py)

ภาพวาดจากแท่ง **ชุดเดียวกับที่คิดคะแนน** — ถ้าภาพดึงข้อมูลเองจะมีวันที่ภาพกับตัวเลขไม่ตรงกัน
(บทเรียนเดียวกับ Phase 49.2 ที่หน้าเว็บอ่าน snapshot แทนการดึงเอง)
"""
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")   # headless: ไม่มีจอบน CI และไม่ต้องการหน้าต่าง
import matplotlib.pyplot as plt  # noqa: E402

from src.technical import score as S  # noqa: E402
from src.technical.bars import Bar  # noqa: E402
from src.technical.indicators import sma  # noqa: E402

WEEKS_SHOWN = 104    # 2 ปี: เห็นยอด 52W และเส้นเฉลี่ยครบหนึ่งรอบ
MONTHS_SHOWN = 36

SHORT_LABELS = {     # ภาษาอังกฤษสั้นๆ สำหรับในภาพ (ตัวเต็มภาษาไทยอยู่ใน score.py)
    "T1": "Week close > SMA40W",
    "T2": "SMA40W rising (vs 10w ago)",
    "T3": "Month close > SMA10M",
    "T4": "12-1m return vs benchmark",
    "T5": "Within 25% of 52W high",
    "T6": "Weekly RSI <= 75",
}

PRICE, AVG, HIGH, PASS, FAIL, MUTED = "#1f2937", "#2563eb", "#9ca3af", "#15803d", "#b91c1c", "#6b7280"


def _rolling_sma(closes: list[float], n: int) -> list[float | None]:
    return [sma(closes[: i + 1], n) for i in range(len(closes))]


def _dates(bars: list[Bar]) -> list[date]:
    return [date.fromisoformat(d) for d, _ in bars]


def render_png(ticker: str, week: list[Bar], month: list[Bar], result: dict) -> bytes:
    """ภาพ 2 แผง (Week บน, Month ล่าง) + กล่องคะแนน T1–T6. week/month = แท่งปิดแล้ว เก่า -> ใหม่."""
    wc = [c for _, c in week]
    mc = [c for _, c in month]
    w_sma = _rolling_sma(wc, S.SMA_WEEKS)[-WEEKS_SHOWN:]
    m_sma = _rolling_sma(mc, S.SMA_MONTHS)[-MONTHS_SHOWN:]
    wd, wc = _dates(week)[-WEEKS_SHOWN:], wc[-WEEKS_SHOWN:]
    md, mc = _dates(month)[-MONTHS_SHOWN:], mc[-MONTHS_SHOWN:]

    fig = plt.figure(figsize=(11, 7.5), dpi=100)
    grid = fig.add_gridspec(2, 2, width_ratios=[3.2, 1.4], hspace=0.35, wspace=0.08)
    ax_w, ax_m, ax_s = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[1, 0]), fig.add_subplot(grid[:, 1])

    ax_w.plot(wd, wc, color=PRICE, lw=1.4, label="Week close")
    ax_w.plot(wd, w_sma, color=AVG, lw=1.6, label=f"SMA{S.SMA_WEEKS}W")
    if len(wc) >= 1:
        high52 = max(c for _, c in week[-52:])
        ax_w.axhline(high52, color=HIGH, lw=1, ls="--", label="52W high")
        ax_w.axhline(high52 * (1 + S.MAX_DRAWDOWN_PCT / 100), color=HIGH, lw=1, ls=":",
                     label=f"{S.MAX_DRAWDOWN_PCT:.0f}% from high")
        ax_w.scatter([wd[-1]], [wc[-1]], color=PRICE, zorder=5, s=18)
    ax_w.set_title(f"{ticker} - weekly (last closed {result.get('last_week')})", loc="left", fontsize=11)

    ax_m.plot(md, mc, color=PRICE, lw=1.4, marker="o", ms=2.5, label="Month close")
    ax_m.plot(md, m_sma, color=AVG, lw=1.6, label=f"SMA{S.SMA_MONTHS}M")
    ax_m.set_title(f"monthly (last closed {result.get('last_month')})", loc="left", fontsize=11)

    for ax in (ax_w, ax_m):
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="upper left", frameon=False)
        ax.tick_params(labelsize=8)

    _score_box(ax_s, result)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)       # ไม่ปิด = รันทั้ง watchlist แล้ว memory บวมเรื่อยๆ
    return buf.getvalue()


def _score_box(ax, result: dict) -> None:
    ax.axis("off")
    if result.get("score") is None:
        ax.text(0, 0.95, "UNMEASURABLE", fontsize=14, weight="bold", color=MUTED, va="top")
        return
    ax.text(0, 0.98, f"{result['score']}/{result['max']}", fontsize=26, weight="bold", va="top")
    ax.text(0, 0.88, result["tier"].replace("_", " "), fontsize=11, color=MUTED, va="top")
    y = 0.78
    for c in result["criteria"]:
        mark, color = ("PASS", PASS) if c["passed"] else ("FAIL", FAIL)
        ax.text(0, y, f"{c['key']} {mark}", fontsize=10, weight="bold", color=color, va="top")
        ax.text(0, y - 0.035, SHORT_LABELS[c["key"]], fontsize=8.5, va="top")
        edge = "  (borderline)" if c["borderline"] else ""
        ax.text(0, y - 0.065, f"value {c['value']:+.2f}  margin {c['margin']:+.2f}{edge}",
                fontsize=8, color=MUTED, va="top")
        y -= 0.115
    ax.text(0, 0.02, "Second opinion only - not a buy/sell signal.", fontsize=7.5,
            color=MUTED, style="italic", va="bottom")
