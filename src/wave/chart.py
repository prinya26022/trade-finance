"""ภาพ 4H ธีมมืดแบบจอ TradingView ที่ผู้ใช้ดูอยู่ + ป้ายคลื่น + เส้นตาย/เป้าของแต่ละฉาก.

ทำไมวาดเองแทนการแคปจาก TradingView: ภาพต้องมาจากแท่งชุดเดียวกับตัวเลขในข้อความ (แคปมาจะเป็น
คนละ feed — คนละ exchange คนละราคา) และการเปิดเว็บด้วยบอทติดทั้งล็อกอิน, ข้อตกลงการใช้งาน
และหน้าเว็บที่เปลี่ยนได้ทุกเมื่อ. ใช้ EMA ชุดเดียวกับที่ผู้ใช้ตั้งบน TradingView แทน เพื่อให้
หน้าตาคุ้นตา. ข้อความในภาพเป็นอังกฤษล้วน (ฟอนต์ไม่มีไทยบน CI — ดู src/technical/chart.py)
"""
import io
from datetime import timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.wave.analysis import Report  # noqa: E402
from src.wave.candles import Candle, resample_4h  # noqa: E402
from src.wave.trend import ema  # noqa: E402  (Pine ta.ema — ที่เดียวทั้งแพ็กเกจ)

BG, GRID, TEXT, MUTED = "#131722", "#2a2e39", "#d1d4dc", "#787b86"
UP, DOWN = "#26a69a", "#ef5350"
# EMA ตาม indicator ของผู้ใช้ (สีเดิม) — 50 กับ 200 ซึ่งเป็นเส้นหลักที่ใช้ตัดสินเทรนด์ D/4H ด้วย
EMAS = ((50, "#9c27b0"), (200, "#ffeb3b"))
TREND_COLOR = {"up": UP, "down": DOWN, "mixed": "#fbc02d", "unknown": MUTED}
SCENARIO_COLOR = {"A": "#42a5f5", "B": "#ff9800", "C": "#ab47bc"}
SHORT = {"A": "A: i of 5, now ii", "B": "B: 5 done", "C": "C: 4 not done"}


def render_png(rep: Report, hourly: list[Candle]) -> bytes:
    c4 = resample_4h(hourly)
    closes = [c.close for c in c4]
    lines = {n: ema(closes, n) for n, _ in EMAS}
    start = rep.pivots[0].ts - timedelta(days=3)
    idx = [i for i, c in enumerate(c4) if c.ts >= start]
    view = [c4[i] for i in idx]

    fig, ax = plt.subplots(figsize=(12, 6.8), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    width = timedelta(hours=2.8)
    for c in view:
        col = UP if c.close >= c.open else DOWN
        ax.vlines(c.ts + timedelta(hours=2), c.low, c.high, color=col, lw=0.8)
        ax.add_patch(plt.Rectangle((c.ts + timedelta(hours=0.6), min(c.open, c.close)), width,
                                   max(abs(c.close - c.open), 1e-9), color=col, lw=0))
    for n, col in EMAS:
        pts = [(c4[i].ts + timedelta(hours=2), lines[n][i]) for i in idx if lines[n][i] is not None]
        if pts:
            ax.plot(*zip(*pts), color=col, lw=1.1, label=f"EMA {n}")

    # เส้นเชื่อมจุดที่มาร์ก + ป้าย
    px = [(p.ts, p.price) for p in rep.pivots]
    ax.plot(*zip(*px), color=TEXT, lw=1.3)
    span = max(c.high for c in view) - min(c.low for c in view)
    for p in rep.pivots:
        off = span * (0.03 if p.kind == "H" else -0.045)
        ax.text(p.ts, p.price + off, p.label, color=TEXT, fontsize=15, weight="bold", ha="center")
    if rep.sub.get("pull") is not None:
        s1, pull = (rep.sub["s1_ts"], rep.sub["s1"]), (rep.sub["pull_ts"], rep.sub["pull"])
        ax.plot([rep.pivots[-1].ts, s1[0], pull[0]], [rep.pivots[-1].price, s1[1], pull[1]],
                color=MUTED, lw=1.1, ls="--")
        ax.text(s1[0], s1[1] + span * 0.03, "i? / 5?", color=MUTED, fontsize=10, ha="center")
        ax.text(pull[0], pull[1] - span * 0.045, "ii?", color=MUTED, fontsize=10, ha="center")

    # เส้นตายของแต่ละฉาก (เส้นประ) + เป้าหลัก (จุดไข่ปลา, ฉากละไม่เกิน 2 เส้นกันรก)
    right = view[-1].ts + timedelta(hours=6)
    for sc in rep.scenarios:
        col = SCENARIO_COLOR.get(sc.key, MUTED)
        if sc.kill_level is not None:
            ax.axhline(sc.kill_level, color=col, lw=1, ls="--", alpha=0.9)
            ax.text(right, sc.kill_level, f" {sc.key} dies {sc.kill_level:,.0f}", color=col,
                    fontsize=8.5, va="center")
        for label, lvl in sc.targets[:2]:
            ax.axhline(lvl, color=col, lw=0.8, ls=":", alpha=0.7)
            ax.text(right, lvl, f" {sc.key} tgt {lvl:,.0f}", color=col, fontsize=8, va="center", alpha=0.9)

    last = rep.last
    ax.axhline(last.close, color=MUTED, lw=0.6, ls=":")
    # แถบเทรนด์ TF ใหญ่ อยู่ "เหนือ" กรอบกราฟ — ในกรอบจะทับป้ายเป้า/เส้นตายที่ขอบขวา
    for i, t in enumerate(rep.trend):
        ax.text(0.62 + i * 0.095, 1.012, f"{t.tf} {t.state.upper()}", transform=ax.transAxes,
                ha="left", va="bottom", fontsize=9, weight="bold", color=BG,
                bbox=dict(boxstyle="round,pad=0.3", fc=TREND_COLOR[t.state], ec="none"))
    # เว้นขอบล่าง/บนให้ป้ายคลื่นกับบรรทัดสถานะไม่ทับกัน — รวมทุกเส้นที่วาดไว้ในช่วงด้วย
    levels = [c.low for c in view] + [c.high for c in view] + [
        x for sc in rep.scenarios for x in ([sc.kill_level] if sc.kill_level else []) + [v for _, v in sc.targets[:2]]]
    lo, hi = min(levels), max(levels)
    ax.set_ylim(lo - 0.10 * (hi - lo), hi + 0.05 * (hi - lo))
    ax.set_title(f"{rep.symbol} 4H - wave check ({last.ts:%Y-%m-%d %H:%M} UTC, last {last.close:,.0f})",
                 color=TEXT, loc="left", fontsize=11)
    status = "   ".join(f"{SHORT.get(sc.key, sc.key)}: {'ALIVE' if sc.alive else 'DEAD'}"
                       for sc in rep.scenarios) or "rules check only"
    ax.text(0.01, 0.02, status + "   |   rules " + ("PASS" if rep.valid else "FAIL"),
            transform=ax.transAxes, color=TEXT, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=8)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.grid(color=GRID, lw=0.6)
    ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=TEXT)
    ax.set_xlim(view[0].ts, right + timedelta(hours=40))
    ax.yaxis.tick_right()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
