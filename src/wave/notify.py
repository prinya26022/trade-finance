"""ข้อความภาษาไทยอ่านง่าย — ลำดับตามที่คนเทรดต้องรู้: ตอนนี้อยู่ไหน → แต่ละทางตายที่ไหน →
หลักฐาน → ระดับที่ต้องจับตา. ไม่มีเปอร์เซ็นต์ความน่าจะเป็น ไม่มีคำว่าซื้อ/ขาย"""
import os

from src.notify import discord
from src.wave.analysis import Report, fmt

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_WAVE"
LEAN = {"A": "→ เข้าทาง A", "B": "→ เข้าทาง B", "-": ""}
STATE = {"up": "🟢 ขาขึ้น", "down": "🔴 ขาลง", "mixed": "🟡 ปนกัน", "unknown": "⚪ วัดไม่ได้"}


def _trend_lines(rep: Report) -> list[str]:
    if not rep.trend:
        return []
    out = ["**เทรนด์ TF ใหญ่** (ผ่านทุกข้อ = ขาขึ้น · ตกทุกข้อ = ขาลง · นอกนั้น = ปนกัน):"]
    for t in rep.trend:
        lines = " · ".join(f"{k} {fmt(v)}" for k, v in t.lines.items())
        checks = " · ".join(("✅ " if c.up else "❌ " if c.up is False else "➖ ") + c.text for c in t.checks)
        out.append(f"**{t.tf}** {STATE[t.state]} — {checks}" + (f" ({lines})" if lines else ""))
    return out + [""]


def _alignment(rep: Report, bias: str) -> str:
    """ฉากนี้ไปทางเดียวกับ TF ไหน สวน TF ไหน — ข้อเท็จจริง ไม่ใช่โอกาส"""
    with_ = [t.tf for t in rep.trend if t.state == bias]
    against = [t.tf for t in rep.trend if t.state in ("up", "down") and t.state != bias]
    mixed = [t.tf for t in rep.trend if t.state == "mixed"]
    parts = [f"ตาม {', '.join(with_)}" if with_ else "ไม่มี TF ไหนเป็นเทรนด์ทางเดียวกัน",
             f"สวน {', '.join(against)}" if against else "",
             f"TF ที่ยังปนกัน {', '.join(mixed)}" if mixed else ""]
    return "  🧭 " + " · ".join(x for x in parts if x)


def format_message(rep: Report) -> str:
    L = [f"**{rep.name}** · {rep.symbol} ล่าสุด **{fmt(rep.last.close)}** "
         f"({rep.last.ts:%d %b %H:%M} UTC)", "",
         "**จุดที่มาร์ก (ราคาจริงจากแท่ง):** "
         + " · ".join(f"{p.label}={fmt(p.price)}" for p in rep.pivots), ""]

    L.append("**กฎเหล็ก:** " + ("ผ่านครบ ✅" if rep.valid else "ผิด ❌ — count นี้ใช้ไม่ได้"))
    for r in rep.rules:
        if not r.ok or r.text.startswith("คลื่น 4"):     # โชว์ข้อที่ผิด + ข้อที่ใกล้เส้นที่สุดเสมอ
            L.append(f"{'✅' if r.ok else '❌'} {r.text}: {r.detail}")
    L += ["", f"**ตอนนี้:** {rep.state}", ""]
    L += _trend_lines(rep)

    for sc in rep.scenarios:
        mark = "🟢 ยังเป็นไปได้" if sc.alive else "⚫ ตายแล้ว"
        L.append(f"**ฉาก {sc.key} — {sc.title}** ({mark})")
        L.append(f"  {sc.meaning}")
        L.append(f"  ❌ ผิดเมื่อ: {sc.kill_text}")
        if sc.confirm_text:
            L.append(f"  ✔️ ชัดขึ้นเมื่อ: {sc.confirm_text}")
        if sc.targets:
            L.append("  🎯 " + " · ".join(f"{t} {fmt(x)}" for t, x in sc.targets))
        if rep.trend and sc.bias:
            L.append(_alignment(rep, sc.bias))
        L.append("")

    if rep.evidence:
        L.append("**หลักฐานตามตำรา** (แนวโน้ม ไม่ใช่กฎ — ไม่ได้รวมเป็นเปอร์เซ็นต์):")
        L += [f"• {e.text} {LEAN.get(e.leans, '')}".rstrip() for e in rep.evidence]
        L.append("")
    if rep.parent_note:
        L += [f"**ภาพใหญ่:** {rep.parent_note}", ""]

    kills = [(sc.kill_level, sc.key) for sc in rep.scenarios if sc.alive and sc.kill_level is not None]
    if len(kills) >= 2:
        lo, hi = min(kills), max(kills)
        L.append(f"**สรุประดับ:** ระหว่าง {fmt(lo[0])} – {fmt(hi[0])} ยังตัดสินไม่ได้ · "
                 f"หลุด {fmt(lo[0])} ฉาก {lo[1]} ตาย · ทะลุ {fmt(hi[0])} ฉาก {hi[1]} ตาย")
    L.append("_เครื่องไม่ได้นับคลื่นแทน — ตรวจ count ที่มาร์กและไล่ทุกทางที่ราคายังไม่ฆ่า_")
    return "\n".join(L)


def format_summary(rep: Report) -> str:
    """คำบรรยายใต้ภาพ — สั้นพอให้อยู่ใน message เดียวกับภาพเสมอ (เพดาน Discord 2,000 ตัวอักษร).
    รายละเอียดเต็มตามไปเป็นข้อความถัดไป ไม่ถูกตัดทิ้ง"""
    L = [f"**{rep.name}** · {rep.symbol} **{fmt(rep.last.close)}** ({rep.last.ts:%d %b %H:%M} UTC)",
         f"กฎเหล็ก: {'ผ่านครบ ✅' if rep.valid else 'ผิด ❌'} · {rep.state}"]
    if rep.trend:
        L.append("เทรนด์: " + " · ".join(f"{t.tf} {STATE[t.state]}" for t in rep.trend))
    for sc in rep.scenarios:
        L.append(f"**{sc.key}** {sc.title} — {'🟢' if sc.alive else '⚫'} ผิดเมื่อ{sc.kill_text}")
    kills = [(sc.kill_level, sc.key) for sc in rep.scenarios if sc.alive and sc.kill_level is not None]
    if len(kills) >= 2:
        lo, hi = min(kills), max(kills)
        L.append(f"➡️ ระหว่าง {fmt(lo[0])} – {fmt(hi[0])} ยังตัดสินไม่ได้")
    return "\n".join(L)[:discord.DISCORD_CONTENT_LIMIT]


def send(rep: Report, hourly, webhook_url: str | None = None) -> bool:
    from src.notify.discord import post_chunks
    from src.wave.chart import render_png

    url = webhook_url or os.environ.get(WEBHOOK_ENV)
    ok = discord.post_image(format_summary(rep), render_png(rep, hourly),
                            f"wave_{rep.symbol.replace('-', '_')}.png", url)
    return post_chunks(format_message(rep), url) and ok
